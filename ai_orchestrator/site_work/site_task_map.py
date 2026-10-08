"""L1 Shared Contracts — 사이트 업무 지도(Site Task Map) 스키마·분류·병합·조회 (순수 함수).

기준서: docs/specs/2026-10-03_site_task_map.md (M1)

- 네트워크·파일·시계를 쓰지 않는다(시각은 호출자가 문자열로 넘긴다). 입력을 수정하지 않는다.
- 지도에는 **구조만** 담는다: 필드 이름·역할·라벨, 화면 URL, 절차. 입력값·데이터 행·쿠키·토큰은 담지 않는다.
- 위험 등급은 안전 장치다. 애매하면 높은 쪽으로 판정한다(`submit` > `write` > `read`).
- steps 는 Chrome DevTools Recorder JSON(= Puppeteer Replay) 단계 형식과 호환된다.
  값 자리는 실제 값이 아니라 `{{필드이름}}` 매개변수 표시다.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
from typing import Any
from urllib.parse import urlparse

from .site_map_labels import clean_label, is_global_landmark
from .site_map_menu import OPEN_PAGE_ID, validate_open_url
from .site_task_spec import carry_never, effective_never, never_kind

SCHEMA_VERSION = 1

RISK_READ, RISK_WRITE, RISK_SUBMIT = "read", "write", "submit"
RISKS = (RISK_READ, RISK_WRITE, RISK_SUBMIT)
_RISK_RANK = {r: i for i, r in enumerate(RISKS)}

STATE_OBSERVED, STATE_VERIFIED, STATE_STALE = "observed", "verified", "stale"
STATES = (STATE_OBSERVED, STATE_VERIFIED, STATE_STALE)

CAT_SEARCH, CAT_INPUT, CAT_SUBMIT, CAT_LOGIN, CAT_NAVIGATE = "search", "input", "submit", "login", "navigate"
CATEGORIES = (CAT_SEARCH, CAT_INPUT, CAT_SUBMIT, CAT_LOGIN, CAT_NAVIGATE, "download", "unclassified")

AUTH_PUBLIC, AUTH_LOGIN, AUTH_CERT = "public", "login", "certificate"
AUTHS = (AUTH_PUBLIC, AUTH_LOGIN, AUTH_CERT)

# 한글은 부분 문자열, 영문은 단어 앞부분(`display` 가 `pay` 로 걸리지 않게)으로 맞춘다.
_SUBMIT_KO = ("제출", "신고", "통보", "결제", "송금", "이체", "삭제", "제거", "탈퇴", "서명", "전송", "발송", "발급", "승인", "확정", "취소", "로그아웃", "출금", "발행", "인증서", "납부", "지급", "회원가입", "가입하기", "가입신청")
_SUBMIT_EN = ("submit", "delete", "remove", "pay", "send", "logout", "signout", "sign", "approve", "confirm", "withdraw", "cancel")
_WRITE_KO = ("저장", "수정", "등록", "추가", "변경", "업로드", "첨부", "신청", "작성", "글쓰기")
_WRITE_EN = ("save", "update", "add", "edit", "upload", "create", "register", "apply", "insert")

_SKIP_INPUT_TYPES = {"hidden", "submit", "button", "image", "reset"}
_SHORT_ACTION_LINK = 12  # href 가 '#'·javascript: 인 링크는 동작 버튼으로 본다(글자 수 제한)
_BUTTON_TASKS_MAX = 6  # 한 화면에서 버튼 업무로 기록하는 최대 개수(위험한 것부터)
_NEAR = 80  # 입력창에서 문서 순서로 이만큼(요소 수) 안의 컨트롤만 그 업무의 동작 버튼으로 본다


# ── 위험 등급 ─────────────────────────────────────────────────────────────


def _hits(text: str, ko: tuple[str, ...], en: tuple[str, ...]) -> bool:
    low = text.lower()
    if any(w in low for w in ko):
        return True
    tokens = re.findall(r"[a-z]+", low)
    return any(tok.startswith(w) for tok in tokens for w in en)


def risk_of(texts: list[str]) -> str:
    """버튼·동작 이름·URL 조각 목록에서 위험 등급을 정한다. 가장 높은 등급이 이긴다."""
    joined = " ".join(str(t) for t in texts if t)
    if _hits(joined, _SUBMIT_KO, _SUBMIT_EN) or any(str(t).strip().endswith("가입") for t in texts):  # '블로그 마켓 가입' 처럼 끝이 '가입'인 버튼은 가입 제출이다('공제가입번호' 같은 이름은 아니다)
        return RISK_SUBMIT
    if _hits(joined, _WRITE_KO, _WRITE_EN):
        return RISK_WRITE
    return RISK_READ


def max_risk(a: str, b: str) -> str:
    return a if _RISK_RANK[a] >= _RISK_RANK[b] else b


# ── 스냅샷 → 업무 ─────────────────────────────────────────────────────────


def slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()[:60] or "root"


def fingerprint(fields: list[dict[str, Any]]) -> str:
    """필드 이름 집합의 지문. 순서·라벨이 바뀌어도 같고, 필드가 늘거나 줄거나 이름이 바뀌면 달라진다."""
    names = sorted(f"{f.get('name') or f.get('id') or ''}:{f.get('type', '')}" for f in fields)
    return hashlib.sha1("|".join(names).encode("utf-8"), usedforsecurity=False).hexdigest()[:12]  # 변경 감지용 지문, 보안 용도 아님


def _field(raw: dict[str, Any]) -> dict[str, Any] | None:
    typ = str(raw.get("type") or "").lower()
    if typ in _SKIP_INPUT_TYPES or not raw.get("visible", True):
        return None
    name = str(raw.get("name") or "")
    ident = str(raw.get("id") or "")
    if not (name or ident):
        return None
    tag = str(raw.get("tag") or "").upper()
    role = "combobox" if tag == "SELECT" else ("checkbox" if typ == "checkbox" else "radio" if typ == "radio" else "textbox")
    return {
        "name": name,
        "id": ident,
        "type": "password" if typ == "password" else (typ or tag.lower()),
        "role": role,
        "label": str(raw.get("aria") or raw.get("placeholder") or "")[:40],
        "required": bool(raw.get("required")),
    }


def _dedupe_fields(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    out = []
    for f in fields:
        key = (f["name"] or f["id"], f["role"] if f["role"] in ("radio", "checkbox") else f["type"])
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def _has_form_keys(frame: dict[str, Any]) -> bool:
    return any("form" in x for key in ("inputs", "buttons", "links") for x in frame.get(key, []))


def _controls(frame: dict[str, Any], form_key: str | None = None, span: tuple[int, int] | None = None) -> list[str]:
    """동작 컨트롤 이름: 버튼 + href 가 '#'·javascript: 인 짧은 링크.

    스냅샷에 소속 폼 키가 있으면 `form_key` 와 같은 폼의 컨트롤만 쓴다(메뉴 링크가 이 업무의 위험을 올리지 않게).
    `span`(입력창들의 문서 순번 범위)이 있으면 그 앞뒤 `_NEAR` 안의 것만 쓴다(폼이 페이지 전체를 감싸는 사이트 대응).
    키가 없는 예전 스냅샷은 프레임 전체를 쓴다(안전한 쪽으로 넓게).
    """
    scoped = form_key is not None and _has_form_keys(frame)

    def mine(item: dict[str, Any]) -> bool:
        if scoped and str(item.get("form") or "") != form_key:
            return False
        pos = item.get("pos")
        return not (span and isinstance(pos, int) and not span[0] - _NEAR <= pos <= span[1] + _NEAR)

    names = [str(b.get("text") or b.get("aria") or "") for b in frame.get("buttons", []) if mine(b)]
    for link in (x for x in frame.get("links", []) if mine(x)):
        href = str(link.get("href") or "")
        text = str(link.get("text") or "")
        if text and len(text) <= _SHORT_ACTION_LINK and (href in ("#", "") or href.lower().startswith("javascript")):
            names.append(text)
    return [n for n in names if n]


def _primary_control(controls: list[str]) -> str:
    return next((c for c in controls if c in ("검색", "조회", "확인") or "검색" in c or "조회" in c), controls[0] if controls else "")


def recorder_steps(url: str, fields: list[dict[str, Any]], *, risk: str, control: str) -> list[dict[str, Any]]:
    """Recorder JSON 호환 단계. 값은 `{{필드이름}}` 자리표시자. read 업무만 마지막 클릭을 포함한다."""
    steps: list[dict[str, Any]] = [{"type": "navigate", "url": url}]
    for f in fields:
        if f["role"] in ("radio", "checkbox"):
            continue
        sel = [[f"[name='{f['name']}']"]] if f["name"] else [[f"#{f['id']}"]]
        if f["label"]:
            sel.append([f"aria/{f['label']}"])
        steps.append({"type": "change", "selectors": sel, "value": "{{" + (f["name"] or f["id"]) + "}}"})
    if risk == RISK_READ and control:
        steps.append({"type": "click", "selectors": [[f"aria/{control}"], [f"text/{control}"]]})
    return steps


def _form_actions(frame: dict[str, Any], form_key: str) -> list[str]:
    """위험 판정에 쓸 폼 action 경로. 폼 키(`순번:이름`)가 있으면 그 폼 것만, 없으면 프레임의 모든 폼."""
    forms = frame.get("forms", [])
    index = form_key.split(":", 1)[0]
    if _has_form_keys(frame) and index.isdigit():
        forms = [forms[int(index)]] if int(index) < len(forms) else []
    return [urlparse(f.get("action") or "").path for f in forms]


def _group_inputs(frame: dict[str, Any]) -> list[tuple[str, list[dict[str, Any]]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for raw in frame.get("inputs", []):
        groups.setdefault(str(raw.get("form") or ""), []).append(raw)
    return list(groups.items())


def open_page_task(host: str, start_url: str, *, auth: str = AUTH_PUBLIC, now: str = "") -> dict[str, Any]:
    """사이트당 하나인 읽기 업무 `주소 열기` — 지도의 메뉴 색인(또는 결과의 next_url)에서 고른 같은 호스트 주소를 열어 읽는다(M8).

    절차는 `navigate {{url}}` 하나다. 주소는 실행 요청 검증(`validate_run_request`)과 실행기(`_step_navigate`)가 같은 호스트 GET 이동만 허용한다.
    """
    fields = [{"name": "url", "id": "", "type": "text", "role": "textbox", "label": "열 주소(메뉴 색인의 href 또는 결과의 next_url)", "required": True}]
    return {
        "id": OPEN_PAGE_ID,
        "name": "주소 열기(open_page) — 메뉴·다음 쪽 주소를 열어 읽기",
        "category": CAT_NAVIGATE,
        "purpose": "",
        "risk": RISK_READ,
        "auth": auth,
        "state": STATE_OBSERVED,
        "url": start_url,
        "host": host,
        "fields": fields,
        "control": "",
        "outputs": [],
        "steps": [{"type": "navigate", "url": "{{url}}"}],
        "fingerprint": fingerprint(fields),
        "observed_at": now,
        "verified_at": "",
        "failures": 0,
        "changes": [],
    }


def tasks_from_snapshot(snapshot: dict[str, Any], *, auth: str = AUTH_PUBLIC, now: str = "") -> list[dict[str, Any]]:
    """`scripts.explorer.page_snapshot.collect()` 결과 → 업무 목록. 입력창이 없는 화면은 건너뛴다.

    입력창이 어느 폼에 속하는지 스냅샷에 `form` 키가 있으면 폼별로, 없으면 프레임 하나를 업무 하나로 본다.
    """
    url = str(snapshot.get("url") or "")
    host = urlparse(url).hostname or ""
    path = urlparse(url).path or "/"
    title = str(snapshot.get("title") or "")[:80]
    tasks: list[dict[str, Any]] = []
    for frame in snapshot.get("frames", []):
        if "error" in frame:
            continue
        frame_url = str(frame.get("url") or url)
        used_controls: set[str] = set()
        for form_key, raws in _group_inputs(frame):
            kept = [(r, f) for r in raws if (f := _field(r))]
            fields = _dedupe_fields([f for _, f in kept])
            if not fields:
                continue
            positions = [r["pos"] for r, _ in kept if isinstance(r.get("pos"), int)]  # 실제 쓰는 필드만(hidden 은 위치가 흩어져 있다)
            controls = _controls(frame, form_key, (min(positions), max(positions)) if positions else None)
            has_password = any(f["type"] == "password" for f in fields)
            action_text = [*_form_actions(frame, form_key), urlparse(frame_url).path]
            risk = risk_of(controls + action_text)
            if has_password:
                risk, category = RISK_SUBMIT, CAT_LOGIN
            elif risk == RISK_SUBMIT:
                category = CAT_SUBMIT
            elif risk == RISK_WRITE:
                category = CAT_INPUT
            else:
                category = CAT_SEARCH
            control = _primary_control(controls)
            used_controls.update(controls)
            tid = f"{slug(path)}#{slug(form_key) if form_key else 'page'}"
            tasks.append(
                {
                    "id": tid,
                    "name": (title or path)[:80],
                    "category": category,
                    "purpose": "",
                    "risk": risk,
                    "auth": AUTH_LOGIN if has_password and auth == AUTH_PUBLIC else auth,
                    "state": STATE_OBSERVED,
                    "url": frame_url,
                    "host": host,
                    "fields": fields,
                    "control": control,
                    "outputs": [],
                    "steps": recorder_steps(frame_url, fields, risk=risk, control=control),
                    "fingerprint": fingerprint(fields),
                    "observed_at": now,
                    "verified_at": "",
                    "failures": 0,
                    "changes": [],
                    **_never_key(never_kind([*controls, *action_text, title, path], fields, risk=risk)),
                }
            )
        tasks.extend(_button_tasks(frame, frame_url, host, path, title, used_controls, auth=auth, now=now))
    return tasks


def _button_tasks(  # noqa: PLR0913 - 한 프레임의 버튼 업무를 만드는 데 필요한 값들(주소·제목·이미 쓰인 버튼·접근·시각)
    frame: dict[str, Any], frame_url: str, host: str, path: str, title: str, used: set[str], *, auth: str, now: str
) -> list[dict[str, Any]]:
    """입력창 업무에 쓰이지 않은 **버튼**을 버튼 업무로 기록한다(발행·조회·이체처럼 누르는 것이 곧 업무인 화면).

    위험 등급은 버튼 글자와 주소로 정하며(불확실하면 높게), 읽기가 아니면 클릭 단계를 만들지 않는다.
    """
    seen: set[str] = set()
    ranked: list[tuple[str, str]] = []
    for b in frame.get("buttons", []):
        raw = str(b.get("text") or b.get("aria") or "").strip()
        text = clean_label(str(b.get("text") or ""), str(b.get("aria") or ""))  # 표시·실행용 이름(첫 의미 있는 줄, 수치 제외, 40자)
        if not text or raw in used or text in used or text in seen or not b.get("visible", True):
            continue
        risk = risk_of([text, path])
        if risk == RISK_READ and is_global_landmark(b.get("landmark")):
            continue  # 사이트 공통 메뉴(banner·navigation·contentinfo)는 업무가 아니라 지도의 global_nav 로 한 번만 기록한다
        seen.add(text)
        ranked.append((risk, text))
    ranked.sort(key=lambda x: -_RISK_RANK[x[0]])  # 위험한 버튼부터 남긴다(상한이 있어도 놓치지 않게)
    tasks = []
    for risk, text in ranked[:_BUTTON_TASKS_MAX]:
        category = CAT_SUBMIT if risk == RISK_SUBMIT else CAT_INPUT if risk == RISK_WRITE else CAT_NAVIGATE
        digest = hashlib.sha1(text.encode("utf-8"), usedforsecurity=False).hexdigest()[:6]  # 이름 충돌 방지용, 보안 용도 아님(한글 버튼 이름은 slug 로 지워진다)
        tasks.append(
            {
                "id": f"{slug(path)}#btn_{digest}",
                "name": f"{text} ({title or path})"[:80],
                "category": category,
                "purpose": "",
                "risk": risk,
                "auth": auth,
                "state": STATE_OBSERVED,
                "url": frame_url,
                "host": host,
                "fields": [],
                "control": text,
                "outputs": [],
                "steps": recorder_steps(frame_url, [], risk=risk, control=text),
                "fingerprint": fingerprint([{"name": text, "type": "button"}]),
                "observed_at": now,
                "verified_at": "",
                "failures": 0,
                "changes": [],
                **_never_key(never_kind([text, path], [], risk=risk)),
            }
        )
    return tasks


def _never_key(kind: str) -> dict[str, str]:
    """`never` 가 있을 때만 키를 만든다(없는 업무의 저장 형식·구조 지문은 그대로)."""
    return {"never": kind} if kind else {}


def coverage_of(per_snapshot: list[tuple[dict[str, Any], list[dict[str, Any]]]]) -> dict[str, Any]:
    """탐색 점검표: 읽은 화면 수·편집 영역 수·버튼 업무 수·업무를 못 찾은 화면 수. 불완전하면 warning."""
    editable = unrecognized = 0
    total = 0
    buttons_only = 0
    for snap, found in per_snapshot:
        total += len(found)
        buttons_only += sum(1 for t in found if not t["fields"])
        frames = [f for f in snap.get("frames", []) if "error" not in f]
        editable += sum(1 for f in frames for i in f.get("inputs", []) if i.get("type") == "editable" and i.get("visible", True))
        has_controls = any(f.get("inputs") or f.get("buttons") for f in frames)
        if has_controls and not found:
            unrecognized += 1
    cov: dict[str, Any] = {"pages_read": len(per_snapshot), "tasks": total, "editable": editable, "buttons_only": buttons_only, "unrecognized": unrecognized}
    if per_snapshot and total == 0:
        cov["warning"] = "화면은 읽었지만 업무를 하나도 인식하지 못했습니다 — 탐색이 불완전하니 업무가 없다고 단정하지 말고 사용자에게 알리세요."
    elif unrecognized:
        cov["warning"] = f"읽은 화면 중 {unrecognized}쪽에서 업무를 인식하지 못했습니다 — 지도가 불완전할 수 있습니다."
    return cov


# ── 지도 ──────────────────────────────────────────────────────────────────


_AUTH_RANK = {AUTH_PUBLIC: 0, AUTH_LOGIN: 1, AUTH_CERT: 2}


def stronger_auth(current: str, observed: str) -> str:
    """사이트의 접근 구분은 더 엄격한 쪽으로만 올라간다(공개 → 로그인 → 인증서). 로그인한 세션으로 탐색하면 '공개'로 남지 않게 한다."""
    return observed if _AUTH_RANK.get(observed, 0) > _AUTH_RANK.get(current, 0) else current


def note_exploration(site_map: dict[str, Any], *, pages: int, auth: str, now: str, coverage: dict[str, Any] | None = None) -> dict[str, Any]:
    """탐색을 했다는 사실(시각·방문 쪽수)과 접근 구분, 점검표를 기록한다. 업무가 하나도 없어도 '탐색한 사이트'임이 남는다."""
    explored: dict[str, Any] = {"at": now, "pages": int(pages)}
    if coverage is not None:
        explored["coverage"] = coverage
    return dict(site_map, auth=stronger_auth(site_map.get("auth", AUTH_PUBLIC), auth), explored=explored, updated_at=now)


def empty_map(host: str, *, auth: str = AUTH_PUBLIC, now: str = "") -> dict[str, Any]:
    return {"version": SCHEMA_VERSION, "host": host, "auth": auth, "updated_at": now, "tasks": []}


def validate_map(data: Any) -> dict[str, Any]:
    """저장본 검증. 형식이 틀리면 ValueError (조용히 고쳐 쓰지 않는다)."""
    if not isinstance(data, dict) or data.get("version") != SCHEMA_VERSION:
        raise ValueError(f"사이트 지도 버전이 맞지 않습니다(필요 {SCHEMA_VERSION})")
    if not isinstance(data.get("host"), str) or not isinstance(data.get("tasks"), list):
        raise ValueError("사이트 지도 형식이 올바르지 않습니다")
    for t in data["tasks"]:
        if not isinstance(t, dict) or t.get("risk") not in RISKS or t.get("state") not in STATES or not t.get("id"):
            raise ValueError("사이트 지도의 업무 항목 형식이 올바르지 않습니다")
    return data


def merge_tasks(site_map: dict[str, Any], observed: list[dict[str, Any]], *, now: str) -> dict[str, Any]:
    """새로 관찰한 업무를 지도에 합친다(새 dict 반환).

    - 없던 업무: 추가(observed).
    - 구조(지문)가 같은 업무: 검증 상태·이력 유지, 관찰 시각만 갱신.
    - 구조가 바뀐 업무: 새 구조로 교체하고 검증은 잃는다(observed). 이전 지문은 changes 에 남긴다.
    - 사람이 정한 이름·목적·분류는 유지한다(자동 관찰이 덮어쓰지 않는다).
    """
    by_id = {t["id"]: dict(t) for t in site_map["tasks"]}
    for new in observed:
        old = by_id.get(new["id"])
        if old is None:
            by_id[new["id"]] = dict(new, observed_at=now)
            continue
        if old["fingerprint"] == new["fingerprint"]:
            kept = dict(old, observed_at=now, **_never_key(carry_never(old, new)))
            if _RISK_RANK[new["risk"]] > _RISK_RANK[old["risk"]]:  # 규칙이 강화돼 위험이 올라갔다 — 올리고 읽기용 클릭 단계는 뺀다(내리지는 않는다)
                kept.update(risk=new["risk"], steps=new["steps"], category=new["category"], state=STATE_OBSERVED)
            by_id[new["id"]] = kept
            continue
        change = {"at": now, "from": old["fingerprint"], "to": new["fingerprint"], "was": old["state"]}
        merged = dict(new, observed_at=now, changes=[*old.get("changes", []), change][-20:])
        for keep in ("name", "purpose", "category"):
            if old.get(keep):
                merged[keep] = old[keep]
        merged["risk"] = max_risk(old["risk"], new["risk"])  # 위험 등급은 내려가지 않는다
        merged.update(_never_key(carry_never(old, new)))  # never 표시도 자동 관찰로 지워지지 않는다
        by_id[new["id"]] = merged
    return dict(site_map, updated_at=now, tasks=sorted(by_id.values(), key=lambda t: t["id"]))


def _update(site_map: dict[str, Any], task_id: str, **changes: Any) -> dict[str, Any]:
    if not any(t["id"] == task_id for t in site_map["tasks"]):
        raise ValueError("업무를 찾을 수 없습니다")
    tasks = [dict(t, **changes) if t["id"] == task_id else t for t in site_map["tasks"]]
    return dict(site_map, tasks=tasks)


def mark_verified(site_map: dict[str, Any], task_id: str, *, now: str) -> dict[str, Any]:
    """실제로 한 번 성공했을 때. 실패 횟수는 0 으로."""
    return dict(_update(site_map, task_id, state=STATE_VERIFIED, verified_at=now, failures=0), updated_at=now)


def mark_failed(site_map: dict[str, Any], task_id: str, *, now: str) -> dict[str, Any]:
    """필드·주소가 지도와 달라 실패했을 때. 재탐색이 필요하다는 표시(stale)."""
    task = next((t for t in site_map["tasks"] if t["id"] == task_id), None)
    if task is None:
        raise ValueError("업무를 찾을 수 없습니다")
    return dict(_update(site_map, task_id, state=STATE_STALE, failures=int(task.get("failures", 0)) + 1), updated_at=now)


def set_classification(
    site_map: dict[str, Any], task_id: str, *, name: str | None = None, purpose: str | None = None, category: str | None = None
) -> dict[str, Any]:
    """사람이 이름·목적·분류를 확정한다. 위험 등급은 여기서 바꾸지 못한다(낮추기 금지)."""
    changes: dict[str, Any] = {}
    if name is not None:
        changes["name"] = name.strip()[:80]
    if purpose is not None:
        changes["purpose"] = purpose.strip()[:200]
    if category is not None:
        if category not in CATEGORIES:
            raise ValueError(f"분류는 {', '.join(CATEGORIES)} 중 하나여야 합니다")
        changes["category"] = category
    return _update(site_map, task_id, **changes)


def lookup(site_map: dict[str, Any], query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    """키워드로 업무 후보를 찾는다(이름·목적·주소·필드·라벨 일치 점수순). 키워드가 비면 전부."""
    words = [w for w in re.split(r"\s+", query.lower().strip()) if w]
    scored = []
    for t in site_map["tasks"]:
        hay = " ".join([t.get("name", ""), t.get("purpose", ""), t.get("url", ""), *(f"{f['name']} {f['label']}" for f in t.get("fields", []))]).lower()
        score = sum(1 for w in words if w in hay) if words else 1
        if score:
            scored.append((score, t))
    scored.sort(key=lambda s: (-s[0], s[1]["id"]))
    return [t for _, t in scored[:limit]]


# ── 탐색 요청 (승인 카드로만 시작) ────────────────────────────────────────────

EXPLORE_DEPTH_MAX = 4
EXPLORE_PAGES_MAX = 200
EXPLORE_DEFAULT_DEPTH = 2
EXPLORE_DEFAULT_PAGES = 20
EXPLORE_DEFAULT_DELAY_S = 1.0
_HOST_OK = re.compile(r"^[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?$")
# 탐색이 이동하지 않을 주소 조각(로그아웃·삭제·제출·결제 등). 클릭은 하지 않고 주소 이동(GET)만 하므로 URL 로 걸러낸다.
EXPLORE_SKIP_URL = ("logout", "signout", "logoff", "delete", "remove", "submit", "withdraw", "cancel", "payment", "pay.", "/pay/", "send")


def validate_explore_request(raw: dict[str, Any]) -> dict[str, Any]:
    """탐색 요청 정규화. 잘못되면 ValueError. 내부망·로컬 주소와 인증정보가 든 주소는 거부한다."""
    url = str(raw.get("start_url") or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("시작 주소는 http(s):// 로 시작하는 전체 주소여야 합니다")
    if parsed.username or parsed.password:
        raise ValueError("주소에 아이디·비밀번호를 넣을 수 없습니다")
    host = parsed.hostname.lower()
    if not _HOST_OK.match(host) or ".." in host:
        raise ValueError("호스트 이름이 올바르지 않습니다")
    if host == "localhost" or host.endswith((".local", ".internal", ".localhost")):
        raise ValueError("로컬·내부 주소는 탐색할 수 없습니다")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified):
        raise ValueError("로컬·내부 주소는 탐색할 수 없습니다")

    def _bounded(key: str, default: int, top: int) -> int:
        value = raw.get(key, default)
        try:
            number = int(value)
        except (TypeError, ValueError) as e:
            raise ValueError(f"{key} 는 정수여야 합니다") from e
        if not 1 <= number <= top:
            raise ValueError(f"{key} 는 1~{top} 사이여야 합니다")
        return number

    return {
        "host": host,
        "start_url": parsed._replace(fragment="").geturl(),
        "depth": _bounded("depth", EXPLORE_DEFAULT_DEPTH, EXPLORE_DEPTH_MAX),
        "max_pages": _bounded("max_pages", EXPLORE_DEFAULT_PAGES, EXPLORE_PAGES_MAX),
        "auth": raw.get("auth") if raw.get("auth") in AUTHS else AUTH_PUBLIC,
    }


# ── 지도 기반 실행 (M5): 매개변수 검증·결과 열 이름 반영 ──────────────────────

RUN_VALUE_MAX = 200
OUTPUT_COLUMNS_MAX = 30
_PLACEHOLDER = re.compile(r"\{\{([^{}]+)\}\}")


def step_placeholders(steps: list[dict[str, Any]]) -> list[str]:
    """steps 의 `{{이름}}` 매개변수 자리(등장 순서, 중복 제거)."""
    names: list[str] = []
    for step in steps:
        for name in _PLACEHOLDER.findall(str(step.get("value") or "")) + _PLACEHOLDER.findall(str(step.get("url") or "")):
            if name not in names:
                names.append(name)
    return names


def effective_risk(task: dict[str, Any]) -> str:
    """저장된 위험 등급과 **현재 규칙**으로 다시 판정한 등급 중 높은 쪽. 키워드 규칙이 나중에 늘어도 예전에 저장된 업무가 조용히 read 로 남지 않게 한다."""
    path = urlparse(str(task.get("url") or "")).path
    return max_risk(str(task.get("risk") or RISK_READ), risk_of([str(task.get("control") or ""), path]))


def with_effective_risk(site_map: dict[str, Any]) -> dict[str, Any]:
    """화면·조회 응답에 내보낼 때 업무마다 유효 위험 등급을 반영한 사본(저장본은 건드리지 않는다)."""
    return dict(site_map, tasks=[dict(t, risk=effective_risk(t), **_never_key(effective_never(dict(t, risk=effective_risk(t))))) for t in site_map["tasks"]])


def _require_dict(params: Any) -> None:
    if not isinstance(params, dict):
        raise ValueError("매개변수는 {이름: 값} 형태여야 합니다")


def _validate_open_page_request(task: dict[str, Any], params: dict[str, Any]) -> dict[str, str]:
    """주소 열기 업무: 값은 url 하나, 같은 호스트의 안전한 GET 주소만."""
    extra = sorted(set(params) - {"url"})
    if extra:
        raise ValueError("지도에 없는 매개변수: " + ", ".join(map(str, extra)) + " (사용 가능: url)")
    return {"url": validate_open_url(params.get("url"), str(task.get("host") or ""), risk_of=risk_of, skip_fragments=EXPLORE_SKIP_URL)}


def _require_runnable(task: dict[str, Any]) -> None:
    """AI 가 실행할 수 있는 업무인지: never(자동 실행 불가)가 먼저 막고, 그다음 read 가 아니면 막는다."""
    risk = effective_risk(task)
    never = effective_never(dict(task, risk=risk))
    if never:
        raise ValueError(f"자동 실행 불가 업무입니다(never:{never}) — 승인으로도 실행할 수 없고 사람이 사이트에서 직접 해야 합니다")
    if risk != RISK_READ:
        raise ValueError(f"조회(read) 업무만 실행할 수 있습니다(이 업무는 {RISK_LABEL_KO.get(risk, risk)}). 실행은 사람 승인 카드로만 합니다")


def validate_run_request(task: dict[str, Any], params: dict[str, Any]) -> dict[str, str]:
    """실행 요청 검증 → 문자열 매개변수. 규칙 위반은 ValueError.

    - 조회(read) 업무만 실행한다: 위험 등급은 클라이언트 표시를 믿지 않고 여기서(서버 쪽) 판정한다.
    - 지도에 없는 매개변수는 거부, 입력칸이 있는 업무는 적어도 하나는 있어야 한다, 필수 칸은 반드시 있어야 한다.
    - 값은 200자 이내 문자열, 제어문자 금지. 지도에 없는 칸을 채우거나 값을 지도에 남기지 않는다.
    """
    _require_runnable(task)
    _require_dict(params)
    if task.get("id") == OPEN_PAGE_ID:
        return _validate_open_page_request(task, params)
    wanted = step_placeholders(task.get("steps", []))
    unknown = sorted(set(params) - set(wanted))
    if unknown:
        raise ValueError("지도에 없는 매개변수: " + ", ".join(map(str, unknown)) + " (사용 가능: " + ", ".join(wanted) + ")")
    values: dict[str, str] = {}
    for name, value in params.items():
        text = "" if value is None else str(value)
        if len(text) > RUN_VALUE_MAX:
            raise ValueError(f"매개변수 '{name}' 은(는) {RUN_VALUE_MAX}자 이내여야 합니다")
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
            raise ValueError(f"매개변수 '{name}' 에 제어문자를 넣을 수 없습니다")
        if text.strip():
            values[str(name)] = text.strip()
    required = [f["name"] or f["id"] for f in task.get("fields", []) if f.get("required")]
    missing = [name for name in required if name in wanted and name not in values]
    if missing:
        raise ValueError("필수 매개변수가 없습니다: " + ", ".join(missing))
    if wanted and not values:
        raise ValueError("조회할 값이 없습니다 — 매개변수를 하나 이상 넣으세요(사용 가능: " + ", ".join(wanted) + ")")
    return values


RISK_LABEL_KO = {RISK_READ: "조회", RISK_WRITE: "입력·저장", RISK_SUBMIT: "제출·신고·삭제"}


def substitute(value: str, params: dict[str, str]) -> str | None:
    """`{{이름}}` 을 값으로 바꾼다. 값이 없는 자리가 있으면 None (그 단계는 건너뛴다)."""
    missing = False

    def repl(match: re.Match[str]) -> str:
        nonlocal missing
        if match.group(1) in params:
            return params[match.group(1)]
        missing = True
        return ""

    out = _PLACEHOLDER.sub(repl, value)
    return None if missing else out


def apply_outputs(site_map: dict[str, Any], task_id: str, headers: list[str], *, now: str) -> dict[str, Any]:
    """결과 표의 **열 이름**만 업무에 기록한다(구조 정보. 행 데이터는 저장하지 않는다)."""
    cleaned = [str(h).strip()[:40] for h in headers if str(h).strip()][:OUTPUT_COLUMNS_MAX]
    return dict(_update(site_map, task_id, outputs=cleaned), updated_at=now)

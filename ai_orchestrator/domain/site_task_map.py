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
import re
from typing import Any
from urllib.parse import urlparse

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
_SUBMIT_KO = ("제출", "신고", "통보", "결제", "송금", "이체", "삭제", "제거", "탈퇴", "서명", "전송", "발송", "발급", "승인", "확정", "취소", "로그아웃")
_SUBMIT_EN = ("submit", "delete", "remove", "pay", "send", "logout", "signout", "sign", "approve", "confirm", "withdraw", "cancel")
_WRITE_KO = ("저장", "수정", "등록", "추가", "변경", "업로드", "첨부", "신청", "작성")
_WRITE_EN = ("save", "update", "add", "edit", "upload", "create", "register", "apply", "insert")

_SKIP_INPUT_TYPES = {"hidden", "submit", "button", "image", "reset"}
_SHORT_ACTION_LINK = 12  # href 가 '#'·javascript: 인 링크는 동작 버튼으로 본다(글자 수 제한)


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
    if _hits(joined, _SUBMIT_KO, _SUBMIT_EN):
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
    return hashlib.sha1("|".join(names).encode("utf-8")).hexdigest()[:12]  # noqa: S324 - 변경 감지용 지문, 보안 용도 아님


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


def _controls(frame: dict[str, Any]) -> list[str]:
    """동작 컨트롤 이름: 버튼 + href 가 '#'·javascript: 인 짧은 링크."""
    names = [str(b.get("text") or b.get("aria") or "") for b in frame.get("buttons", [])]
    for link in frame.get("links", []):
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


def _group_inputs(frame: dict[str, Any]) -> list[tuple[str, list[dict[str, Any]]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for raw in frame.get("inputs", []):
        groups.setdefault(str(raw.get("form") or ""), []).append(raw)
    return list(groups.items())


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
        controls = _controls(frame)
        for form_key, raws in _group_inputs(frame):
            fields = _dedupe_fields([f for f in (_field(r) for r in raws) if f])
            if not fields:
                continue
            has_password = any(f["type"] == "password" for f in fields)
            action_text = [urlparse(frm.get("action") or "").path for frm in frame.get("forms", [])] + [urlparse(frame_url).path]
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
                }
            )
    return tasks


# ── 지도 ──────────────────────────────────────────────────────────────────


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
            by_id[new["id"]] = dict(old, observed_at=now)
            continue
        change = {"at": now, "from": old["fingerprint"], "to": new["fingerprint"], "was": old["state"]}
        merged = dict(new, observed_at=now, changes=[*old.get("changes", []), change][-20:])
        for keep in ("name", "purpose", "category"):
            if old.get(keep):
                merged[keep] = old[keep]
        merged["risk"] = max_risk(old["risk"], new["risk"])  # 위험 등급은 내려가지 않는다
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

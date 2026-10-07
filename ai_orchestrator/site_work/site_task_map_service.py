"""L6 Business Workflows — 사이트 업무 지도 조회·확정 (HTTP/DB 모름, 규칙은 domain, 저장은 persistence).

기준서: docs/specs/2026-10-03_site_task_map.md (M2)

- 에이전트(AI)가 쓰는 것은 `list_hosts`·`lookup`(읽기)과 `run_task`(조회 업무 실행 — 위험 등급은 서버가 강제)뿐이다. `classify`·`record_outcome` 은 사람(관리자 화면)만 호출한다.
- `lookup` 응답에는 실행 규칙을 함께 실어, 지도의 절차를 읽은 에이전트가 위험 등급을 넘어 실행하지 않게 한다.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from . import site_map_history as hist
from . import site_map_sources as sources
from . import site_task_map as tm
from . import site_task_map_store as store
from .site_map_menu import OPEN_PAGE_ID

LOOKUP_LIMIT_MAX = 20

RULES = (
    "risk 가 read 인 업무는 sitemap.run(task_id, params)으로 실행한다(직접 절차를 흉내 내지 말 것). write·submit 은 절차를 참고만 하고 실행은 사람 승인 카드로만 한다. "
    "state 가 stale 이거나 observed 인 업무는 화면이 지도와 다를 수 있으니 첫 화면에서 fields 가 맞는지 먼저 확인하고, 다르면 중단해 사용자에게 알린다. "
    "steps 의 {{이름}} 은 값을 넣을 자리다. 입력값·조회 결과 데이터는 지도에 저장하지 않는다. "
    "menu 가 있으면 사이트의 메뉴(카테고리·게시판 등) 색인이다: 라벨에 맞는 href 를 골라 open_page_task_id 업무를 sitemap.run(task_id, {url: href}) 로 실행하면 같은 호스트의 그 화면을 읽기 전용으로 열어 "
    "표 또는 items(상품·목록 항목)와 next_url(다음 쪽)을 돌려준다. 메뉴에 없는 주소를 지어내지 말 것. "
    "data_sources 는 화면이 로드될 때 사이트가 부르는 데이터 API 의 구조(경로·목록 경로·필드 이름·건수)다 — 이 사이트가 무엇을 다루는지 아는 근거이며 값은 없다. "
    "declared_tools 는 사이트가 스스로 선언한 에이전트용 도구(WebMCP) 목록이다 — 읽기만 한다(실행하지 말 것)."
)
MENU_SHOWN_MAX = 30


# 지도 기반 실행기(브라우저): (호스트, 업무 id, 검증된 매개변수) -> 결과 dict. 라우터가 주입한다(서비스는 브라우저·scripts 를 모른다).
Runner = Callable[[str, str, dict[str, str]], dict[str, Any]]
_runner_ref: list[Runner | None] = [None]  # 한 칸짜리 보관소 — `global` 로 다시 대입하지 않는다


def configure_runner(runner: Runner | None) -> None:
    _runner_ref[0] = runner


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _summary(site_map: dict[str, Any]) -> dict[str, Any]:
    states = [t["state"] for t in site_map["tasks"]]
    return {
        "host": site_map["host"],
        "auth": site_map["auth"],
        "tasks": len(states),
        "verified": states.count(tm.STATE_VERIFIED),
        "stale": states.count(tm.STATE_STALE),
        "updated_at": site_map["updated_at"],
    }


def list_hosts() -> list[dict[str, Any]]:
    """저장된 사이트 지도 요약. 깨진 파일 하나가 목록 전체를 막지 않게 그 항목만 오류로 표시한다."""
    out = []
    for host in store.list_hosts():
        try:
            site_map = store.load(host)
            if not site_map["tasks"] and not site_map.get("explored"):  # 탐색 기록도 업무도 없는 빈 파일은 '탐색한 사이트'가 아니다(상세가 404 가 되는 불일치 방지)
                continue
            out.append(_summary(site_map))
        except ValueError as e:
            out.append({"host": host, "error": str(e)})
    return out


def get_map(host: str) -> dict[str, Any]:
    site_map = store.load(host)
    if not site_map["tasks"] and not site_map.get("explored"):  # 탐색했지만 업무가 없는 사이트는 지도를 그대로 보여준다(경고·점검표 포함)
        raise ValueError("이 사이트의 지도가 없습니다")
    return tm.with_effective_risk(site_map)


def _menu_view(site_map: dict[str, Any], query: str) -> dict[str, Any]:
    """조회 응답에 더하는 메뉴 색인: 키워드가 라벨·주소에 맞는 항목을 먼저(없으면 앞에서부터) 최대 MENU_SHOWN_MAX 개 + 주소 열기 업무 id."""
    entries = list(site_map["menu"])
    words = [w for w in query.lower().split() if w]
    is_hit = [bool(words) and any(w in f"{e['label']} {e['href']}".lower() for w in words) for e in entries]
    shown = ([e for e, hit in zip(entries, is_hit, strict=True) if hit] + [e for e, hit in zip(entries, is_hit, strict=True) if not hit])[:MENU_SHOWN_MAX]
    seen = max(int(site_map.get("menu_total_seen") or 0), len(entries))
    return {"menu": shown, "menu_total": len(entries), "menu_total_seen": seen, "menu_truncated": seen > len(entries), "open_page_task_id": OPEN_PAGE_ID}


def lookup(host: str, query: str = "", *, limit: int = 5) -> dict[str, Any]:
    """키워드로 업무 후보를 찾는다. 지도가 없으면 known=False 로 알려 탐색이 필요함을 전한다(오류로 만들지 않는다)."""
    limit = max(1, min(int(limit), LOOKUP_LIMIT_MAX))
    site_map = store.load(host)
    if not site_map["tasks"]:
        explored = site_map.get("explored")
        if explored:  # 탐색은 했지만 입력창이 있는 조회 업무를 찾지 못한 사이트 — '미탐색'으로 오해해 같은 탐색을 되풀이하지 않게 한다
            hint = f"이 사이트는 {str(explored.get('at', ''))[:10]} 에 {explored.get('pages', 0)}쪽을 탐색했지만 입력창이 있는 조회 업무를 찾지 못했습니다. 같은 탐색을 되풀이하지 말고 사용자에게 알리세요."
            warning = (explored.get("coverage") or {}).get("warning")
            if warning:
                hint = f"{hint} 주의: {warning}"
            observed = sources.summary(site_map)
            if observed.get("data_sources"):  # 업무는 못 찾았지만 화면이 부르는 데이터 API 구조는 관측했다 — 빈 사이트로 오해하지 않게 알린다
                hint = f"{hint} 다만 데이터 소스 {observed['data_sources_total']}개를 관측했습니다(data_sources) — 이 사이트는 화면을 자바스크립트로 그려 폼·링크 업무가 안 잡힌 것일 수 있습니다."
            return {"host": site_map["host"], "known": False, "explored": True, "count": 0, "tasks": [], "rules": RULES, "hint": hint, **observed}
        return {"host": site_map["host"], "known": False, "count": 0, "tasks": [], "rules": RULES, "hint": "이 사이트는 아직 탐색된 적이 없습니다. 사용자에게 탐색을 요청하세요."}
    found = tm.lookup(tm.with_effective_risk(site_map), query, limit=limit)
    out = {
        "host": site_map["host"],
        "known": True,
        "auth": site_map["auth"],
        "count": len(found),
        "total": len(site_map["tasks"]),
        "tasks": found,
        "rules": RULES,
        "map_rev": int(site_map.get("map_rev") or 0),  # 이 지도의 버전 — 실행·재호출 때 map_rev 로 고정해 지도가 바뀌었는지 확인한다
        "map_fingerprint": str(site_map.get("map_fingerprint") or ""),
    }
    if site_map.get("menu"):
        out.update(_menu_view(site_map, query))
    out.update(sources.summary(site_map))  # 데이터 소스 요약·선언 도구(있을 때만 키가 생긴다)
    warning = ((site_map.get("explored") or {}).get("coverage") or {}).get("warning")
    if warning:  # 탐색이 불완전했다 — AI 가 업무가 없다고 단정하지 않고 사용자에게 알리게 한다
        out["warning"] = warning
    return out


def classify(host: str, task_id: str, *, name: str | None = None, purpose: str | None = None, category: str | None = None) -> dict[str, Any]:
    """사람이 업무 이름·목적·분류를 확정한다(위험 등급은 바꾸지 못한다)."""
    site_map = store.load(host)
    updated = tm.set_classification(site_map, task_id, name=name, purpose=purpose, category=category)
    store.save(dict(updated, updated_at=_now()))
    return next(t for t in updated["tasks"] if t["id"] == task_id)


def record_outcome(host: str, task_id: str, *, ok: bool) -> dict[str, Any]:
    """실행 결과 기록: 성공이면 verified, 지도와 달라 실패면 stale."""
    site_map = store.load(host)
    now = _now()
    updated = tm.mark_verified(site_map, task_id, now=now) if ok else tm.mark_failed(site_map, task_id, now=now)
    store.save(updated)
    return next(t for t in updated["tasks"] if t["id"] == task_id)


def _pinned_fingerprint(host: str, rev: int | None) -> str:
    """고정하려는 버전의 지문(보존돼 있으면). 없으면 빈 문자열 — 번호가 다르면 '바뀜'으로 본다."""
    if rev is None:
        return ""
    try:
        return str(store.history_load(host, rev).get("fingerprint") or "")
    except ValueError:
        return ""


def history(host: str) -> dict[str, Any]:
    """보존 중인 지도 버전 목록(최신 순)과 현재 버전."""
    site_map = store.load(host)
    return {"host": site_map["host"], "map_rev": int(site_map.get("map_rev") or 0), "map_fingerprint": str(site_map.get("map_fingerprint") or ""), "revisions": store.history_list(host)}


def diff(host: str, rev_from: int, rev_to: int | None = None) -> dict[str, Any]:
    """두 지도 버전의 차이(`rev_to` 를 생략하면 현재 버전과 비교). 값 없이 구조(업무·메뉴·데이터 소스)만 비교한다."""
    current = store.load(host)
    target = int(rev_to) if rev_to is not None else int(current.get("map_rev") or 0)
    if target <= 0:
        raise ValueError("비교할 지도 버전을 찾을 수 없습니다")
    old, new = store.history_load(host, rev_from), store.history_load(host, target)
    return {"host": current["host"], "from": int(rev_from), "to": target, **hist.diff(old["structure"], new["structure"])}


def run_task(host: str, task_id: str, params: dict[str, Any], *, map_rev: int | None = None) -> dict[str, Any]:
    """지도에 저장된 **조회(read)** 업무를 실행한다. 위험 등급·매개변수는 여기서(서버 쪽) 먼저 검증하고, 브라우저는 주입된 실행기가 다룬다.

    결과(표)는 응답으로만 돌려주고 지도에는 열 이름과 검증 상태만 남는다.
    """
    runner = _runner_ref[0]
    if runner is None:
        raise ValueError("지도 실행기가 연결되지 않았습니다")
    site_map = store.load(host)
    changed = hist.pin_check(map_rev, int(site_map.get("map_rev") or 0), str(site_map.get("map_fingerprint") or ""), _pinned_fingerprint(host, map_rev))
    if changed is not None:  # 기준 지도 버전이 바뀌었다 — 브라우저를 건드리기 전에 사람에게 되돌려 묻는다
        return changed
    task = next((t for t in site_map["tasks"] if t["id"] == task_id), None)
    if task is None:
        raise ValueError("업무를 찾을 수 없습니다")
    values = tm.validate_run_request(task, params)  # read 가 아니거나 매개변수가 틀리면 ValueError (브라우저를 건드리기 전)
    return runner(site_map["host"], task_id, values)

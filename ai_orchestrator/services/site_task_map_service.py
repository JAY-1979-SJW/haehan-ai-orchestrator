"""L6 Business Workflows — 사이트 업무 지도 조회·확정 (HTTP/DB 모름, 규칙은 domain, 저장은 persistence).

기준서: docs/specs/2026-10-03_site_task_map.md (M2)

- 에이전트(AI)가 쓰는 것은 `list_hosts`·`lookup`(읽기)과 `run_task`(조회 업무 실행 — 위험 등급은 서버가 강제)뿐이다. `classify`·`record_outcome` 은 사람(관리자 화면)만 호출한다.
- `lookup` 응답에는 실행 규칙을 함께 실어, 지도의 절차를 읽은 에이전트가 위험 등급을 넘어 실행하지 않게 한다.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from ..domain import site_task_map as tm
from ..persistence import site_task_map_store as store

LOOKUP_LIMIT_MAX = 20

RULES = (
    "risk 가 read 인 업무는 sitemap.run(task_id, params)으로 실행한다(직접 절차를 흉내 내지 말 것). write·submit 은 절차를 참고만 하고 실행은 사람 승인 카드로만 한다. "
    "state 가 stale 이거나 observed 인 업무는 화면이 지도와 다를 수 있으니 첫 화면에서 fields 가 맞는지 먼저 확인하고, 다르면 중단해 사용자에게 알린다. "
    "steps 의 {{이름}} 은 값을 넣을 자리다. 입력값·조회 결과 데이터는 지도에 저장하지 않는다."
)


# 지도 기반 실행기(브라우저): (호스트, 업무 id, 검증된 매개변수) -> 결과 dict. 라우터가 주입한다(서비스는 브라우저·scripts 를 모른다).
Runner = Callable[[str, str, dict[str, str]], dict[str, Any]]
_runner: Runner | None = None


def configure_runner(runner: Runner | None) -> None:
    global _runner
    _runner = runner


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
            out.append(_summary(store.load(host)))
        except ValueError as e:
            out.append({"host": host, "error": str(e)})
    return out


def get_map(host: str) -> dict[str, Any]:
    site_map = store.load(host)
    if not site_map["tasks"]:
        raise ValueError("이 사이트의 지도가 없습니다")
    return site_map


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
            return {"host": site_map["host"], "known": False, "explored": True, "count": 0, "tasks": [], "rules": RULES, "hint": hint}
        return {"host": site_map["host"], "known": False, "count": 0, "tasks": [], "rules": RULES, "hint": "이 사이트는 아직 탐색된 적이 없습니다. 사용자에게 탐색을 요청하세요."}
    found = tm.lookup(site_map, query, limit=limit)
    out = {
        "host": site_map["host"],
        "known": True,
        "auth": site_map["auth"],
        "count": len(found),
        "total": len(site_map["tasks"]),
        "tasks": found,
        "rules": RULES,
    }
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


def run_task(host: str, task_id: str, params: dict[str, Any]) -> dict[str, Any]:
    """지도에 저장된 **조회(read)** 업무를 실행한다. 위험 등급·매개변수는 여기서(서버 쪽) 먼저 검증하고, 브라우저는 주입된 실행기가 다룬다.

    결과(표)는 응답으로만 돌려주고 지도에는 열 이름과 검증 상태만 남는다.
    """
    if _runner is None:
        raise ValueError("지도 실행기가 연결되지 않았습니다")
    site_map = store.load(host)
    task = next((t for t in site_map["tasks"] if t["id"] == task_id), None)
    if task is None:
        raise ValueError("업무를 찾을 수 없습니다")
    values = tm.validate_run_request(task, params)  # read 가 아니거나 매개변수가 틀리면 ValueError (브라우저를 건드리기 전)
    return _runner(site_map["host"], task_id, values)

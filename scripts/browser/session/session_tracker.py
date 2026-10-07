"""세션 상태 추적 — 도메인별 로그인 상태 인메모리 캐시.

사용:
    from scripts.browser.session.session_tracker import is_logged_in, mark_state
    mark_state("naver.com", {"logged_in": True, "user": "skyjwsin"})
    if is_logged_in("naver.com"):
        ...
"""

from __future__ import annotations

from typing import Any

_STATE: dict[str, dict] = {}


def mark_state(domain: str, state: dict[str, Any]) -> dict[str, bool]:
    """도메인 세션 상태 업데이트 + 로그인 상태 변화 판정.

    반환: {"changed": 변화 여부, "new_logged_in": 새 로그인 상태}.
    변화 = 이전 관찰이 있으면 logged_in 이 달라진 경우, 첫 관찰이면 로그인 상태인 경우
    (page_helper_common 의 AUTH_SUCCESS/AUTH_FAIL 감사 로그가 사용).
    """
    previous = _STATE.get(domain)
    _STATE[domain] = dict(state)
    new_logged_in = bool(state.get("logged_in"))
    if previous is None:
        changed = new_logged_in
    else:
        changed = bool(previous.get("logged_in")) != new_logged_in
    return {"changed": changed, "new_logged_in": new_logged_in}


def is_logged_in(domain: str) -> bool:
    """도메인 로그인 여부 (캐시 기반)."""
    return bool(_STATE.get(domain, {}).get("logged_in"))


def get_state(domain: str) -> dict:
    """도메인 전체 세션 상태."""
    return dict(_STATE.get(domain, {}))



"""세션 상태 추적 — 도메인별 로그인 상태 인메모리 캐시.

사용:
    from scripts.session_tracker import is_logged_in, mark_state
    mark_state("naver.com", {"logged_in": True, "user": "skyjwsin"})
    if is_logged_in("naver.com"):
        ...
"""

from __future__ import annotations

from typing import Any

_STATE: dict[str, dict] = {}


def mark_state(domain: str, state: dict[str, Any]) -> None:
    """도메인 세션 상태 업데이트."""
    _STATE[domain] = dict(state)


def is_logged_in(domain: str) -> bool:
    """도메인 로그인 여부 (캐시 기반)."""
    return bool(_STATE.get(domain, {}).get("logged_in"))


def get_state(domain: str) -> dict:
    """도메인 전체 세션 상태."""
    return dict(_STATE.get(domain, {}))


def clear_state(domain: str) -> None:
    """도메인 세션 상태 초기화."""
    _STATE.pop(domain, None)


def all_states() -> dict[str, dict]:
    """전체 도메인 세션 상태 스냅샷."""
    return dict(_STATE)

"""session_tracker.mark_state 의 상태 변화 판정 — page_helper_common 의 로그인 감사 로그가 쓰는 계약.

정의: 이전 관찰이 있으면 logged_in 이 달라졌을 때만 changed, 이전 관찰이 없으면(첫 관찰) 로그인 상태일 때만 changed.
"""

from __future__ import annotations

import pytest

from scripts.browser.session import session_tracker


@pytest.fixture(autouse=True)
def _clean_state():
    session_tracker._STATE.clear()
    yield
    session_tracker._STATE.clear()


def test_first_observation_logged_in_is_change():
    change = session_tracker.mark_state("example.test", {"logged_in": True})
    assert change == {"changed": True, "new_logged_in": True}


def test_first_observation_logged_out_is_not_change():
    change = session_tracker.mark_state("example.test", {"logged_in": False})
    assert change["changed"] is False
    assert change["new_logged_in"] is False


def test_logged_out_to_in_is_change():
    session_tracker.mark_state("example.test", {"logged_in": False})
    change = session_tracker.mark_state("example.test", {"logged_in": True})
    assert change == {"changed": True, "new_logged_in": True}


def test_logged_in_to_out_is_change():
    session_tracker.mark_state("example.test", {"logged_in": True})
    change = session_tracker.mark_state("example.test", {"logged_in": False})
    assert change == {"changed": True, "new_logged_in": False}


def test_same_state_is_not_change():
    session_tracker.mark_state("example.test", {"logged_in": True})
    change = session_tracker.mark_state("example.test", {"logged_in": True, "user": "someone"})
    assert change["changed"] is False


def test_state_is_still_stored():
    session_tracker.mark_state("example.test", {"logged_in": True, "user": "someone"})
    assert session_tracker.is_logged_in("example.test") is True
    assert session_tracker.get_state("example.test")["user"] == "someone"

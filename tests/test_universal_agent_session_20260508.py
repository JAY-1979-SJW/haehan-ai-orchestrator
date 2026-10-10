"""tests/test_universal_agent_session_20260508.py"""
import pytest

from core.agent_runtime.runtime.universal.natural_language_task_api import check_result_safety
from core.agent_runtime.runtime.universal.universal_agent_session import (
    clear_all_sessions,
    close_session,
    create_session,
    get_session,
    get_session_history,
    grant_session_permission,
    revoke_session_permission,
    run_task_in_session,
)

_SAFE_FIELDS = [
    "cookie_exported", "session_exported", "password_collected",
    "otp_collected", "certificate_password_collected",
    "storage_state_exported", "server_browser_used",
]

_PAGE = {
    "url": "https://example.com/notice",
    "title": "공지사항",
    "text_content": "공지사항 | 목록 | 검색",
    "buttons": ["검색"],
    "links": ["notice1.html", "notice2.html"],
    "form_labels": [],
    "heading_texts": ["공지사항"],
}


def _dummy(action, domain="", **kwargs):
    return {"ok": True, "action": action}


@pytest.fixture(autouse=True)
def _clear():
    clear_all_sessions()
    yield
    clear_all_sessions()


def test_create_session_returns_session_dict():
    s = create_session(host="example.com", user_id="u1")
    assert "session_id" in s
    assert s["host"] == "example.com"
    assert s["user_id"] == "u1"
    assert isinstance(s["task_history"], list)


def test_get_session_returns_copy():
    s = create_session(host="example.com")
    sid = s["session_id"]
    s2 = get_session(sid)
    assert s2 is not None
    assert s2["session_id"] == sid


def test_get_session_unknown_returns_none():
    assert get_session("nonexistent-id") is None


def test_run_task_safe_fields():
    s = create_session(host="example.com")
    sid = s["session_id"]
    r = run_task_in_session(sid, "공지사항 읽어줘", page_data=_PAGE,
                            runner_fn=_dummy, dry_run=True)
    violations = check_result_safety(r)
    assert not violations, f"safe field 위반: {violations}"


def test_run_task_server_browser_used_false():
    s = create_session(host="example.com")
    sid = s["session_id"]
    r = run_task_in_session(sid, "페이지 읽어줘", page_data=_PAGE,
                            runner_fn=_dummy, dry_run=True)
    assert r.get("server_browser_used") is False


def test_run_task_updates_history():
    s = create_session(host="example.com")
    sid = s["session_id"]
    run_task_in_session(sid, "공지 찾아줘", page_data=_PAGE,
                        runner_fn=_dummy, dry_run=True)
    run_task_in_session(sid, "내용 요약해줘", page_data=_PAGE,
                        runner_fn=_dummy, dry_run=True)
    history = get_session_history(sid)
    assert len(history) == 2


def test_get_session_history_entries_have_fields():
    s = create_session(host="example.com")
    sid = s["session_id"]
    run_task_in_session(sid, "공지 읽어줘", page_data=_PAGE,
                        runner_fn=_dummy, dry_run=True)
    history = get_session_history(sid)
    entry = history[0]
    assert "task_id" in entry
    assert "instruction" in entry
    assert "status" in entry
    assert "executed_at" in entry


def test_run_task_unknown_session_returns_failed():
    r = run_task_in_session("bad-session-id", "공지 읽어줘", page_data=_PAGE)
    assert r["status"] == "FAILED"


def test_grant_session_permission():
    s = create_session(host="example.com")
    sid = s["session_id"]
    result = grant_session_permission(sid, "publish_post", "example.com")
    assert result is not None
    assert "permission_id" in result
    assert result["action"] == "publish_post"


def test_revoke_session_permission():
    s = create_session(host="example.com")
    sid = s["session_id"]
    grant = grant_session_permission(sid, "write_comment", "example.com")
    perm_id = grant["permission_id"]
    ok = revoke_session_permission(sid, perm_id)
    assert ok is True


def test_close_session_removes_it():
    s = create_session(host="example.com")
    sid = s["session_id"]
    ok = close_session(sid)
    assert ok is True
    assert get_session(sid) is None


def test_close_session_unknown_returns_false():
    assert close_session("nonexistent") is False


def test_multiple_sessions_independent():
    s1 = create_session(host="a.com")
    s2 = create_session(host="b.com")
    run_task_in_session(s1["session_id"], "공지 읽어줘", page_data=_PAGE,
                        runner_fn=_dummy, dry_run=True)
    assert len(get_session_history(s1["session_id"])) == 1
    assert len(get_session_history(s2["session_id"])) == 0


def test_all_safe_fields_false_in_failed_session():
    r = run_task_in_session("invalid", "공지 읽어줘", page_data=_PAGE)
    for f in _SAFE_FIELDS:
        assert r.get(f) is False, f"{f} != False"

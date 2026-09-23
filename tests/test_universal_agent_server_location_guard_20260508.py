"""tests/test_universal_agent_server_location_guard_20260508.py"""

import pytest

from ai_orchestrator.server.execution_location_guard import (
    LOCAL_AGENT_REQUIRED,
    SERVER_INTERNAL_ONLY,
)
from ai_orchestrator.server.universal_agent_models import (
    build_task_from_input,
    validate_task_model,
)
from ai_orchestrator.server.universal_agent_task_api import (
    clear_all,
    create_task,
    get_task,
    list_pending_local_agent_tasks,
    reject_server_external_fetch,
    update_task_result,
)

_SAFE_FIELDS = [
    "cookie_exported",
    "session_exported",
    "password_collected",
    "otp_collected",
    "certificate_password_collected",
    "storage_state_exported",
    "server_browser_used",
]


@pytest.fixture(autouse=True)
def _clear():
    clear_all()
    yield
    clear_all()


def _assert_safe(r):
    for f in _SAFE_FIELDS:
        assert r.get(f) is False


def test_create_task_external_url_local_agent():
    r = create_task(action="open_url", target_url="https://naver.com/")
    assert r["execution_location"] == LOCAL_AGENT_REQUIRED
    assert r["status"] == "WAITING_LOCAL_AGENT"
    assert r["local_agent_required"] is True
    assert "local_agent_handoff" in r
    _assert_safe(r)


def test_create_task_internal_url_server_internal():
    r = create_task(action="health_check", target_url="http://localhost:8000/health")
    assert r["execution_location"] == SERVER_INTERNAL_ONLY
    assert r["local_agent_required"] is False


def test_create_task_no_url_server_internal():
    r = create_task(action="status_check")
    assert r["execution_location"] == SERVER_INTERNAL_ONLY


def test_validate_external_with_server_browser_used_true_rejected():
    r = validate_task_model(
        {
            "target_url": "https://naver.com/",
            "execution_location": SERVER_INTERNAL_ONLY,
            "server_browser_used": True,
        }
    )
    assert r["valid"] is False


def test_validate_external_local_agent_passes():
    r = validate_task_model(
        {
            "target_url": "https://naver.com/",
            "execution_location": LOCAL_AGENT_REQUIRED,
            "server_browser_used": False,
        }
    )
    assert r["valid"] is True


def test_validate_external_server_internal_rejected():
    r = validate_task_model(
        {
            "target_url": "https://naver.com/",
            "execution_location": SERVER_INTERNAL_ONLY,
        }
    )
    assert r["valid"] is False


def test_get_task():
    created = create_task(action="open_url", target_url="https://example.com/")
    fetched = get_task(created["task_id"])
    assert fetched is not None
    assert fetched["task_id"] == created["task_id"]


def test_update_task_result_safe():
    created = create_task(action="open_url", target_url="https://example.com/")
    ok = update_task_result(created["task_id"], "COMPLETED", {"data": "ok"})
    assert ok is True


def test_update_task_rejects_server_browser_used_true():
    created = create_task(action="open_url", target_url="https://example.com/")
    ok = update_task_result(
        created["task_id"],
        "COMPLETED",
        {"data": "ok", "server_browser_used": True},
    )
    assert ok is False


def test_list_pending_local_agent_tasks():
    create_task(action="open_url", target_url="https://naver.com/")
    create_task(action="health_check", target_url="http://localhost/health")
    pending = list_pending_local_agent_tasks()
    assert len(pending) == 1
    assert pending[0]["execution_location"] == LOCAL_AGENT_REQUIRED


def test_reject_server_external_fetch_blocked():
    r = reject_server_external_fetch("https://naver.com/", purpose="title_preview")
    assert r["ok"] is False
    assert r["status"] == "BLOCKED"
    _assert_safe(r)


def test_reject_internal_fetch_passes():
    r = reject_server_external_fetch("http://localhost/health")
    assert r["ok"] is True
    assert r["blocked"] is False


def test_handoff_payload_no_sensitive_data():
    r = create_task(action="open_url", target_url="https://kbstar.com/")
    handoff = r["local_agent_handoff"]
    _assert_safe(handoff)
    # cookie/session/password 키 없음
    forbidden = ("password", "otp", "cookie_value", "session_value", "token")
    for key in handoff:
        for f in forbidden:
            assert f not in key.lower() or handoff[key] is False


def test_build_task_from_input_external():
    t = build_task_from_input("t1", "open_url", target_url="https://gov.kr/")
    assert t.execution_location == LOCAL_AGENT_REQUIRED
    assert t.local_agent_required is True
    assert t.server_browser_used is False

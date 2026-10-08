"""tests/app_contracts/test_server_side_external_web_execution_guard_20260508.py"""

import pytest

from ai_orchestrator.server.execution_location_guard import (
    BLOCKED_SERVER_BROWSER_LAUNCH,
    LOCAL_AGENT_REQUIRED,
    SERVER_INTERNAL_ONLY,
    USER_DIRECT_REQUIRED,
    assert_server_may_not_execute_external_web,
    build_local_agent_handoff,
    classify_execution_location_for_server,
    require_local_agent_for_external_url,
    validate_task_execution_location,
)
from ai_orchestrator.server.external_url_blocker import (
    block_external_fetch_from_server,
    guard_server_browser_action,
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


def _assert_safe(r):
    for f in _SAFE_FIELDS:
        assert r.get(f) is False, f"{f} != False"


def test_localhost_is_server_internal():
    r = classify_execution_location_for_server({"target_url": "http://localhost:8000/health"})
    assert r["execution_location"] == SERVER_INTERNAL_ONLY


def test_127_is_server_internal():
    r = classify_execution_location_for_server({"target_url": "http://127.0.0.1:3000/api"})
    assert r["execution_location"] == SERVER_INTERNAL_ONLY


def test_internal_docker_service_allowed():
    r = classify_execution_location_for_server({"target_url": "http://haehan-ai-orchestrator-api:8400/api/v1/health"})
    assert r["execution_location"] == SERVER_INTERNAL_ONLY


def test_naver_is_local_agent_required():
    r = classify_execution_location_for_server(
        {
            "target_url": "https://naver.com",
            "action": "open_url",
        }
    )
    assert r["execution_location"] == LOCAL_AGENT_REQUIRED


def test_g2b_is_local_agent_required():
    r = classify_execution_location_for_server(
        {
            "target_url": "https://www.g2b.go.kr/",
            "action": "read_page",
        }
    )
    assert r["execution_location"] == LOCAL_AGENT_REQUIRED


def test_gov_kr_is_local_agent_required():
    r = classify_execution_location_for_server(
        {
            "target_url": "https://www.gov.kr/portal",
            "action": "extract_text",
        }
    )
    assert r["execution_location"] == LOCAL_AGENT_REQUIRED


def test_external_read_page_blocked_on_server():
    r = guard_server_browser_action("read_page", "https://kbstar.com/")
    assert r["ok"] is False
    assert r["status"] == "BLOCKED"
    _assert_safe(r)


def test_external_download_blocked_on_server():
    r = guard_server_browser_action("download_file", "https://example.com/file.exe")
    assert r["ok"] is False
    assert r["blocked_reason"] == BLOCKED_SERVER_BROWSER_LAUNCH


def test_external_screenshot_blocked_on_server():
    r = guard_server_browser_action("screenshot", "https://wooribank.com/")
    assert r["ok"] is False


def test_external_selector_discovery_blocked_on_server():
    r = guard_server_browser_action("selector_discovery", "https://hometax.go.kr/")
    assert r["ok"] is False
    assert r["blocked"] is True


def test_internal_url_not_blocked():
    r = guard_server_browser_action("read_page", "http://localhost:3000/api")
    assert r["ok"] is True
    assert r["blocked"] is False


def test_assert_raises_for_external():
    with pytest.raises(ValueError):
        assert_server_may_not_execute_external_web(
            {
                "target_url": "https://naver.com",
                "action": "open_url",
            }
        )


def test_assert_passes_for_internal():
    # internal URL은 raise 안 함
    assert_server_may_not_execute_external_web(
        {
            "target_url": "http://localhost/health",
            "action": "open_url",
        }
    )


def test_require_local_agent_external_returns_true():
    r = require_local_agent_for_external_url("https://gov.kr/")
    assert r["requires_local_agent"] is True
    assert r["execution_location"] == LOCAL_AGENT_REQUIRED


def test_require_local_agent_internal_returns_false():
    r = require_local_agent_for_external_url("http://127.0.0.1:8000/")
    assert r["requires_local_agent"] is False


def test_handoff_payload_structure():
    r = build_local_agent_handoff(
        {
            "task_id": "t1",
            "target_url": "https://naver.com/",
            "action": "open_url",
        }
    )
    assert r["task_id"] == "t1"
    assert r["execution_location"] == LOCAL_AGENT_REQUIRED
    assert r["status"] == "WAITING_LOCAL_AGENT"
    assert r["local_agent_required"] is True
    _assert_safe(r)


def test_validate_external_with_server_internal_blocked():
    r = validate_task_execution_location(
        {
            "target_url": "https://naver.com",
            "execution_location": SERVER_INTERNAL_ONLY,
        }
    )
    assert r["valid"] is False


def test_validate_server_browser_used_true_blocked():
    r = validate_task_execution_location(
        {
            "target_url": "https://naver.com",
            "server_browser_used": True,
        }
    )
    assert r["valid"] is False
    assert r["blocked_reason"] == BLOCKED_SERVER_BROWSER_LAUNCH


def test_blocked_result_no_sensitive_data():
    r = block_external_fetch_from_server("https://naver.com/login")
    _assert_safe(r)
    # cookie/session/token 키가 없어야 함
    for key in r:
        assert "cookie" not in key.lower() or r[key] is False
        assert "session" not in key.lower() or key == "session_exported" or r[key] is False
        assert "token" not in key.lower()


def test_payment_action_external_user_direct():
    r = classify_execution_location_for_server(
        {
            "target_url": "https://shop.example.com/checkout",
            "action": "payment",
        }
    )
    assert r["execution_location"] == USER_DIRECT_REQUIRED


def test_url_query_token_sanitized():
    r = block_external_fetch_from_server("https://example.com/path?token=secret123&user=foo")
    # url_safe에 token이 포함되지 않음
    assert "secret123" not in r.get("url_safe", "")
    assert "token=" not in r.get("url_safe", "")


def test_safe_fields_in_blocked_result():
    r = block_external_fetch_from_server("https://naver.com/")
    _assert_safe(r)


def test_internal_fetch_passes():
    r = block_external_fetch_from_server("http://localhost:8000/health")
    assert r["blocked"] is False
    assert r["ok"] is True

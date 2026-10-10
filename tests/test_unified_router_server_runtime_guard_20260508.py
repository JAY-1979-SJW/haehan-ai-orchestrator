"""tests/test_unified_router_server_runtime_guard_20260508.py

unified_execution_router의 runtime_context guard 단위 검증.
runtime_context == "server" + 외부 URL → 즉시 BLOCKED 반환되는지 확인.
"""

from ai_orchestrator.browser_tool.routing.unified_execution_router import route_browser_task
from ai_orchestrator.server.execution_location_guard import (
    BLOCKED_SERVER_EXTERNAL_WEB_EXECUTION,
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
        assert r.get(f) is False, f"{f} != False in {r}"


def test_server_runtime_external_url_blocked():
    """runtime_context=server + 외부 URL → BLOCKED."""
    r = route_browser_task(
        {
            "task_id": "t1",
            "action": "open_url",
            "target_url": "https://naver.com/",
            "runtime_context": "server",
        }
    )
    assert r.get("status") == "BLOCKED"
    assert r.get("blocked_reason") == BLOCKED_SERVER_EXTERNAL_WEB_EXECUTION
    _assert_safe(r)


def test_server_runtime_g2b_blocked():
    r = route_browser_task(
        {
            "task_id": "t2",
            "action": "read_page",
            "target_url": "https://www.g2b.go.kr/",
            "runtime_context": "server",
        }
    )
    assert r.get("status") == "BLOCKED"
    assert r.get("blocked_reason") == BLOCKED_SERVER_EXTERNAL_WEB_EXECUTION


def test_server_runtime_bank_blocked():
    r = route_browser_task(
        {
            "task_id": "t3",
            "action": "download",
            "target_url": "https://obank.kbstar.com/",
            "runtime_context": "server",
        }
    )
    assert r.get("status") == "BLOCKED"


def test_server_runtime_localhost_not_blocked_by_guard():
    """runtime_context=server + 내부 URL → guard는 통과 (이후 일반 라우팅 적용)."""
    r = route_browser_task(
        {
            "task_id": "t4",
            "action": "open_url",
            "target_url": "http://localhost:8000/health",
            "runtime_context": "server",
        }
    )
    # blocked_reason이 BLOCKED_SERVER_EXTERNAL_WEB_EXECUTION은 아니어야 함
    assert r.get("blocked_reason") != BLOCKED_SERVER_EXTERNAL_WEB_EXECUTION


def test_no_runtime_context_external_url_normal_routing():
    """runtime_context 미지정 + 외부 URL → 기존 라우팅(LOCAL_BROWSER_DEFAULT/handoff)."""
    r = route_browser_task(
        {
            "task_id": "t5",
            "action": "open_url",
            "target_url": "https://example.com/",
        }
    )
    # runtime_context 없으면 server guard 트리거 안 됨 (기존 LOCAL_BROWSER_DEFAULT 경로)
    # blocked_reason이 BLOCKED_SERVER_EXTERNAL_WEB_EXECUTION이면 안 됨
    assert r.get("blocked_reason") != BLOCKED_SERVER_EXTERNAL_WEB_EXECUTION


def test_local_agent_runtime_external_url_not_blocked_by_server_guard():
    """runtime_context=local_agent + 외부 URL → server guard 미적용."""
    r = route_browser_task(
        {
            "task_id": "t6",
            "action": "open_url",
            "target_url": "https://example.com/",
            "runtime_context": "local_agent",
        }
    )
    assert r.get("blocked_reason") != BLOCKED_SERVER_EXTERNAL_WEB_EXECUTION


def test_server_runtime_safe_fields_in_blocked():
    """server runtime + 외부 URL 차단 결과에 safe field 모두 False."""
    r = route_browser_task(
        {
            "task_id": "t7",
            "action": "screenshot",
            "target_url": "https://naver.com/",
            "runtime_context": "server",
        }
    )
    _assert_safe(r)


def test_server_runtime_message_ko_present():
    """차단 결과에 한글 메시지 포함."""
    r = route_browser_task(
        {
            "task_id": "t8",
            "action": "open_url",
            "target_url": "https://gov.kr/",
            "runtime_context": "server",
        }
    )
    assert "로컬 에이전트" in r.get("message_ko", "")


def test_server_runtime_no_target_url_not_blocked():
    """target_url 없으면 외부 URL 차단 대상 아님."""
    r = route_browser_task(
        {
            "task_id": "t9",
            "action": "status_check",
            "runtime_context": "server",
        }
    )
    assert r.get("blocked_reason") != BLOCKED_SERVER_EXTERNAL_WEB_EXECUTION

"""통합 브라우저 실행 라우터 테스트 (LOCAL_BROWSER_DEFAULT 아키텍처)"""

from __future__ import annotations

from ai_orchestrator.browser_tool.unified_browser_safe_result import (
    EXEC_LOCAL_AGENT,
    EXEC_SERVER_BROWSER,
    EXEC_USER_DIRECT,
    STATUS_BLOCKED,
    STATUS_LOCAL_HANDOFF_CREATED,
    STATUS_USER_ACTION_REQUIRED,
)
from ai_orchestrator.browser_tool.routing.unified_execution_router import (
    classify_task_only,
    route_browser_task,
)


def _task(**kw):
    base = {
        "task_id": "t1",
        "action": "open",
        "target_url": "https://www.g2b.go.kr/notice/list",
        "readonly": True,
    }
    base.update(kw)
    return base


# G-1: 외부 웹 open → LOCAL_BROWSER_DEFAULT → LOCAL_HANDOFF_CREATED
def test_external_web_local_handoff():
    r = route_browser_task(_task())
    assert r["ok"] is True
    assert r["execution_used"] == EXEC_LOCAL_AGENT
    assert r["final_status"] == STATUS_LOCAL_HANDOFF_CREATED


# G-2: cookie_export 차단
def test_cookie_export_blocked():
    r = route_browser_task(_task(action="cookie_export"))
    assert r["ok"] is False
    assert r["final_status"] == STATUS_BLOCKED


# G-3: session_export 차단
def test_session_export_blocked():
    r = route_browser_task(_task(action="session_export"))
    assert r["ok"] is False
    assert r["final_status"] == STATUS_BLOCKED


# G-4: otp_input → USER_ACTION_REQUIRED
def test_otp_input_user_direct():
    r = route_browser_task(_task(action="otp_input"))
    assert r["final_status"] == STATUS_USER_ACTION_REQUIRED
    assert r["execution_used"] == EXEC_USER_DIRECT


# G-5: login → LOCAL_AGENT handoff (서버 시도 없음)
def test_login_local_handoff_no_server_attempt():
    r = route_browser_task(_task(action="login"))
    assert r["final_status"] == STATUS_LOCAL_HANDOFF_CREATED
    assert r["execution_used"] == EXEC_LOCAL_AGENT


# G-6: 내부 API → SERVER_BROWSER
def test_internal_api_server():
    r = route_browser_task(_task(action="report_generate", target_url="https://internal/api"))
    assert r["execution_used"] == EXEC_SERVER_BROWSER


# G-7: server_result 401 → HANDOFF_TO_LOCAL_AGENT
def test_server_result_401_handoff():
    r = route_browser_task(
        _task(action="report_generate", target_url="https://internal/api"),
        server_result={"http_status": 401, "verdict": "LIVE_FAIL"},
    )
    assert r["final_status"] == STATUS_LOCAL_HANDOFF_CREATED
    assert r["execution_used"] == EXEC_LOCAL_AGENT


# G-8: 안전 결과에 cookie 없음
def test_safe_result_no_cookie():
    r = route_browser_task(_task())
    assert r.get("cookie_exported") is False
    assert r.get("password_collected") is False
    assert r.get("otp_collected") is False


# G-9: task_id 없음 → BLOCKED
def test_missing_task_id_blocked():
    r = route_browser_task({"action": "open", "target_url": "https://www.g2b.go.kr"})
    assert r["ok"] is False
    assert r["final_status"] == STATUS_BLOCKED


# G-10: classify_task_only dry-run
def test_classify_task_only():
    r = classify_task_only(_task())
    assert "execution_location" in r
    assert r["task_id"] == "t1"


# G-11: local_agent_handoff에 local_browser_default=True 포함
def test_handoff_local_browser_default_flag():
    r = route_browser_task(_task())
    handoff = r.get("local_agent_handoff")
    assert handoff is not None
    assert handoff.get("local_browser_default") is True


# G-12: hometax → LOCAL_BROWSER_DEFAULT
def test_hometax_local_browser_default():
    r = route_browser_task(
        _task(
            action="open",
            target_url="https://www.hometax.go.kr/notice",
        )
    )
    assert r["execution_used"] == EXEC_LOCAL_AGENT
    assert r["final_status"] == STATUS_LOCAL_HANDOFF_CREATED


# G-13: classify_task_only fallback_allowed
def test_classify_fallback_allowed():
    r = classify_task_only(_task())
    assert "fallback_allowed" in r


# G-14: local_agent_handoff payload 안전성 검증
def test_handoff_payload_safety():
    r = route_browser_task(_task(action="login"))
    handoff = r.get("local_agent_handoff")
    assert handoff is not None
    assert handoff["readonly"] is True
    assert handoff["cookie_included"] is False
    assert handoff["password_included"] is False


# G-15: 사용자 안내 문구 포함
def test_user_message_contains_guide():
    r = route_browser_task(_task())
    assert "사용자 PC" in r["message_ko"]


# G-16: bid_submit → BLOCKED
def test_bid_submit_blocked():
    r = route_browser_task(_task(action="bid_submit"))
    assert r["final_status"] == STATUS_BLOCKED
    assert r["ok"] is False


# G-17: SERVER_ALLOWED 경로 server_result 성공
def test_server_allowed_success():
    r = route_browser_task(
        _task(action="report_generate", target_url="https://internal/api"),
        server_result={"http_status": 200, "verdict": "LIVE_PASS"},
    )
    assert r["ok"] is True
    assert r["execution_used"] == EXEC_SERVER_BROWSER

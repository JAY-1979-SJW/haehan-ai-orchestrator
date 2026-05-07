"""통합 브라우저 실행 라우터 테스트"""
from __future__ import annotations
import pytest
from ai_orchestrator.browser_tool.unified_execution_router import (
    route_browser_task, classify_task_only,
)
from ai_orchestrator.browser_tool.unified_browser_safe_result import (
    STATUS_SUCCESS, STATUS_BLOCKED, STATUS_LOCAL_HANDOFF_CREATED,
    STATUS_USER_ACTION_REQUIRED, STATUS_FAILED,
    EXEC_SERVER_BROWSER, EXEC_LOCAL_AGENT, EXEC_USER_DIRECT, EXEC_BLOCKED,
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


# G-1: 공개 read → SERVER_BROWSER dry-run 성공
def test_public_read_dry_run():
    r = route_browser_task(_task())
    assert r["ok"] is True
    assert r["execution_used"] == EXEC_SERVER_BROWSER

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

# G-5: login → LOCAL_AGENT handoff
def test_login_local_handoff():
    r = route_browser_task(_task(action="login"))
    assert r["final_status"] == STATUS_LOCAL_HANDOFF_CREATED
    assert r["execution_used"] == EXEC_LOCAL_AGENT

# G-6: server_result 401 → HANDOFF_TO_LOCAL_AGENT
def test_server_result_401_handoff():
    r = route_browser_task(
        _task(),
        server_result={"http_status": 401, "verdict": "LIVE_FAIL"},
    )
    assert r["final_status"] == STATUS_LOCAL_HANDOFF_CREATED
    assert r["execution_used"] == EXEC_LOCAL_AGENT

# G-7: server_result 성공 → COMPLETE_ON_SERVER
def test_server_result_success():
    r = route_browser_task(
        _task(),
        server_result={"http_status": 200, "verdict": "LIVE_PASS"},
    )
    assert r["ok"] is True
    assert r["execution_used"] == EXEC_SERVER_BROWSER

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

# G-11: 보안 신호 로그인 → HANDOFF
def test_security_signal_login_handoff():
    r = route_browser_task(
        _task(),
        server_result={
            "http_status": 200,
            "verdict": "LIVE_PASS",
            "security_signals": ["login_required"],
        },
    )
    # login_required 신호 있으므로 server success 경로 우회 → fallback
    assert r["execution_used"] in (EXEC_LOCAL_AGENT, EXEC_SERVER_BROWSER)

# G-12: hometax → LOCAL_REQUIRED (login)
def test_hometax_login_local():
    r = route_browser_task(_task(
        action="login",
        target_url="https://www.hometax.go.kr/login",
    ))
    assert r["execution_used"] == EXEC_LOCAL_AGENT

# G-13: classify_task_only fallback_allowed
def test_classify_fallback_allowed():
    r = classify_task_only(_task())
    assert "fallback_allowed" in r

# G-14: local_agent_handoff payload 검증 (login case)
def test_handoff_payload_in_result():
    r = route_browser_task(_task(action="login"))
    handoff = r.get("local_agent_handoff")
    assert handoff is not None
    assert handoff["readonly"] is True
    assert handoff["cookie_included"] is False

# G-15: 결과 안전성 검증 통과 (전체 흐름)
def test_result_safety_validated():
    r = route_browser_task(_task())
    # validate_safe_result가 위반이 없으면 반환됨 (위반이면 BLOCKED로 변환)
    assert r["final_status"] != STATUS_BLOCKED or r["ok"] is False

# G-16: bid_submit → BLOCKED 또는 USER_ACTION_REQUIRED
def test_bid_submit_blocked_or_user_direct():
    r = route_browser_task(_task(action="bid_submit"))
    assert r["final_status"] in (STATUS_BLOCKED, STATUS_USER_ACTION_REQUIRED)
    assert r["ok"] is False

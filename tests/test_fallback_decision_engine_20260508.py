"""Fallback 판정 엔진 테스트"""

from __future__ import annotations

from ai_orchestrator.browser_tool.routing.fallback_decision_engine import (
    BLOCK,
    COMPLETE_ON_SERVER,
    HANDOFF_TO_LOCAL_AGENT,
    REQUIRE_USER_DIRECT_ACTION,
    RETRY_ON_SERVER,
    decide_fallback,
)

_PROFILE_FALLBACK_OK = {
    "server_to_local_fallback": True,
    "login_execution": "LOCAL_REQUIRED",
}
_PROFILE_NO_FALLBACK = {
    "server_to_local_fallback": False,
    "login_execution": "LOCAL_REQUIRED",
}


def _decide(task=None, profile=None, server_result=None, signals=None, http_status=200, error_type=""):
    return decide_fallback(
        task=task or {"action": "open"},
        domain_profile=profile or _PROFILE_FALLBACK_OK,
        server_result=server_result or {},
        security_signals=signals or [],
        http_status=http_status,
        error_type=error_type,
    )


# D-1: 서버 성공 → COMPLETE_ON_SERVER
def test_server_success_complete():
    r = _decide(server_result={"verdict": "LIVE_PASS"}, http_status=200)
    assert r["decision"] == COMPLETE_ON_SERVER


# D-2: HTTP 401 → HANDOFF_TO_LOCAL_AGENT
def test_http_401_handoff():
    r = _decide(http_status=401)
    assert r["decision"] == HANDOFF_TO_LOCAL_AGENT


# D-3: HTTP 403 → HANDOFF_TO_LOCAL_AGENT
def test_http_403_handoff():
    r = _decide(http_status=403)
    assert r["decision"] == HANDOFF_TO_LOCAL_AGENT


# D-4: HTTP 500 → RETRY_ON_SERVER
def test_http_500_retry():
    r = _decide(http_status=500)
    assert r["decision"] == RETRY_ON_SERVER


# D-5: login_required 신호 + fallback 가능 → HANDOFF
def test_login_required_handoff():
    r = _decide(signals=["login_required"])
    assert r["decision"] == HANDOFF_TO_LOCAL_AGENT


# D-6: login_required 신호 + fallback 불가 → REQUIRE_USER_DIRECT_ACTION
def test_login_required_no_fallback_user_direct():
    r = _decide(signals=["login_required"], profile=_PROFILE_NO_FALLBACK)
    assert r["decision"] == REQUIRE_USER_DIRECT_ACTION


# D-7: otp_detected → REQUIRE_USER_DIRECT_ACTION
def test_otp_signal_user_direct():
    r = _decide(signals=["otp_detected"])
    assert r["decision"] == REQUIRE_USER_DIRECT_ACTION


# D-8: bid_submit_detected → REQUIRE_USER_DIRECT_ACTION
def test_bid_submit_user_direct():
    r = _decide(signals=["bid_submit_detected"])
    assert r["decision"] == REQUIRE_USER_DIRECT_ACTION


# D-9: cookie_export 신호 → BLOCK
def test_cookie_export_block():
    r = _decide(signals=["cookie_export"])
    assert r["decision"] == BLOCK
    assert r["sensitive_transfer_blocked"] is True


# D-10: auto_sign 신호 → BLOCK
def test_auto_sign_block():
    r = _decide(signals=["auto_sign"])
    assert r["decision"] == BLOCK


# D-11: cookie_export action → BLOCK
def test_cookie_export_action_block():
    r = _decide(task={"action": "cookie_export"})
    assert r["decision"] == BLOCK


# D-12: network_error → RETRY_ON_SERVER
def test_network_error_retry():
    r = _decide(error_type="network_error")
    assert r["decision"] == RETRY_ON_SERVER


# D-13: 서버 verdict LIVE_FAIL + fallback 가능 → HANDOFF
def test_server_fail_handoff():
    r = _decide(server_result={"verdict": "LIVE_FAIL"})
    assert r["decision"] == HANDOFF_TO_LOCAL_AGENT


# D-14: 서버 verdict LIVE_FAIL + fallback 불가 → BLOCK
def test_server_fail_no_fallback_block():
    r = _decide(server_result={"verdict": "LIVE_FAIL"}, profile=_PROFILE_NO_FALLBACK)
    assert r["decision"] == BLOCK


# D-15: sensitive_transfer_blocked always True for BLOCK
def test_block_sensitive_transfer_blocked():
    r = _decide(signals=["auto_payment"])
    assert r["decision"] == BLOCK
    assert r["sensitive_transfer_blocked"] is True


# D-16: HANDOFF fallback_to = LOCAL_AGENT
def test_handoff_fallback_to():
    r = _decide(http_status=401)
    assert r["fallback_to"] == "LOCAL_AGENT"


# D-17: COMPLETE_ON_SERVER fallback_to = None
def test_complete_no_fallback_to():
    r = _decide(server_result={"verdict": "LIVE_PASS"}, http_status=200)
    assert r["fallback_to"] is None

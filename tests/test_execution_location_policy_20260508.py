"""실행 위치 정책 테스트 (LOCAL_BROWSER_DEFAULT 아키텍처 반영)"""

from __future__ import annotations

from ai_orchestrator.browser_tool.routing.execution_location_policy import (
    BLOCKED,
    LOCAL_BROWSER_DEFAULT,
    SERVER_ALLOWED,
    SERVER_ONLY,
    USER_DIRECT_ONLY,
    classify_execution_location,
    get_execution_reason,
    is_local_browser_default,
    is_local_required,
    is_server_allowed,
    is_server_first,
    is_user_direct_only,
    should_block,
)


def _task(**kw):
    return {"task_id": "t1", "action": "open", "target_url": "https://www.g2b.go.kr/test", **kw}


# A-1: 공개 API/리포트 → SERVER_ALLOWED
def test_public_readonly_server_allowed():
    r = classify_execution_location(_task(action="read", readonly=True, site_category="public_readonly"))
    assert r["execution_location"] == SERVER_ALLOWED


# A-2: 내부 백엔드 → SERVER_ONLY
def test_internal_server_only():
    r = classify_execution_location(_task(action="db_query"))
    assert r["execution_location"] == SERVER_ONLY


# A-3: 외부 웹(g2b) open → LOCAL_BROWSER_DEFAULT
def test_external_web_local_browser_default():
    r = classify_execution_location(_task(action="open", site_category="government_procurement"))
    assert r["execution_location"] == LOCAL_BROWSER_DEFAULT


# A-4: government cert → LOCAL_BROWSER_DEFAULT
def test_cert_auth_local_browser_default():
    r = classify_execution_location(_task(action="cert_auth"))
    assert r["execution_location"] == LOCAL_BROWSER_DEFAULT


# A-5: bank login → LOCAL_BROWSER_DEFAULT
def test_bank_login_local_browser_default():
    r = classify_execution_location(_task(action="login", site_category="financial_banking_auth"))
    assert r["execution_location"] == LOCAL_BROWSER_DEFAULT


# A-6: OTP → USER_DIRECT_ONLY
def test_otp_user_direct():
    r = classify_execution_location(_task(action="otp_input"))
    assert r["execution_location"] == USER_DIRECT_ONLY


# A-7: bid_submit → BLOCKED
def test_bid_submit_blocked():
    r = classify_execution_location(_task(action="bid_submit"))
    assert r["execution_location"] == BLOCKED


# A-8: cookie export → BLOCKED
def test_cookie_export_blocked():
    r = classify_execution_location(_task(action="cookie_export"))
    assert r["execution_location"] == BLOCKED


# A-9: 기본값 (category 없음) → LOCAL_BROWSER_DEFAULT
def test_default_is_local_browser_default():
    r = classify_execution_location({"task_id": "t1", "action": "open", "target_url": "https://www.example.com"})
    assert r["execution_location"] == LOCAL_BROWSER_DEFAULT


# helper 함수 확인
def test_is_server_allowed_helper():
    assert is_server_allowed(_task(action="report_generate"))


def test_is_local_browser_default_helper():
    assert is_local_browser_default(_task(action="login"))


def test_is_server_first_legacy():
    # is_server_first는 SERVER_ALLOWED와 동일 (레거시 호환)
    assert is_server_first(_task(action="report_generate"))


def test_is_local_required_legacy():
    # is_local_required는 LOCAL_BROWSER_DEFAULT와 동일 (레거시 호환)
    assert is_local_required(_task(action="login"))


def test_is_user_direct_only_helper():
    assert is_user_direct_only(_task(action="otp_input"))


def test_should_block_helper():
    assert should_block(_task(action="cookie_export"))


def test_get_execution_reason_not_empty():
    reason = get_execution_reason(_task(action="open", site_category="government_procurement"))
    assert isinstance(reason, str) and reason


# session_export도 차단
def test_session_export_blocked():
    r = classify_execution_location(_task(action="session_export"))
    assert r["execution_location"] == BLOCKED


# LOCAL_BROWSER_DEFAULT fallback_allowed=True
def test_local_browser_default_fallback_allowed():
    r = classify_execution_location(_task(action="open", site_category="government_procurement"))
    assert r["fallback_allowed"] is True


# BLOCKED fallback_allowed=False
def test_blocked_fallback_not_allowed():
    r = classify_execution_location(_task(action="cookie_export"))
    assert r["fallback_allowed"] is False


# USER_DIRECT_ONLY fallback_allowed=False
def test_user_direct_fallback_not_allowed():
    r = classify_execution_location(_task(action="otp_input"))
    assert r["fallback_allowed"] is False


# 사용자 안내 문구 포함 확인
def test_local_browser_default_user_message():
    r = classify_execution_location(_task(action="open", site_category="government_procurement"))
    assert "사용자 PC" in r["user_message_ko"]
    assert "앱이 저장하지 않습니다" in r["user_message_ko"]

"""실행 위치 정책 테스트"""
from __future__ import annotations
import pytest
from ai_orchestrator.browser_tool.execution_location_policy import (
    SERVER_FIRST, SERVER_ONLY, LOCAL_REQUIRED, USER_DIRECT_ONLY, BLOCKED,
    classify_execution_location, is_server_first, is_local_required,
    is_user_direct_only, should_block, get_execution_reason,
)

def _task(**kw):
    return {"task_id": "t1", "action": "open", "target_url": "https://www.g2b.go.kr/test", **kw}

# A-1: 공개 URL read → SERVER_FIRST
def test_public_read_server_first():
    r = classify_execution_location(_task(action="read", readonly=True, site_category="public_readonly"))
    assert r["execution_location"] == SERVER_FIRST

# A-2: 내부 백엔드 → SERVER_ONLY
def test_internal_server_only():
    r = classify_execution_location(_task(action="db_query"))
    assert r["execution_location"] == SERVER_ONLY

# A-3: g2b login → LOCAL_REQUIRED
def test_g2b_login_local_required():
    r = classify_execution_location(_task(action="login"))
    assert r["execution_location"] == LOCAL_REQUIRED

# A-4: government cert → LOCAL_REQUIRED
def test_cert_auth_local_required():
    r = classify_execution_location(_task(action="cert_auth"))
    assert r["execution_location"] == LOCAL_REQUIRED

# A-5: bank login → LOCAL_REQUIRED
def test_bank_login_local_required():
    r = classify_execution_location(_task(action="login", site_category="financial_banking_auth"))
    assert r["execution_location"] == LOCAL_REQUIRED

# A-6: OTP → USER_DIRECT_ONLY
def test_otp_user_direct():
    r = classify_execution_location(_task(action="otp_input"))
    assert r["execution_location"] == USER_DIRECT_ONLY

# A-7: bid submit → USER_DIRECT_ONLY 또는 BLOCKED
def test_bid_submit_blocked_or_user_direct():
    r = classify_execution_location(_task(action="bid_submit"))
    assert r["execution_location"] in (USER_DIRECT_ONLY, BLOCKED)

# A-8: cookie export → BLOCKED
def test_cookie_export_blocked():
    r = classify_execution_location(_task(action="cookie_export"))
    assert r["execution_location"] == BLOCKED

# helper 함수 확인
def test_is_server_first_helper():
    assert is_server_first(_task(action="open", readonly=True, site_category="public_readonly"))

def test_is_local_required_helper():
    assert is_local_required(_task(action="login"))

def test_is_user_direct_only_helper():
    assert is_user_direct_only(_task(action="otp_input"))

def test_should_block_helper():
    assert should_block(_task(action="cookie_export"))

def test_get_execution_reason_not_empty():
    reason = get_execution_reason(_task(action="open", site_category="public_readonly"))
    assert isinstance(reason, str) and reason

# session_export도 차단
def test_session_export_blocked():
    r = classify_execution_location(_task(action="session_export"))
    assert r["execution_location"] == BLOCKED

# wildcard domain 분류 시 기본값 사용 (사이트 profile 의존)
def test_fallback_allowed_server_first():
    r = classify_execution_location(_task(action="open", site_category="public_readonly"))
    assert r["fallback_allowed"] is True

def test_blocked_fallback_not_allowed():
    r = classify_execution_location(_task(action="cookie_export"))
    assert r["fallback_allowed"] is False

def test_user_direct_fallback_not_allowed():
    r = classify_execution_location(_task(action="otp_input"))
    assert r["fallback_allowed"] is False

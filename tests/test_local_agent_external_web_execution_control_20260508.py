"""tests/test_local_agent_external_web_execution_control_20260508.py

LOCAL_AGENT_EXTERNAL_WEB_EXECUTION_CONTROL_CLOSEOUT_1 단위 검증.

기존 정책 모듈을 재사용하여 다음을 검증한다 (신규 모듈 추가 없음):
- action_risk_policy 4등급 분류
- site_type_classifier (은행/정부/카드/보험)
- security_route_policy (보안프로그램/UAC)
- universal_safe_result (redaction)
- server.execution_location_guard (LOCAL_AGENT_REQUIRED handoff)

mock/local fixture만 사용. 외부 사이트 실접속 0건.
"""

import pytest

from ai_orchestrator.contracts.action_risk_policy import (
    GRADE_AUTO_ALLOWED,
    GRADE_BLOCKED,
    GRADE_USER_DELEGATED,
    GRADE_USER_DIRECT,
    classify_action,
)
from ai_orchestrator.server.execution_location_guard import (
    LOCAL_AGENT_REQUIRED,
    SERVER_INTERNAL_ONLY,
    classify_execution_location_for_server,
)
from ai_orchestrator.server.universal_agent_task_api import clear_all, create_task
from core.agent_runtime.runtime.security_program.local_security_installer_runner import (
    GRADE_BLOCKED as INSTALLER_GRADE_BLOCKED,
)
from core.agent_runtime.runtime.security_program.local_security_installer_runner import (
    STATUS_INSTALL_PERMISSION_REQUIRED,
    STATUS_WAITING_USER_UAC,
    check_action_allowed,
)
from core.agent_runtime.runtime.site_profile.site_type_classifier import (
    SITE_GOVERNMENT,
    classify_site,
)
from core.agent_runtime.runtime.universal.universal_safe_result import (
    STATUS_COMPLETED,
    build_universal_result,
    sanitize_universal_result,
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
        assert r.get(f) is False, f"{f} != False in {r}"


# ── 1. 공개 조회 → AUTO_ALLOWED ──────────────────────────────────────────────


def test_public_readonly_read_page_auto_allowed():
    grade = classify_action("read_page")
    assert grade == GRADE_AUTO_ALLOWED


def test_public_search_auto_allowed():
    grade = classify_action("search")
    assert grade == GRADE_AUTO_ALLOWED


def test_extract_text_auto_allowed():
    grade = classify_action("extract_text")
    assert grade == GRADE_AUTO_ALLOWED


# ── 2. 은행/정부 도메인 분류 ──────────────────────────────────────────────────


def test_government_g2b_classified():
    r = classify_site({"host": "www.g2b.go.kr"})
    assert r["site_type"] == SITE_GOVERNMENT


def test_government_hometax_classified():
    r = classify_site({"host": "hometax.go.kr"})
    assert r["site_type"] == SITE_GOVERNMENT


def test_government_gov_kr_classified():
    r = classify_site({"host": "www.gov.kr"})
    assert r["site_type"] == SITE_GOVERNMENT


# ── 3. 비밀번호/OTP/인증서 자동 입력 → USER_DIRECT ───────────────────────────


def test_login_password_input_user_direct():
    grade = classify_action("login_password_input")
    assert grade == GRADE_USER_DIRECT


def test_otp_input_user_direct():
    grade = classify_action("otp_input")
    assert grade == GRADE_USER_DIRECT


def test_cert_password_input_user_direct():
    grade = classify_action("cert_password_input")
    assert grade == GRADE_USER_DIRECT


# ── 4. 결제/송금/투찰/전자서명 → USER_DIRECT or BLOCKED ──────────────────────


def test_confirm_payment_user_direct():
    grade = classify_action("confirm_payment")
    assert grade == GRADE_USER_DIRECT


def test_confirm_transfer_user_direct():
    grade = classify_action("confirm_transfer")
    assert grade == GRADE_USER_DIRECT


def test_bid_final_submit_user_direct():
    grade = classify_action("bid_final_submit")
    assert grade == GRADE_USER_DIRECT


def test_e_sign_user_direct():
    grade = classify_action("e_sign")
    assert grade == GRADE_USER_DIRECT


def test_government_final_submit_user_direct():
    grade = classify_action("government_final_submit")
    assert grade == GRADE_USER_DIRECT


# ── 5. credential 자동화 → BLOCKED ──────────────────────────────────────────


def test_password_save_blocked():
    grade = classify_action("password_save")
    assert grade == GRADE_BLOCKED


def test_otp_save_blocked():
    grade = classify_action("otp_save")
    assert grade == GRADE_BLOCKED


def test_cert_password_save_blocked():
    grade = classify_action("cert_password_save")
    assert grade == GRADE_BLOCKED


def test_collect_password_blocked():
    grade = classify_action("collect_password")
    assert grade == GRADE_BLOCKED


# ── 6. cookie/session 추출 → BLOCKED ─────────────────────────────────────────


def test_cookie_export_blocked():
    assert classify_action("cookie_export") == GRADE_BLOCKED


def test_session_export_blocked():
    assert classify_action("session_export") == GRADE_BLOCKED


def test_storage_state_export_blocked():
    assert classify_action("storage_state_export") == GRADE_BLOCKED


def test_token_export_blocked():
    assert classify_action("token_export") == GRADE_BLOCKED


def test_localStorage_dump_blocked():
    assert classify_action("localStorage_dump") == GRADE_BLOCKED


# ── 7. 인증서/NPKI 파일 접근 → BLOCKED ──────────────────────────────────────


def test_cert_file_access_blocked():
    assert classify_action("cert_file_access") == GRADE_BLOCKED


def test_npki_access_blocked():
    assert classify_action("npki_access") == GRADE_BLOCKED


def test_read_certificate_file_blocked():
    assert classify_action("read_certificate_file") == GRADE_BLOCKED


# ── 8. 자동 결제/송금/투찰/서명 → BLOCKED ───────────────────────────────────


def test_auto_sign_blocked():
    assert classify_action("auto_sign") == GRADE_BLOCKED


def test_auto_bid_submit_blocked():
    assert classify_action("auto_bid_submit") == GRADE_BLOCKED


def test_auto_payment_blocked():
    assert classify_action("auto_payment") == GRADE_BLOCKED


def test_auto_transfer_blocked():
    assert classify_action("auto_transfer") == GRADE_BLOCKED


def test_transfer_money_blocked():
    assert classify_action("transfer_money") == GRADE_BLOCKED


# ── 9. 보안프로그램 / UAC 흐름 (local_security_installer_runner 기반) ───────


def test_installer_uac_status_exists():
    """UAC 사용자 직접 승인 상태 존재."""
    assert STATUS_WAITING_USER_UAC == "WAITING_USER_UAC"


def test_installer_permission_required_status_exists():
    """설치 권한 사용자 승인 필요 상태 존재."""
    assert STATUS_INSTALL_PERMISSION_REQUIRED == "INSTALL_PERMISSION_REQUIRED"


def test_installer_runner_blocks_uac_bypass():
    r = check_action_allowed("bypass_uac")
    assert r["allowed"] is False
    assert r["grade"] == INSTALLER_GRADE_BLOCKED


def test_installer_runner_blocks_security_bypass():
    r = check_action_allowed("bypass_security_program")
    assert r["allowed"] is False


def test_installer_runner_blocks_silent_install_auto():
    r = check_action_allowed("silent_install_auto")
    assert r["allowed"] is False


# ── 10. 결과 redaction (sanitize_universal_result) ──────────────────────────


def test_sanitize_strips_password():
    r = build_universal_result(task_id="t1", status=STATUS_COMPLETED)
    r["password"] = "secret123"
    s = sanitize_universal_result(r)
    assert "password" not in s


def test_sanitize_strips_cookie():
    r = build_universal_result(task_id="t1", status=STATUS_COMPLETED)
    r["cookie"] = "abc=xyz"
    s = sanitize_universal_result(r)
    assert "cookie" not in s


def test_sanitize_strips_token():
    r = build_universal_result(task_id="t1", status=STATUS_COMPLETED)
    r["token"] = "eyJhbGciOi..."
    s = sanitize_universal_result(r)
    assert "token" not in s


def test_sanitize_strips_storage_state():
    r = build_universal_result(task_id="t1", status=STATUS_COMPLETED)
    r["storage_state"] = {"cookies": []}
    s = sanitize_universal_result(r)
    assert "storage_state" not in s


def test_sanitize_safe_fields_always_false():
    r = build_universal_result(task_id="t1", status=STATUS_COMPLETED)
    r["server_browser_used"] = True  # 시도
    s = sanitize_universal_result(r)
    assert s.get("server_browser_used") is False


# ── 11. server execution_location_guard handoff ────────────────────────────


def test_naver_external_local_agent_required():
    r = classify_execution_location_for_server(
        {
            "target_url": "https://naver.com/",
            "action": "open_url",
        }
    )
    assert r["execution_location"] == LOCAL_AGENT_REQUIRED


def test_localhost_server_internal_only():
    r = classify_execution_location_for_server(
        {
            "target_url": "http://localhost:8000/health",
            "action": "open_url",
        }
    )
    assert r["execution_location"] == SERVER_INTERNAL_ONLY


def test_create_task_external_returns_handoff():
    r = create_task(action="open_url", target_url="https://kbstar.com/")
    assert r["execution_location"] == LOCAL_AGENT_REQUIRED
    assert r["status"] == "WAITING_LOCAL_AGENT"
    assert r["server_browser_used"] is False
    _assert_safe(r)


def test_create_task_handoff_no_sensitive_fields():
    r = create_task(action="open_url", target_url="https://hometax.go.kr/")
    handoff = r["local_agent_handoff"]
    # 민감 키 부재 또는 False
    forbidden = ["password", "otp", "cert_password", "cookie_value", "session_value", "token", "npki"]
    for key in handoff:
        for f in forbidden:
            assert f not in key.lower() or handoff[key] is False, f"민감 키 발견: {key} in handoff"
    _assert_safe(handoff)


# ── 12. 사용자 직접 조작 모드 분리 ──────────────────────────────────────────


def test_form_submit_is_user_delegated_not_auto():
    """form_submit은 자동 실행 아님 — 사용자 권한 위임 후 실행."""
    grade = classify_action("form_submit")
    assert grade == GRADE_USER_DELEGATED


def test_blog_publish_is_user_delegated():
    grade = classify_action("blog_publish")
    assert grade == GRADE_USER_DELEGATED


def test_send_email_is_user_delegated():
    grade = classify_action("send_email")
    assert grade == GRADE_USER_DELEGATED


def test_file_upload_is_user_delegated():
    grade = classify_action("file_upload")
    assert grade == GRADE_USER_DELEGATED


# ── 13. 우회/스팸 → BLOCKED ────────────────────────────────────────────────


def test_captcha_bypass_blocked():
    assert classify_action("captcha_bypass") == GRADE_BLOCKED


def test_account_restriction_bypass_blocked():
    assert classify_action("account_restriction_bypass") == GRADE_BLOCKED


def test_bulk_spam_post_blocked():
    assert classify_action("bulk_spam_post") == GRADE_BLOCKED


# ── 14. server_browser_used False 강제 ─────────────────────────────────────


def test_universal_result_server_browser_used_false():
    r = build_universal_result(task_id="t1", status=STATUS_COMPLETED)
    assert r.get("server_browser_used") is False


def test_local_agent_handoff_server_browser_used_false():
    r = create_task(action="open_url", target_url="https://gov.kr/")
    assert r["server_browser_used"] is False
    assert r["local_agent_handoff"]["server_browser_used"] is False

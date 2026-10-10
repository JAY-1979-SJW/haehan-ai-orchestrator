"""
나라장터 read-only safe result 검증 테스트
"""

from ai_orchestrator.contracts.local_task_protocol import (
    STATUS_COMPLETED,
    STATUS_USER_ACTION_REQUIRED,
    STATUS_WAITING_USER_AUTH,
    build_result,
)
from core.agent_runtime.runtime.local_session_boundary import (
    enforce_session_boundary,
    is_safe_for_export,
    validate_session_boundary,
)
from core.agent_runtime.runtime.result_sanitizer import (
    sanitize_result,
    validate_sanitized_result,
)

G2B_HOST = "www.g2b.go.kr"
TASK_ID = "g2b-safe-result-test-001"


def _make_g2b_completed_result(**extra) -> dict:
    r = build_result(
        task_id=TASK_ID,
        ok=True,
        status=STATUS_COMPLETED,
        current_url_host=G2B_HOST,
        title_hint="나라장터",
        extracted_data={"body_text_sample": "입찰공고 목록"},
        message_ko="페이지 읽기 완료.",
    )
    r.update(extra)
    return r


class TestSafeResultFields:
    def test_completed_result_safe_fields(self):
        result = _make_g2b_completed_result()
        assert result["sensitive_data_collected"] is False
        assert result["cookie_exported"] is False
        assert result["session_exported"] is False
        assert result["password_collected"] is False
        assert result["otp_collected"] is False
        assert result["certificate_password_collected"] is False

    def test_sanitize_removes_cookie(self):
        result = _make_g2b_completed_result(cookie="abc123")
        safe = sanitize_result(result)
        assert safe.get("cookie") in (None, False, "")
        assert safe["sensitive_data_collected"] is False

    def test_sanitize_removes_session(self):
        result = _make_g2b_completed_result(session="sess_xyz")
        safe = sanitize_result(result)
        assert safe.get("session") in (None, False, "")

    def test_sanitize_removes_token(self):
        result = _make_g2b_completed_result(token="tok_abc")
        safe = sanitize_result(result)
        assert safe.get("token") in (None, False, "")

    def test_sanitize_removes_password(self):
        result = _make_g2b_completed_result(password="pw123")
        safe = sanitize_result(result)
        assert safe.get("password") in (None, False, "")

    def test_sanitize_removes_otp(self):
        result = _make_g2b_completed_result(otp="123456")
        safe = sanitize_result(result)
        assert safe.get("otp") in (None, False, "")

    def test_sanitize_removes_cert_password(self):
        result = _make_g2b_completed_result(certificate_password="certpw")
        safe = sanitize_result(result)
        assert safe.get("certificate_password") in (None, False, "")

    def test_sanitize_removes_npki(self):
        result = _make_g2b_completed_result(npki="path/to/npki")
        safe = sanitize_result(result)
        assert safe.get("npki") in (None, False, "")

    def test_validate_no_violations(self):
        result = sanitize_result(_make_g2b_completed_result())
        violations = validate_sanitized_result(result)
        assert violations == []

    def test_body_text_preserved(self):
        result = _make_g2b_completed_result()
        safe = sanitize_result(result)
        assert safe["extracted_data"]["body_text_sample"] == "입찰공고 목록"

    def test_title_hint_preserved(self):
        result = _make_g2b_completed_result()
        safe = sanitize_result(result)
        assert safe["title_hint"] == "나라장터"


class TestSessionBoundary:
    def test_enforce_boundary_on_g2b_result(self):
        result = _make_g2b_completed_result()
        safe = enforce_session_boundary(result)
        assert is_safe_for_export(safe) is True

    def test_boundary_removes_storage_state(self):
        result = _make_g2b_completed_result(storage_state={"cookies": []})
        safe = enforce_session_boundary(result)
        assert safe.get("storage_state") in (None, False, {})
        assert safe["storage_state_exported"] is False

    def test_boundary_forces_all_safe_fields(self):
        result = _make_g2b_completed_result(
            cookie_exported=True,
            session_exported=True,
            password_collected=True,
        )
        safe = enforce_session_boundary(result)
        assert safe["cookie_exported"] is False
        assert safe["session_exported"] is False
        assert safe["password_collected"] is False

    def test_double_sanitize_safe(self):
        result = _make_g2b_completed_result(cookie="abc", session="xyz")
        step1 = sanitize_result(result)
        step2 = enforce_session_boundary(step1)
        violations = validate_session_boundary(step2)
        assert violations == []


class TestWaitingUserAuthResult:
    def test_waiting_user_auth_safe_fields(self):
        result = build_result(
            task_id=TASK_ID,
            ok=False,
            status=STATUS_WAITING_USER_AUTH,
            current_url_host=G2B_HOST,
            message_ko="인증이 필요합니다.",
        )
        assert result["sensitive_data_collected"] is False
        assert result["cookie_exported"] is False
        assert result["password_collected"] is False

    def test_user_action_required_safe_fields(self):
        result = build_result(
            task_id=TASK_ID,
            ok=False,
            status=STATUS_USER_ACTION_REQUIRED,
            current_url_host=G2B_HOST,
            message_ko="OTP 입력이 필요합니다.",
        )
        assert result["sensitive_data_collected"] is False
        assert result["otp_collected"] is False

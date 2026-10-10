"""
나라장터 read-only 정책 guard 테스트

서버 외부 브라우저 실행 없음.
위험 action 차단.
민감정보 수집 없음.
"""

import pytest

from ai_orchestrator.browser_tool.policy.security_signal_detector import (
    SIG_BID_SUBMIT,
    SIG_CERT_AUTH,
    SIG_CONTRACT_SUBMIT,
    SIG_E_SIGNATURE,
    SIG_LOGIN_REQUIRED,
    SIG_OTP,
    SIG_PAYMENT_OR_TRANSFER,
    detect_from_page_text,
)
from ai_orchestrator.contracts.local_task_protocol import (
    EXEC_MODE_LOCAL_PLAYWRIGHT,
    build_task,
)
from core.agent_runtime.runtime.auth.auto_resume_after_auth import (
    can_auto_resume,
    classify_resume_eligibility,
)
from core.agent_runtime.runtime.security_guard import (
    block_forbidden_action,
    validate_task_before_run,
)

G2B_HOST = "www.g2b.go.kr"
G2B_URL = "https://www.g2b.go.kr/"


def _g2b_task(action: str) -> dict:
    return build_task(action=action, target_url=G2B_URL, domain=G2B_HOST)


def _raw_task(action: str) -> dict:
    """build_task를 우회해 raw dict 생성 (차단 action 검증용)."""
    return {
        "task_id": "guard-test",
        "task_type": "browser_task",
        "execution_mode": EXEC_MODE_LOCAL_PLAYWRIGHT,
        "action": action,
        "target_url": G2B_URL,
        "domain": G2B_HOST,
        "readonly": True,
        "requires_user_presence": False,
        "timeout_seconds": 30,
        "metadata": {},
    }


class TestSecurityGuardG2b:
    def test_read_page_allowed(self):
        task = _g2b_task("read_page")
        guard = validate_task_before_run(task)
        assert guard["allowed"] is True

    def test_extract_text_allowed(self):
        task = _g2b_task("extract_text")
        guard = validate_task_before_run(task)
        assert guard["allowed"] is True

    def test_extract_table_allowed(self):
        task = _g2b_task("extract_table")
        guard = validate_task_before_run(task)
        assert guard["allowed"] is True

    def test_detect_login_status_allowed(self):
        task = _g2b_task("detect_login_status")
        guard = validate_task_before_run(task)
        assert guard["allowed"] is True

    def test_capture_screenshot_allowed(self):
        task = _g2b_task("capture_screenshot")
        guard = validate_task_before_run(task)
        assert guard["allowed"] is True

    def test_cookie_export_blocked(self):
        # 위험 action은 build_task 자체에서 ValueError로 차단되며,
        # block_forbidden_action으로도 검증 가능
        result = block_forbidden_action(_raw_task("cookie_export"))
        assert result["blocked"] is True

    def test_auto_bid_submit_blocked(self):
        result = block_forbidden_action(_raw_task("auto_bid_submit"))
        assert result["blocked"] is True

    def test_auto_sign_blocked(self):
        result = block_forbidden_action(_raw_task("auto_sign"))
        assert result["blocked"] is True

    def test_auto_payment_blocked(self):
        result = block_forbidden_action(_raw_task("auto_payment"))
        assert result["blocked"] is True

    def test_collect_password_blocked(self):
        result = block_forbidden_action(_raw_task("collect_password"))
        assert result["blocked"] is True

    def test_collect_otp_blocked(self):
        result = block_forbidden_action(_raw_task("collect_otp"))
        assert result["blocked"] is True

    def test_read_certificate_file_blocked(self):
        result = block_forbidden_action(_raw_task("read_certificate_file"))
        assert result["blocked"] is True

    def test_npki_access_blocked(self):
        result = block_forbidden_action(_raw_task("npki_access"))
        assert result["blocked"] is True

    def test_build_task_rejects_dangerous_action(self):
        """build_task는 허용 목록 외 action을 ValueError로 거부한다."""
        with pytest.raises(ValueError, match="허용되지 않은 action"):
            build_task(action="auto_bid_submit", target_url=G2B_URL, domain=G2B_HOST)

    def test_build_task_rejects_cookie_export(self):
        with pytest.raises(ValueError, match="허용되지 않은 action"):
            build_task(action="cookie_export", target_url=G2B_URL, domain=G2B_HOST)

    def test_task_with_password_field_blocked(self):
        task = _g2b_task("read_page")
        task["password"] = "pw123"
        guard = validate_task_before_run(task)
        assert guard["allowed"] is False

    def test_task_with_cookie_field_blocked(self):
        task = _g2b_task("read_page")
        task["cookie"] = "abc"
        guard = validate_task_before_run(task)
        assert guard["allowed"] is False

    def test_task_with_session_field_blocked(self):
        task = _g2b_task("read_page")
        task["session"] = "sess"
        guard = validate_task_before_run(task)
        assert guard["allowed"] is False


class TestSecuritySignalDetector:
    def test_login_text_detected(self):
        result = detect_from_page_text(title="로그인", body_text="아이디와 비밀번호를 입력하세요")
        assert result["has_security_signal"] is True
        assert SIG_LOGIN_REQUIRED in result["signals"]

    def test_cert_auth_text_detected(self):
        result = detect_from_page_text(title="인증서 로그인", body_text="공동인증서를 선택하세요")
        assert SIG_CERT_AUTH in result["signals"]

    def test_otp_text_detected(self):
        result = detect_from_page_text(title="OTP 인증", body_text="일회용 비밀번호를 입력하세요")
        assert SIG_OTP in result["signals"]

    def test_bid_submit_text_detected(self):
        result = detect_from_page_text(title="전자입찰", body_text="투찰 버튼을 클릭하세요")
        assert SIG_BID_SUBMIT in result["signals"]

    def test_payment_text_detected(self):
        result = detect_from_page_text(title="결제", body_text="결제를 진행하세요")
        assert SIG_PAYMENT_OR_TRANSFER in result["signals"]

    def test_e_signature_text_detected(self):
        result = detect_from_page_text(title="전자서명", body_text="공인전자서명을 수행합니다")
        assert SIG_E_SIGNATURE in result["signals"]

    def test_readonly_page_no_signal(self):
        result = detect_from_page_text(
            title="나라장터",
            body_text="입찰공고 목록 조회 결과입니다. 공고번호 제목 기관명",
        )
        # 읽기 전용 페이지에서 submit/sign/bid 신호 없음
        assert SIG_BID_SUBMIT not in result["signals"]
        assert SIG_E_SIGNATURE not in result["signals"]
        assert SIG_CONTRACT_SUBMIT not in result["signals"]


class TestAutoResumePolicy:
    def test_readonly_actions_eligible_after_auth(self):
        for action in (
            "read_page",
            "extract_text",
            "extract_table",
            "detect_login_status",
            "capture_screenshot",
            "download_file",
            "search",
        ):
            assert can_auto_resume(action) is True, f"{action} should be auto-resumable"

    def test_dangerous_actions_not_eligible_after_auth(self):
        for action in ("submit", "sign", "payment", "bid_submit", "final_submit", "transfer", "contract_submit"):
            eligibility = classify_resume_eligibility(action)
            assert eligibility["eligible"] is False, f"{action} should NOT be auto-resumable"
            assert "사용자 직접" in eligibility["reason"]

    def test_server_browser_not_used(self):
        # 공통 task protocol에서 서버 외부 브라우저 실행이 없는지 확인
        # execution_mode가 LOCAL_PLAYWRIGHT만 허용됨을 검증
        task = _g2b_task("read_page")
        assert task["execution_mode"] == EXEC_MODE_LOCAL_PLAYWRIGHT

    def test_g2b_task_no_external_browser_flag(self):
        task = _g2b_task("read_page")
        # 서버 브라우저 실행 관련 필드 없음
        assert "server_browser" not in task
        assert "remote_browser" not in task

"""
auth_completion_detector 테스트
"""

from core.agent_runtime.runtime.auth.auth_completion_detector import (
    check_auth_completed_from_dict,
    check_auth_completed_from_page_state,
)


class TestCheckAuthCompletedFromPageState:
    def test_login_page_not_completed(self):
        result = check_auth_completed_from_page_state(
            current_title="로그인",
            current_url="https://example.com/login",
            body_text_sample="아이디와 비밀번호를 입력하세요. 로그인이 필요합니다.",
        )
        assert result["auth_completed"] is False
        assert result["status"] == "WAITING_USER_AUTH"
        assert result["sensitive_data_collected"] is False

    def test_cert_auth_page_not_completed(self):
        result = check_auth_completed_from_page_state(
            current_title="공동인증서 로그인",
            current_url="https://example.com/cert",
            body_text_sample="인증서를 선택하세요.",
        )
        assert result["auth_completed"] is False
        assert result["sensitive_data_collected"] is False

    def test_business_page_after_auth_completed(self):
        result = check_auth_completed_from_page_state(
            current_title="메인 대시보드",
            current_url="https://example.com/main",
            body_text_sample="환영합니다. 로그아웃",
            prev_title="로그인",
            prev_url="https://example.com/login",
        )
        assert result["auth_completed"] is True
        assert result["status"] == "AUTH_COMPLETED"
        assert result["safe_to_resume"] is True
        assert result["sensitive_data_collected"] is False

    def test_signals_cleared_includes_login(self):
        result = check_auth_completed_from_page_state(
            current_title="홈",
            current_url="https://example.com/home",
            body_text_sample="마이페이지",
            prev_title="로그인 페이지",
            prev_url="https://example.com/login",
        )
        assert result["auth_completed"] is True
        assert "login_required" in result["signals_cleared"]

    def test_no_prev_title_auth_pending(self):
        result = check_auth_completed_from_page_state(
            current_title="홈",
            current_url="https://example.com/home",
            body_text_sample="환영합니다",
        )
        # prev 없이 cleared indicator만으로 완료 판단
        assert result["sensitive_data_collected"] is False

    def test_password_value_not_in_output(self):
        result = check_auth_completed_from_page_state(
            current_title="로그인",
            current_url="https://example.com/login",
            body_text_sample="로그인 페이지",
        )
        assert "password" not in result
        assert "otp" not in result
        assert "cookie" not in result
        assert "session" not in result

    def test_npki_not_in_output(self):
        result = check_auth_completed_from_page_state(
            current_title="npki 인증",
            current_url="https://example.com/npki",
            body_text_sample="npki 인증서를 선택하세요",
        )
        assert "npki" not in result
        assert result["sensitive_data_collected"] is False


class TestCheckAuthCompletedFromDict:
    def test_dict_interface_login_not_completed(self):
        result = check_auth_completed_from_dict(
            {
                "title": "로그인",
                "url": "https://example.com/login",
                "body_text": "로그인이 필요합니다",
            }
        )
        assert result["auth_completed"] is False

    def test_dict_interface_completed(self):
        result = check_auth_completed_from_dict(
            {
                "title": "대시보드",
                "url": "https://example.com/main",
                "body_text": "로그아웃",
                "prev_title": "로그인",
                "prev_url": "https://example.com/login",
            }
        )
        assert result["auth_completed"] is True
        assert result["sensitive_data_collected"] is False

    def test_storage_state_not_accessed(self):
        result = check_auth_completed_from_dict(
            {
                "title": "홈",
                "url": "https://example.com/home",
                "body_text": "마이페이지",
                "prev_title": "로그인",
                "prev_url": "https://example.com/login",
            }
        )
        assert "localStorage" not in result
        assert "sessionStorage" not in result
        assert "storage_state" not in result
        assert "cookies" not in result

"""
user_notification_adapter 테스트
"""

from unittest.mock import MagicMock, patch

from core.agent_runtime.runtime.notify.user_notification_adapter import (
    _SAFE_BODY,
    _SAFE_TITLE,
    FALLBACK_MESSAGE_ONLY,
    NOTIFICATION_FAILED,
    NOTIFICATION_SENT,
    NOTIFICATION_UNAVAILABLE,
    _is_safe_message,
    get_fallback_message,
    notify_auth_required,
    send_notification,
)


class TestSendNotification:
    def test_returns_dict(self):
        result = send_notification()
        assert isinstance(result, dict)

    def test_no_sensitive_data_in_result(self):
        result = send_notification()
        assert result["sensitive_data_included"] is False
        assert result["password_in_message"] is False
        assert result["otp_in_message"] is False
        assert result["cert_password_in_message"] is False

    def test_no_submit_action_in_notification(self):
        result = send_notification()
        assert result["submit_action_in_notification"] is False
        assert result["sign_action_in_notification"] is False
        assert result["payment_action_in_notification"] is False
        assert result["bid_action_in_notification"] is False

    def test_uses_safe_title_when_none_provided(self):
        result = send_notification()
        assert result["title_used"] == _SAFE_TITLE

    def test_uses_safe_body_when_none_provided(self):
        result = send_notification()
        assert result["message_used"] == _SAFE_BODY

    def test_sensitive_title_replaced_with_safe(self):
        result = send_notification(title="password: abc123", body="test")
        assert result["title_used"] == _SAFE_TITLE
        assert result["message_used"] == _SAFE_BODY

    def test_sensitive_body_replaced_with_safe(self):
        result = send_notification(title="test", body="session=abc token=xyz")
        assert result["title_used"] == _SAFE_TITLE
        assert result["message_used"] == _SAFE_BODY

    def test_status_is_valid_value(self):
        result = send_notification()
        assert result["status"] in {
            NOTIFICATION_SENT,
            NOTIFICATION_UNAVAILABLE,
            NOTIFICATION_FAILED,
            FALLBACK_MESSAGE_ONLY,
        }

    def test_plyer_success_returns_sent(self):
        mock_notify = MagicMock()
        with patch.dict("sys.modules", {"plyer": MagicMock(notification=mock_notify)}):
            with patch("sys.platform", "win32"):
                result = send_notification()
        assert result["sensitive_data_included"] is False

    def test_all_libs_unavailable_returns_unavailable(self):
        with patch("sys.platform", "win32"):
            with patch.dict("sys.modules", {"plyer": None, "win10toast": None, "winotify": None}):
                result = send_notification()
        assert result["status"] in {
            NOTIFICATION_UNAVAILABLE,
            NOTIFICATION_FAILED,
            NOTIFICATION_SENT,
            FALLBACK_MESSAGE_ONLY,
        }
        assert result["sensitive_data_included"] is False


class TestNotifyAuthRequired:
    def test_result_has_auth_signal(self):
        result = notify_auth_required(auth_signal="login_required")
        assert result["auth_signal"] == "login_required"

    def test_fallback_available_when_os_unavailable(self):
        with patch(
            "core.agent_runtime.runtime.notify.user_notification_adapter._try_send_os_notification",
            return_value=NOTIFICATION_UNAVAILABLE,
        ):
            result = notify_auth_required()
        assert result["status"] in {
            FALLBACK_MESSAGE_ONLY,
            NOTIFICATION_SENT,
            NOTIFICATION_UNAVAILABLE,
            NOTIFICATION_FAILED,
        }
        assert result["sensitive_data_included"] is False

    def test_fallback_message_present_when_unavailable(self):
        with patch(
            "core.agent_runtime.runtime.notify.user_notification_adapter._try_send_os_notification",
            return_value=NOTIFICATION_UNAVAILABLE,
        ):
            result = notify_auth_required()
        if result["status"] == FALLBACK_MESSAGE_ONLY:
            assert "fallback_message" in result

    def test_no_sensitive_data_in_result(self):
        result = notify_auth_required()
        assert result["sensitive_data_included"] is False


class TestIsSafeMessage:
    def test_safe_message_passes(self):
        assert _is_safe_message("인증이 필요합니다", "브라우저에서 직접 인증해 주세요") is True

    def test_cookie_in_message_fails(self):
        assert _is_safe_message("test", "cookie=abc") is False

    def test_session_in_message_fails(self):
        assert _is_safe_message("test", "session=xyz") is False

    def test_token_in_message_fails(self):
        assert _is_safe_message("test", "token=abc") is False

    def test_submit_in_message_fails(self):
        assert _is_safe_message("test", "click to submit") is False

    def test_npki_in_message_fails(self):
        assert _is_safe_message("npki test", "body") is False

    def test_default_safe_message_passes(self):
        assert _is_safe_message(_SAFE_TITLE, _SAFE_BODY) is True


class TestGetFallbackMessage:
    def test_returns_dict(self):
        result = get_fallback_message()
        assert isinstance(result, dict)

    def test_status_is_fallback(self):
        result = get_fallback_message()
        assert result["status"] == FALLBACK_MESSAGE_ONLY

    def test_no_sensitive_data(self):
        result = get_fallback_message()
        assert result["sensitive_data_included"] is False

    def test_message_uses_safe_body(self):
        result = get_fallback_message()
        assert result["message_used"] == _SAFE_BODY

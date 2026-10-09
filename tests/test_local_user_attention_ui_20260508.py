"""
user attention UI 통합 테스트

인증 필요 → 알림 발송 → 브라우저 포그라운드 → WAITING_USER_AUTH 반환 흐름 검증
"""

from unittest.mock import patch

from core.agent_runtime.runtime.auth.auth_wait_controller import (
    AUTH_SIGNAL_CERT,
    AUTH_SIGNAL_LOGIN,
    AUTH_SIGNAL_OTP,
)
from core.agent_runtime.runtime.notify.user_attention_notifier import (
    build_auth_attention_notice,
    get_notifier_status,
    notify_auth_required,
    request_browser_foreground,
)
from core.agent_runtime.runtime.playwright.browser_foreground_adapter import (
    HEADED_BROWSER_REQUIRED,
)


class TestNotifyAuthRequired:
    def test_returns_waiting_user_auth_status(self):
        result = notify_auth_required(AUTH_SIGNAL_LOGIN)
        assert result["status"] == "WAITING_USER_AUTH"

    def test_notification_status_present(self):
        result = notify_auth_required(AUTH_SIGNAL_LOGIN)
        assert "notification_status" in result

    def test_foreground_status_present(self):
        result = notify_auth_required(AUTH_SIGNAL_LOGIN)
        assert "foreground_status" in result

    def test_message_ko_present(self):
        result = notify_auth_required(AUTH_SIGNAL_LOGIN)
        assert "인증이 필요합니다" in result["message_ko"]

    def test_password_collected_false(self):
        result = notify_auth_required(AUTH_SIGNAL_LOGIN)
        assert result["password_collected"] is False

    def test_otp_collected_false(self):
        result = notify_auth_required(AUTH_SIGNAL_OTP)
        assert result["otp_collected"] is False

    def test_certificate_password_collected_false(self):
        result = notify_auth_required(AUTH_SIGNAL_CERT)
        assert result["certificate_password_collected"] is False

    def test_cookie_exported_false(self):
        result = notify_auth_required(AUTH_SIGNAL_LOGIN)
        assert result["cookie_exported"] is False

    def test_session_exported_false(self):
        result = notify_auth_required(AUTH_SIGNAL_LOGIN)
        assert result["session_exported"] is False

    def test_storage_state_exported_false(self):
        result = notify_auth_required(AUTH_SIGNAL_LOGIN)
        assert result["storage_state_exported"] is False

    def test_sensitive_data_not_included(self):
        result = notify_auth_required(AUTH_SIGNAL_LOGIN)
        assert result["sensitive_data_included"] is False

    def test_no_auto_input_flags(self):
        result = notify_auth_required(AUTH_SIGNAL_LOGIN)
        assert result["password_auto_input"] is False
        assert result["otp_auto_input"] is False
        assert result["cert_password_auto_input"] is False

    def test_no_submit_action_triggered(self):
        result = notify_auth_required(AUTH_SIGNAL_LOGIN)
        assert result["submit_action_triggered"] is False
        assert result["sign_action_triggered"] is False
        assert result["payment_action_triggered"] is False
        assert result["bid_action_triggered"] is False

    def test_headless_mode_sets_foreground_headed_required(self):
        result = notify_auth_required(AUTH_SIGNAL_LOGIN, is_headed=False)
        assert result["foreground_status"] == HEADED_BROWSER_REQUIRED

    def test_notification_failure_does_not_fail_status(self):
        with patch(
            "core.agent_runtime.runtime.notify.user_notification_adapter._try_send_os_notification",
            side_effect=Exception("OS error"),
        ):
            result = notify_auth_required(AUTH_SIGNAL_LOGIN)
        assert result["status"] == "WAITING_USER_AUTH"

    def test_foreground_failure_does_not_fail_status(self):
        with patch(
            "core.agent_runtime.runtime.playwright.browser_foreground_adapter._try_bring_to_foreground",
            side_effect=Exception("win32 error"),
        ):
            result = notify_auth_required(AUTH_SIGNAL_LOGIN)
        assert result["status"] == "WAITING_USER_AUTH"


class TestRequestBrowserForeground:
    def test_returns_dict(self):
        result = request_browser_foreground()
        assert isinstance(result, dict)

    def test_action_field_present(self):
        result = request_browser_foreground()
        assert result["action"] == "bring_browser_to_foreground"

    def test_no_password_read(self):
        result = request_browser_foreground()
        assert result["password_input_read"] is False

    def test_no_sensitive_data_read(self):
        result = request_browser_foreground()
        assert result["sensitive_data_read"] is False

    def test_headless_returns_headed_required(self):
        result = request_browser_foreground(is_headed=False)
        assert result.get("status") == HEADED_BROWSER_REQUIRED


class TestBuildAuthAttentionNotice:
    def test_no_auto_input(self):
        notice = build_auth_attention_notice(AUTH_SIGNAL_LOGIN, timeout_sec=300)
        assert notice["password_auto_input"] is False
        assert notice["otp_auto_input"] is False
        assert notice["cert_password_auto_input"] is False
        assert notice["sensitive_data_included"] is False

    def test_headed_mode_required(self):
        notice = build_auth_attention_notice()
        assert notice["headed_mode_required"] is True
        assert notice["browser_foreground_required"] is True

    def test_message_content(self):
        notice = build_auth_attention_notice()
        assert "인증이 필요합니다" in notice["message_ko"]
        assert "비밀번호" in notice["message_ko"]
        assert "OTP" in notice["message_ko"]
        assert "인증서 비밀번호" in notice["message_ko"]


class TestNotifierStatus:
    def test_os_notification_implemented(self):
        status = get_notifier_status()
        assert status["os_notification_implemented"] is True

    def test_browser_foreground_implemented(self):
        status = get_notifier_status()
        assert status["browser_foreground_implemented"] is True

    def test_os_tray_resident_not_implemented(self):
        status = get_notifier_status()
        assert status["os_tray_resident_implemented"] is False

    def test_os_autostart_not_implemented(self):
        status = get_notifier_status()
        assert status["os_autostart_implemented"] is False


class TestSmoke:
    def test_auth_wait_controller_import_ok(self):
        from core.agent_runtime.runtime.auth.auth_wait_controller import enter_auth_wait

        result = enter_auth_wait("smoke-task", AUTH_SIGNAL_LOGIN)
        assert result["status"] in {"WAITING_USER_AUTH", "USER_ACTION_REQUIRED"}

    def test_auto_resume_import_ok(self):
        from core.agent_runtime.runtime.auth.auto_resume_after_auth import can_auto_resume

        assert can_auto_resume("read_page") is True
        assert can_auto_resume("final_submit") is False

    def test_session_boundary_import_ok(self):
        from core.agent_runtime.runtime.local_session_boundary import get_boundary_safe_defaults, is_safe_for_export

        result = get_boundary_safe_defaults()
        result["ok"] = True
        assert is_safe_for_export(result) is True

    def test_playwright_runner_imports_ok(self):
        from core.agent_runtime.runtime.playwright import playwright_runner

        assert hasattr(playwright_runner, "run_task")

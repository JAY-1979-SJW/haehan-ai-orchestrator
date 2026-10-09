"""
browser_foreground_adapter 테스트
"""

from unittest.mock import patch

from core.agent_runtime.runtime.playwright.browser_foreground_adapter import (
    BROWSER_FOREGROUND_REQUESTED,
    BROWSER_FOREGROUND_UNAVAILABLE,
    HEADED_BROWSER_REQUIRED,
    USER_MANUAL_FOCUS_REQUIRED,
    get_foreground_status,
    request_foreground,
)


class TestRequestForeground:
    def test_headless_returns_headed_required(self):
        result = request_foreground(is_headed=False)
        assert result["status"] == HEADED_BROWSER_REQUIRED

    def test_headless_no_password_read(self):
        result = request_foreground(is_headed=False)
        assert result["password_input_read"] is False
        assert result["input_value_read"] is False

    def test_headless_no_sensitive_data(self):
        result = request_foreground(is_headed=False)
        assert result["sensitive_data_read"] is False

    def test_headless_message_includes_manual_guidance(self):
        result = request_foreground(is_headed=False)
        assert "브라우저" in result["message_ko"]

    def test_headed_no_pid_returns_manual(self):
        result = request_foreground(is_headed=True, browser_pid=None)
        assert result["status"] in {
            BROWSER_FOREGROUND_REQUESTED,
            BROWSER_FOREGROUND_UNAVAILABLE,
            USER_MANUAL_FOCUS_REQUIRED,
        }

    def test_headed_no_password_read(self):
        result = request_foreground(is_headed=True)
        assert result["password_input_read"] is False
        assert result["input_value_read"] is False

    def test_headed_no_sensitive_data(self):
        result = request_foreground(is_headed=True)
        assert result["sensitive_data_read"] is False

    def test_browser_profile_not_modified(self):
        result = request_foreground(is_headed=True)
        assert result["browser_profile_modified"] is False

    def test_headed_with_invalid_pid_graceful(self):
        result = request_foreground(is_headed=True, browser_pid=99999999)
        assert result["status"] in {
            BROWSER_FOREGROUND_REQUESTED,
            BROWSER_FOREGROUND_UNAVAILABLE,
            USER_MANUAL_FOCUS_REQUIRED,
        }
        assert result["sensitive_data_read"] is False

    def test_windows_foreground_with_mock_pid(self):
        with (
            patch("sys.platform", "win32"),
            patch(
                "core.agent_runtime.runtime.playwright.browser_foreground_adapter._foreground_windows",
                return_value=BROWSER_FOREGROUND_REQUESTED,
            ),
        ):
            result = request_foreground(is_headed=True, browser_pid=1234)
        assert result["status"] == BROWSER_FOREGROUND_REQUESTED
        assert result["sensitive_data_read"] is False

    def test_unsupported_platform_returns_unavailable_or_manual(self):
        with patch("sys.platform", "freebsd"):
            result = request_foreground(is_headed=True, browser_pid=1234)
        assert result["status"] in {
            USER_MANUAL_FOCUS_REQUIRED,
            BROWSER_FOREGROUND_UNAVAILABLE,
            BROWSER_FOREGROUND_REQUESTED,
        }


class TestGetForegroundStatus:
    def test_returns_dict(self):
        result = get_foreground_status()
        assert isinstance(result, dict)

    def test_no_sensitive_data(self):
        result = get_foreground_status()
        assert result["sensitive_data_read"] is False
        assert result["password_input_read"] is False

    def test_platform_present(self):
        result = get_foreground_status()
        assert "platform" in result

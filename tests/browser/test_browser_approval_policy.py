"""BROWSER-3: Approval-gated execution policy tests (unit tests with mocks).

This test module verifies the approval and risk detection policies
without requiring a running Playwright browser instance.

Tests:
1. execute_click requires approval_token
2. execute_type requires approval_token
3. Risky buttons require final_approval_token
4. Sensitive fields rejected in execute_type
5. Result data is safe (no secrets)
6. Risk assessment identifies risky buttons
7. Sensitive field detection works

Execution:
  pytest tests/test_browser_approval_policy.py -v
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from core.agent_runtime.browser.browser_controller import (
    BrowserController,
    ExecuteClickResult,
    ExecuteTypeResult,
)


def run_async(coro):
    """Run async function using asyncio.run."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestApprovalPolicy:
    """Tests for approval token policy."""

    @pytest.fixture
    def controller(self):
        """Create a controller with mock page."""
        controller = BrowserController("test-agent")
        controller.page = AsyncMock()
        controller.page.url = "http://localhost:8000"
        controller.page.query_selector = AsyncMock()
        controller.page.text_content = AsyncMock()
        controller.page.get_attribute = AsyncMock()
        controller.page.fill = AsyncMock()
        controller.page.type = AsyncMock()
        return controller

    def test_execute_click_without_approval_rejected(self, controller):
        """execute_click without approval_token should be rejected."""

        async def _test():
            # Setup mock element
            mock_element = AsyncMock()
            mock_element.text_content = AsyncMock(return_value="Click me")
            controller.page.query_selector.return_value = mock_element

            result = await controller.execute_click("#test-btn", approval_token=None)

            assert result.element_found is True
            assert result.executed is False
            assert result.result == "approval_denied"

        run_async(_test())

    def test_execute_type_without_approval_rejected(self, controller):
        """execute_type without approval_token should be rejected."""

        async def _test():
            # Setup mock element
            mock_element = AsyncMock()
            mock_element.get_attribute = AsyncMock(return_value="text")
            controller.page.query_selector.return_value = mock_element

            result = await controller.execute_type("#test-input", "test text", approval_token=None)

            assert result.element_found is True
            assert result.executed is False
            assert result.result == "approval_denied"

        run_async(_test())

    def test_execute_click_with_approval_on_normal_button(self, controller):
        """execute_click with approval should execute on normal button."""

        async def _test():
            # Setup mock element
            mock_element = AsyncMock()
            mock_element.text_content = AsyncMock(return_value="Click me")
            mock_element.evaluate = AsyncMock(return_value="button")
            controller.page.query_selector.return_value = mock_element

            result = await controller.execute_click("#test-btn", approval_token="test-token")

            assert result.element_found is True
            assert result.executed is True
            assert result.result == "success"
            assert result.risk_level == "low"

        run_async(_test())

    def test_execute_type_with_approval_on_normal_input(self, controller):
        """execute_type with approval should execute on normal input."""

        async def _test():
            # Setup mock element
            mock_element = AsyncMock()
            mock_element.get_attribute = AsyncMock(
                side_effect=lambda attr: {
                    "type": "text",
                    "name": "search",
                    "placeholder": "Search",
                    "aria-label": None,
                }.get(attr, "")
            )
            controller.page.query_selector.return_value = mock_element

            result = await controller.execute_type("#search-input", "test query", approval_token="test-token")

            assert result.element_found is True
            assert result.executed is True
            assert result.result == "success"
            assert result.text_length == 10
            assert result.text_preview == "[REDACTED]"
            assert "test query" not in str(result)

        run_async(_test())

    def test_execute_click_submit_requires_final_approval(self, controller):
        """execute_click on submit button requires final_approval_token."""

        async def _test():
            # Setup mock element for submit button
            mock_element = AsyncMock()
            mock_element.text_content = AsyncMock(return_value="Submit Form")
            controller.page.query_selector.return_value = mock_element

            result = await controller.execute_click(
                "#submit-btn", approval_token="test-token", final_approval_token=None
            )

            assert result.element_found is True
            assert result.executed is False
            assert result.final_approval_required is True
            assert result.result == "risky_element"

        run_async(_test())

    def test_execute_click_delete_requires_final_approval(self, controller):
        """execute_click on delete button requires final_approval_token."""

        async def _test():
            # Setup mock element for delete button
            mock_element = AsyncMock()
            mock_element.text_content = AsyncMock(return_value="Delete Item")
            controller.page.query_selector.return_value = mock_element

            result = await controller.execute_click(
                "#delete-btn", approval_token="test-token", final_approval_token=None
            )

            assert result.element_found is True
            assert result.executed is False
            assert result.final_approval_required is True
            assert result.result == "risky_element"

        run_async(_test())

    def test_execute_type_password_field_rejected(self, controller):
        """execute_type on password field should be rejected."""

        async def _test():
            # Setup mock password input
            mock_element = AsyncMock()
            mock_element.get_attribute = AsyncMock(
                side_effect=lambda attr: {
                    "type": "password",
                    "name": "password",
                    "placeholder": "Password",
                    "aria-label": None,
                }.get(attr, "")
            )
            controller.page.query_selector.return_value = mock_element

            result = await controller.execute_type("#password-input", "secret123", approval_token="test-token")

            assert result.element_found is True
            assert result.executed is False
            assert result.result == "sensitive_field"
            assert result.field_type == "password"

        run_async(_test())

    def test_execute_type_otp_field_rejected(self, controller):
        """execute_type on OTP field should be rejected."""

        async def _test():
            # Setup mock OTP input
            mock_element = AsyncMock()
            mock_element.get_attribute = AsyncMock(
                side_effect=lambda attr: {
                    "type": "text",
                    "name": "otp_code",
                    "placeholder": "OTP Code",
                    "aria-label": None,
                }.get(attr, "")
            )
            controller.page.query_selector.return_value = mock_element

            result = await controller.execute_type("#otp-input", "123456", approval_token="test-token")

            assert result.element_found is True
            assert result.executed is False
            assert result.result == "sensitive_field"

        run_async(_test())

    def test_result_no_raw_text_in_dict(self, controller):
        """Result should not contain raw text in __dict__."""
        result = ExecuteTypeResult(
            selector="#input",
            element_found=True,
            executed=True,
            field_type="text",
            text_length=16,
            text_preview="[REDACTED]",
            result="success",
            target_url_domain="localhost",
        )

        result_str = str(result.__dict__)
        assert "sensitive search query" not in result_str
        assert "[REDACTED]" in result_str

    def test_result_no_approval_token(self, controller):
        """Result should not contain approval_token."""
        result = ExecuteClickResult(
            selector="#btn", element_found=True, executed=True, result="success", target_url_domain="localhost"
        )

        result_str = str(result)
        assert "approval_token" not in result_str.lower()


class TestRiskAssessment:
    """Tests for risk assessment in click actions."""

    @pytest.fixture
    def controller(self):
        """Create a controller."""
        return BrowserController("test-agent")

    def test_assess_click_risk_submit_is_risky(self, controller):
        """submit button should be detected as risky."""
        risk_level, is_risky = controller._assess_click_risk("Submit Form", "#submit-btn")
        assert is_risky is True
        assert risk_level == "high"

    def test_assess_click_risk_delete_is_risky(self, controller):
        """delete button should be detected as risky."""
        risk_level, is_risky = controller._assess_click_risk("Delete Item", "#delete-btn")
        assert is_risky is True
        assert risk_level == "high"

    def test_assess_click_risk_payment_is_risky(self, controller):
        """payment button should be detected as risky."""
        _risk_level, is_risky = controller._assess_click_risk("Proceed to Payment", "#checkout")
        assert is_risky is True

    def test_assess_click_risk_comment_is_risky(self, controller):
        """comment button should be detected as risky."""
        _risk_level, is_risky = controller._assess_click_risk("Post Comment", "#comment-btn")
        assert is_risky is True

    def test_assess_click_risk_normal_is_safe(self, controller):
        """normal button should not be risky."""
        risk_level, is_risky = controller._assess_click_risk("Click me", "#normal-btn")
        assert is_risky is False
        assert risk_level == "low"

    def test_assess_click_risk_korean_submit_is_risky(self, controller):
        """Korean submit keyword should be detected as risky."""
        _risk_level, is_risky = controller._assess_click_risk("제출하기", "#submit-btn")
        assert is_risky is True

    def test_assess_click_risk_korean_delete_is_risky(self, controller):
        """Korean delete keyword should be detected as risky."""
        _risk_level, is_risky = controller._assess_click_risk("삭제", "#delete-btn")
        assert is_risky is True


class TestSensitiveFieldDetection:
    """Tests for sensitive field detection."""

    @pytest.fixture
    def controller(self):
        """Create a controller."""
        return BrowserController("test-agent")

    def test_password_type_is_sensitive(self, controller):
        """input[type=password] should be sensitive."""
        is_sensitive = controller._is_sensitive_field("password", "", "", "")
        assert is_sensitive is True

    def test_hidden_type_is_sensitive(self, controller):
        """input[type=hidden] should be sensitive."""
        is_sensitive = controller._is_sensitive_field("hidden", "", "", "")
        assert is_sensitive is True

    def test_password_name_is_sensitive(self, controller):
        """field with name='password' should be sensitive."""
        is_sensitive = controller._is_sensitive_field("text", "password", "", "")
        assert is_sensitive is True

    def test_otp_name_is_sensitive(self, controller):
        """field with name='otp_code' should be sensitive."""
        is_sensitive = controller._is_sensitive_field("text", "otp_code", "", "")
        assert is_sensitive is True

    def test_verification_placeholder_is_sensitive(self, controller):
        """field with placeholder containing 'verification' should be sensitive."""
        is_sensitive = controller._is_sensitive_field("text", "", "Verification Code", "")
        assert is_sensitive is True

    def test_auth_aria_label_is_sensitive(self, controller):
        """field with aria-label containing 'code' should be sensitive."""
        is_sensitive = controller._is_sensitive_field("text", "", "", "Verification Code")
        assert is_sensitive is True

    def test_normal_text_input_not_sensitive(self, controller):
        """normal text input should not be sensitive."""
        is_sensitive = controller._is_sensitive_field("text", "search", "Search...", "")
        assert is_sensitive is False

    def test_email_input_not_sensitive(self, controller):
        """email input should not be sensitive."""
        is_sensitive = controller._is_sensitive_field("email", "email", "Email", "")
        assert is_sensitive is False

    def test_korean_password_is_sensitive(self, controller):
        """Korean word '비밀번호' should be detected as sensitive."""
        is_sensitive = controller._is_sensitive_field("text", "비밀번호", "", "")
        assert is_sensitive is True

    def test_korean_auth_is_sensitive(self, controller):
        """Korean word '인증번호' should be detected as sensitive."""
        is_sensitive = controller._is_sensitive_field("text", "인증번호", "", "")
        assert is_sensitive is True


class TestExtractDomain:
    """Tests for domain extraction from URLs."""

    @pytest.fixture
    def controller(self):
        """Create a controller."""
        return BrowserController("test-agent")

    def test_extract_domain_http(self, controller):
        """Extract domain from http URL."""
        domain = controller._extract_domain("http://example.com/path")
        assert domain == "example.com"

    def test_extract_domain_https(self, controller):
        """Extract domain from https URL."""
        domain = controller._extract_domain("https://example.com/path")
        assert domain == "example.com"

    def test_extract_domain_with_port(self, controller):
        """Extract domain from URL with port."""
        domain = controller._extract_domain("http://localhost:8000/path")
        assert domain == "localhost:8000"

    def test_extract_domain_file_url(self, controller):
        """file:// URL should return empty domain."""
        domain = controller._extract_domain("file:///path/to/file.html")
        assert domain == ""

    def test_extract_domain_invalid_url(self, controller):
        """Invalid URL should return empty domain."""
        domain = controller._extract_domain("not a valid url")
        assert domain == ""

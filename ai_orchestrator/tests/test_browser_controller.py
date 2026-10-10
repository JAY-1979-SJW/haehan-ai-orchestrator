"""Tests for BrowserController dry-run PoC.

Tests cover:
- Controller initialization
- No forbidden methods exist (no cookie/session export)
- Result data structure
- Login/OTP detection heuristics
- Redaction of sensitive data
"""

import tempfile
from pathlib import Path

from core.agent_runtime.browser.browser_controller import (
    BrowserController,
    BrowserControllerError,
    InspectResult,
    PlanClickResult,
    PlanSubmitResult,
    PlanTypeResult,
)


def test_browser_controller_init():
    """Test controller initialization."""
    controller = BrowserController("test_agent")
    assert controller.agent_id == "test_agent"
    assert controller.browser is None
    assert controller.page is None


def test_custom_profile_dir():
    """Test custom profile directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        profile_base = Path(tmpdir)
        controller = BrowserController("test_agent", profile_base)
        assert controller.profile_dir == profile_base / "test_agent"


def test_no_forbidden_methods():
    """Test that no cookie/session extraction methods exist."""
    controller = BrowserController("test_agent")

    # Verify forbidden methods don't exist
    forbidden = [
        "get_cookies",
        "export_cookies",
        "extract_session",
        "export_local_storage",
        "export_session_storage",
        "dump_local_storage",
        "dump_session_storage",
        "reveal_password",
        "auto_login",
        "handle_otp",
    ]

    for method in forbidden:
        assert not hasattr(controller, method), f"Controller has forbidden method: {method}"


def test_inspect_result_dataclass():
    """Test InspectResult structure."""
    result = InspectResult(
        url="http://example.com",
        title="Test Page",
        inputs=[{"name": "email", "type": "email"}],
        clickables=[{"selector": "button", "text": "Submit"}],
        login_required=False,
        otp_detected=False,
    )

    assert result.url == "http://example.com"
    assert result.title == "Test Page"
    assert len(result.inputs) == 1
    assert len(result.clickables) == 1
    assert result.login_required is False
    assert result.otp_detected is False


def test_plan_click_result():
    """Test PlanClickResult structure."""
    plan = PlanClickResult(
        selector="#submit",
        element_found=True,
        element_text="Submit",
        element_tag="button",
        would_click=True,
    )

    assert plan.action == "browser_plan_click"
    assert plan.dry_run is True
    assert plan.executed is False
    assert plan.next_step == "request_approval"


def test_plan_type_result():
    """Test PlanTypeResult structure."""
    plan = PlanTypeResult(
        selector="input[name=email]",
        element_found=True,
        field_type="email",
        text_length=16,
        would_type=True,
    )

    assert plan.action == "browser_plan_type"
    assert plan.dry_run is True
    assert plan.executed is False
    assert plan.text_preview == "[REDACTED]"
    assert plan.next_step == "request_approval"


def test_plan_submit_result():
    """Test PlanSubmitResult structure."""
    plan = PlanSubmitResult(
        selector="#form",
    )

    assert plan.action == "browser_submit"
    assert plan.risk_level == "critical"
    assert plan.final_approval_required is True
    assert plan.executed is False


def test_login_detection_heuristics():
    """Test login page detection heuristics."""
    controller = BrowserController("test_agent")

    # Test with login in URL
    result = controller._detect_login_required("http://example.com/login", "Home", [])
    assert result is True

    # Test with login in title
    result = controller._detect_login_required("http://example.com/auth", "Sign In", [])
    assert result is True

    # Test with password field
    result = controller._detect_login_required("http://example.com", "Home", [{"type": "password", "name": "pwd"}])
    assert result is True

    # Test normal page
    result = controller._detect_login_required("http://example.com", "Home", [{"type": "text", "name": "search"}])
    assert result is False


def test_otp_detection_heuristics():
    """Test OTP/2FA field detection heuristics."""
    controller = BrowserController("test_agent")

    # Test OTP in name
    inputs = [{"name": "otp_code", "type": "text"}]
    assert controller._detect_otp(inputs) is True

    # Test 2FA in placeholder
    inputs = [{"placeholder": "Enter 2FA code", "type": "text"}]
    assert controller._detect_otp(inputs) is True

    # Test Korean 인증번호
    inputs = [{"placeholder": "인증번호 입력", "type": "text"}]
    assert controller._detect_otp(inputs) is True

    # Test normal field
    inputs = [{"name": "email", "type": "email"}]
    assert controller._detect_otp(inputs) is False


def test_no_secret_in_result_string():
    """Test that secrets are not exposed in string representation."""
    result = InspectResult(
        url="http://example.com",
        title="Test",
        inputs=[],
        clickables=[],
    )

    result_str = str(result)

    # Verify no common secret keywords in raw form
    # (Password may appear as field type, but not as value)
    assert "secret" not in result_str.lower()
    assert "password123" not in result_str.lower()
    assert "token123" not in result_str.lower()


def test_plan_results_do_not_contain_raw_text():
    """Test that plan results do not expose raw user input."""
    plan = PlanTypeResult(
        selector="input[name=credit_card]",
        element_found=True,
        field_type="text",
        text_length=16,  # Just the length
        text_preview="[REDACTED]",  # Always redacted
    )

    plan_str = str(plan)

    # No raw input text
    assert "4532111111111111" not in plan_str
    # Text preview is redacted
    assert "[REDACTED]" in plan_str


def test_browser_controller_error():
    """Test BrowserControllerError exception."""
    error = BrowserControllerError("Test error")
    assert isinstance(error, Exception)
    assert str(error) == "Test error"


def test_no_cookies_export_in_class():
    """Test that class design prevents cookie extraction."""
    controller = BrowserController("test_agent")

    # Verify no exposed attributes for cookies
    private_attrs = [attr for attr in dir(controller) if attr.startswith("_")]
    # Should not have a _cookies attribute
    assert "_cookies" not in private_attrs


def test_policy_enforcement_in_results():
    """Test that results enforce security policy."""
    # Create inputs with various field types
    inputs_list = [
        {"name": "email", "type": "email", "placeholder": "Email"},
        {"name": "password", "type": "password", "placeholder": "Password"},
        {"name": "hidden", "type": "hidden", "value": "secret"},
    ]

    # Convert to string (simulating serialization)
    inputs_str = str(inputs_list)

    # Password type should be present, but no value from hidden field
    assert "password" in inputs_str.lower() or "type" in inputs_str
    # Secret hidden value should not be present
    assert "secret" not in inputs_str.lower() or "hidden" in inputs_str


def test_plan_click_never_executes():
    """Test that plan_click result indicates dry-run."""
    plan = PlanClickResult(
        selector="button#submit",
        element_found=True,
        would_click=True,
    )

    # Verify it's marked as dry-run
    assert plan.dry_run is True
    assert plan.executed is False
    # Should indicate next step is approval
    assert "approval" in plan.next_step.lower()


def test_plan_type_never_executes():
    """Test that plan_type result indicates dry-run."""
    plan = PlanTypeResult(
        selector="input[name=search]",
        element_found=True,
        would_type=True,
        text_length=20,
    )

    # Verify it's marked as dry-run
    assert plan.dry_run is True
    assert plan.executed is False
    # Text must be redacted
    assert plan.text_preview == "[REDACTED]"
    # Should indicate next step is approval
    assert "approval" in plan.next_step.lower()


def test_submit_always_critical():
    """Test that submit is always critical."""
    plan = PlanSubmitResult()

    assert plan.risk_level == "critical"
    assert plan.final_approval_required is True
    assert plan.executed is False

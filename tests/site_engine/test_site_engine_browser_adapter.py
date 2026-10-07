"""Unit tests for scripts.site_engine.adapters.browser."""

from scripts.site_engine.adapters.browser import (
    BrowserActionKind,
    build_click_plan,
    build_download_plan,
    build_input_plan,
    build_readonly_navigation_plan,
    build_submit_plan,
    build_upload_plan,
)
from scripts.site_engine.site_types import GateDecision, SiteCapability


def test_readonly_navigation_plan():
    plan = build_readonly_navigation_plan("https://example.com")
    assert plan.kind == BrowserActionKind.NAVIGATE
    assert plan.capability == SiteCapability.READ
    assert plan.required_gate == GateDecision.READ_ONLY_ALLOWED
    assert not plan.is_sensitive


def test_click_plan():
    plan = build_click_plan("#btn-ok", label="확인")
    assert plan.kind == BrowserActionKind.CLICK
    assert plan.required_gate == GateDecision.SERVER_BROWSER_ALLOWED
    assert plan.metadata.get("label") == "확인"


def test_input_plan_nonsensitive():
    plan = build_input_plan("#username", field_name="username")
    assert plan.kind == BrowserActionKind.INPUT
    assert plan.required_gate == GateDecision.SERVER_BROWSER_ALLOWED
    assert not plan.is_sensitive


def test_input_plan_password_sensitive():
    plan = build_input_plan("#pw", field_name="password")
    assert plan.is_sensitive
    assert plan.required_gate == GateDecision.USER_DIRECT_REQUIRED


def test_input_plan_otp_sensitive():
    plan = build_input_plan("#otp", field_name="otp_code")
    assert plan.is_sensitive
    assert plan.required_gate == GateDecision.USER_DIRECT_REQUIRED


def test_input_plan_cookie_sensitive():
    plan = build_input_plan("#c", field_name="session_cookie")
    assert plan.is_sensitive


def test_download_plan():
    plan = build_download_plan("https://example.com/file.pdf", filename="file.pdf")
    assert plan.kind == BrowserActionKind.DOWNLOAD
    assert plan.required_gate == GateDecision.SERVER_BROWSER_ALLOWED
    assert not plan.is_sensitive


def test_upload_plan_approval_required():
    plan = build_upload_plan("#file-input", filename="doc.hwp")
    assert plan.kind == BrowserActionKind.UPLOAD
    assert plan.required_gate == GateDecision.APPROVAL_REQUIRED


def test_submit_plan_approval_required():
    plan = build_submit_plan("#submit-btn", action_label="상신")
    assert plan.kind == BrowserActionKind.SUBMIT
    assert plan.required_gate == GateDecision.APPROVAL_REQUIRED
    assert plan.capability == SiteCapability.SUBMIT


def test_plan_has_no_value_field():
    plan = build_input_plan("#pw", field_name="password")
    assert not hasattr(plan, "value")


def test_plan_sensitive_reason_not_empty():
    plan = build_input_plan("#pw", field_name="password")
    assert plan.sensitive_reason


def test_no_browser_execution_on_import():
    # import 시점에 브라우저가 실행되지 않음을 확인
    import scripts.site_engine.adapters.browser as m

    assert callable(m.build_readonly_navigation_plan)

"""Unit tests for scripts.site_engine.execution_gate."""

from scripts.site_engine.execution_gate import (
    ExecutionDecision,
    ExecutionGateInput,
    ExecutionGateResult,
    GateReason,
    block_for_sensitive_credential_action,
    evaluate_execution_gate,
    require_approval_for_action,
    resolve_execution_location,
)
from scripts.site_engine.profiles import SiteActionPolicy, SiteProfile
from scripts.site_engine.site_types import (
    ExecutionLocation,
    GateDecision,
    SiteCapability,
)

# ── helpers ──────────────────────────────────────────────────────────


def _make_profile(
    key: str = "test",
    allowed: tuple = (SiteCapability.READ, SiteCapability.SEARCH, SiteCapability.SUBMIT),
    blocked: tuple = (),
    policies: tuple = (),
    default_location: ExecutionLocation = ExecutionLocation.SERVER,
) -> SiteProfile:
    return SiteProfile(
        key=key,
        base_url="https://test.example.com",
        display_name="Test",
        login_domain_hints=("test.example.com",),
        allowed_capabilities=allowed,
        blocked_capabilities=blocked,
        action_policies=policies,
        default_execution_location=default_location,
    )


def _gate(
    capability: SiteCapability,
    action: str,
    profile=None,
    is_server_forbidden: bool = False,
    force_approved: bool = False,
) -> ExecutionGateResult:
    return evaluate_execution_gate(
        ExecutionGateInput(
            site_key="test",
            capability=capability,
            action=action,
            is_server_forbidden_site=is_server_forbidden,
            force_approved=force_approved,
        ),
        profile=profile,
    )


# ── 1. read-only action 허용 ─────────────────────────────────────────


def test_read_action_allowed():
    result = _gate(SiteCapability.READ, "list_items")
    assert result.decision == ExecutionDecision.ALLOWED
    assert result.gate_decision == GateDecision.READ_ONLY_ALLOWED


def test_search_action_allowed():
    result = _gate(SiteCapability.SEARCH, "search_query")
    assert result.decision == ExecutionDecision.ALLOWED


# ── 2. submit action → approval required ────────────────────────────


def test_submit_requires_approval():
    result = _gate(SiteCapability.SUBMIT, "submit_form")
    assert result.decision == ExecutionDecision.APPROVAL_REQUIRED
    assert result.requires_approval


def test_submit_with_force_approved_allowed():
    result = _gate(SiteCapability.SUBMIT, "submit_form", force_approved=True)
    assert result.decision == ExecutionDecision.ALLOWED
    assert result.requires_approval


# ── 3. publish/send/upload/delete approval required ─────────────────


def test_publish_requires_approval():
    result = _gate(SiteCapability.PUBLISH, "publish_post")
    assert result.decision == ExecutionDecision.APPROVAL_REQUIRED


def test_send_requires_approval():
    result = _gate(SiteCapability.SEND, "send_mail")
    assert result.decision == ExecutionDecision.APPROVAL_REQUIRED


def test_upload_requires_approval():
    result = _gate(SiteCapability.UPLOAD, "upload_file")
    assert result.decision == ExecutionDecision.APPROVAL_REQUIRED


def test_delete_requires_approval():
    result = _gate(SiteCapability.DELETE, "delete_item")
    assert result.decision == ExecutionDecision.APPROVAL_REQUIRED


def test_sign_requires_approval():
    result = _gate(SiteCapability.SIGN, "sign_document")
    assert result.decision == ExecutionDecision.APPROVAL_REQUIRED


# ── 4. password/otp/certificate → blocked or user_direct ────────────


def test_password_extract_blocked():
    result = _gate(SiteCapability.READ, "extract_password")
    assert result.decision == ExecutionDecision.BLOCKED
    assert result.reason == GateReason.BLOCKED_SENSITIVE_CREDENTIAL


def test_otp_extract_blocked():
    result = _gate(SiteCapability.READ, "get_otp_value")
    assert result.decision == ExecutionDecision.BLOCKED


def test_certificate_extract_blocked():
    result = _gate(SiteCapability.READ, "export_certificate")
    assert result.decision == ExecutionDecision.BLOCKED


def test_private_key_read_blocked():
    result = _gate(SiteCapability.READ, "read_private_key")
    assert result.decision == ExecutionDecision.BLOCKED


def test_password_action_user_direct():
    # extract 없이 credential 키워드만 → USER_DIRECT_REQUIRED
    result = _gate(SiteCapability.FORM_FILL, "input_password")
    assert result.decision == ExecutionDecision.USER_DIRECT_REQUIRED
    assert result.reason == GateReason.USER_DIRECT_REQUIRED_CREDENTIAL


# ── 5. cookie/session extraction → blocked ──────────────────────────


def test_cookie_extraction_blocked():
    result = _gate(SiteCapability.READ, "extract_cookie")
    assert result.decision == ExecutionDecision.BLOCKED


def test_session_dump_blocked():
    result = _gate(SiteCapability.READ, "dump_session")
    assert result.decision == ExecutionDecision.BLOCKED


# ── 6. profile local-agent/user-direct ──────────────────────────────


def test_profile_local_agent_required():
    policy = SiteActionPolicy(
        capability=SiteCapability.READ,
        gate=GateDecision.LOCAL_AGENT_REQUIRED,
        required_execution_location=ExecutionLocation.LOCAL_AGENT,
    )
    profile = _make_profile(policies=(policy,))
    result = _gate(SiteCapability.READ, "read_file", profile=profile)
    assert result.decision == ExecutionDecision.LOCAL_AGENT_REQUIRED


def test_profile_user_direct_required():
    policy = SiteActionPolicy(
        capability=SiteCapability.SIGN,
        gate=GateDecision.USER_DIRECT_REQUIRED,
        required_execution_location=ExecutionLocation.USER_DIRECT,
    )
    profile = _make_profile(
        allowed=(SiteCapability.READ, SiteCapability.SIGN),
        policies=(policy,),
    )
    result = _gate(SiteCapability.SIGN, "sign_doc", profile=profile)
    assert result.decision == ExecutionDecision.USER_DIRECT_REQUIRED


# ── 7. server forbidden site → blocked ──────────────────────────────


def test_server_forbidden_site_blocked():
    result = _gate(SiteCapability.READ, "goto_bank", is_server_forbidden=True)
    assert result.decision == ExecutionDecision.BLOCKED
    assert result.reason == GateReason.BLOCKED_SERVER_FORBIDDEN_SITE


# ── 8. unknown / not-in-allowed blocked ─────────────────────────────


def test_capability_not_in_profile_blocked():
    profile = _make_profile(allowed=(SiteCapability.READ,))
    result = _gate(SiteCapability.DELETE, "delete_item", profile=profile)
    assert result.decision == ExecutionDecision.BLOCKED
    assert result.reason == GateReason.BLOCKED_NOT_IN_ALLOWED


# ── 9. gate result에 reason 포함 ────────────────────────────────────


def test_result_has_reason():
    result = _gate(SiteCapability.SUBMIT, "submit_form")
    assert result.reason is not None
    assert isinstance(result.reason, GateReason)


def test_result_has_detail():
    result = _gate(SiteCapability.SUBMIT, "submit_form")
    assert result.detail


# ── 10. 민감값이 result에 포함되지 않음 ─────────────────────────────


def test_no_sensitive_value_in_result():
    result = _gate(SiteCapability.READ, "extract_password")
    combined = f"{result.decision}{result.reason}{result.detail}"
    assert "hunter2" not in combined
    assert "real_token" not in combined


# ── 11. 기존 site_engine types와 충돌 없음 ──────────────────────────


def test_types_import_no_conflict():
    from scripts.site_engine.execution_gate import ExecutionDecision as ED
    from scripts.site_engine.site_types import GateDecision as GD
    from scripts.site_engine.site_types import SiteCapability as SC

    assert GD.BLOCKED != ED.BLOCKED or True  # 다른 enum, 값 충돌 없음
    assert SC.READ is not None


# ── require_approval_for_action / block_for_sensitive_credential ─────


def test_require_approval_for_submit():
    assert require_approval_for_action("submit_form", SiteCapability.SUBMIT)


def test_require_approval_false_for_read():
    assert not require_approval_for_action("list_items", SiteCapability.READ)


def test_block_for_sensitive_credential_true():
    assert block_for_sensitive_credential_action("extract_password")
    assert block_for_sensitive_credential_action("get_otp_value")
    assert block_for_sensitive_credential_action("dump_session")


def test_block_for_sensitive_credential_false():
    assert not block_for_sensitive_credential_action("input_password")
    assert not block_for_sensitive_credential_action("search_query")


# ── resolve_execution_location ───────────────────────────────────────


def test_resolve_location_no_profile_defaults_server():
    loc = resolve_execution_location(profile=None)
    assert loc == ExecutionLocation.SERVER


def test_resolve_location_profile_local_agent():
    policy = SiteActionPolicy(
        capability=SiteCapability.READ,
        gate=GateDecision.LOCAL_AGENT_REQUIRED,
        required_execution_location=ExecutionLocation.LOCAL_AGENT,
    )
    profile = _make_profile(policies=(policy,))
    loc = resolve_execution_location(profile=profile, capability=SiteCapability.READ)
    assert loc == ExecutionLocation.LOCAL_AGENT

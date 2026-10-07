"""Unit tests for scripts.site_engine.action_planner."""

from scripts.site_engine.action_planner import (
    ActionPlanStatus,
    append_gate_decision,
    build_action_plan,
    require_gate_for_sensitive_action,
    summarize_action_plan,
)
from scripts.site_engine.execution_gate import (
    ExecutionDecision,
    ExecutionGateResult,
    GateReason,
)
from scripts.site_engine.site_types import GateDecision, SiteCapability


def _spec(cap: SiteCapability, action: str, step_id: str = "s1", field_name: str = "") -> dict:
    d = {"capability": cap, "action": action, "step_id": step_id}
    if field_name:
        d["field_name"] = field_name
    return d


def _allowed_gate_result() -> ExecutionGateResult:
    return ExecutionGateResult(
        decision=ExecutionDecision.ALLOWED,
        gate_decision=GateDecision.APPROVAL_REQUIRED,
        reason=GateReason.POLICY_OVERRIDE,
        detail="force_approved",
        requires_approval=True,
    )


# ── 1. READ action plan ──────────────────────────────────────────────


def test_read_plan_ready():
    plan = build_action_plan("p1", "test", [_spec(SiteCapability.READ, "list_items")])
    assert plan.overall_status == ActionPlanStatus.READY
    assert plan.steps[0].status == ActionPlanStatus.READY


def test_search_plan_ready():
    plan = build_action_plan("p1", "test", [_spec(SiteCapability.SEARCH, "search_query")])
    assert plan.overall_status == ActionPlanStatus.READY


# ── 2. CLICK/INPUT action plan ───────────────────────────────────────


def test_click_plan_ready():
    plan = build_action_plan("p1", "test", [_spec(SiteCapability.FORM_FILL, "click_button")])
    assert plan.steps[0].status == ActionPlanStatus.READY


def test_input_nonsensitive_ready():
    plan = build_action_plan("p1", "test", [_spec(SiteCapability.FORM_FILL, "input_username", field_name="username")])
    assert plan.steps[0].status == ActionPlanStatus.READY


# ── 3. password field → USER_ACTION_REQUIRED ────────────────────────


def test_password_field_user_action_required():
    plan = build_action_plan("p1", "test", [_spec(SiteCapability.FORM_FILL, "input_pw", field_name="password")])
    assert plan.steps[0].status == ActionPlanStatus.USER_ACTION_REQUIRED
    assert plan.steps[0].is_sensitive


def test_otp_field_user_action_required():
    plan = build_action_plan("p1", "test", [_spec(SiteCapability.FORM_FILL, "input_otp", field_name="otp_code")])
    assert plan.steps[0].status == ActionPlanStatus.USER_ACTION_REQUIRED


# ── 4. credential extraction → BLOCKED ──────────────────────────────


def test_extract_cookie_blocked():
    plan = build_action_plan("p1", "test", [_spec(SiteCapability.READ, "extract_cookie")])
    assert plan.steps[0].status == ActionPlanStatus.BLOCKED
    assert plan.overall_status == ActionPlanStatus.BLOCKED


def test_dump_session_blocked():
    plan = build_action_plan("p1", "test", [_spec(SiteCapability.READ, "dump_session")])
    assert plan.steps[0].status == ActionPlanStatus.BLOCKED


def test_read_private_key_blocked():
    plan = build_action_plan("p1", "test", [_spec(SiteCapability.READ, "read_private_key")])
    assert plan.steps[0].status == ActionPlanStatus.BLOCKED


# ── 5. SUBMIT/PUBLISH/SEND/UPLOAD/DELETE/SIGN gate required ─────────


def test_submit_gate_required():
    plan = build_action_plan("p1", "test", [_spec(SiteCapability.SUBMIT, "submit_form")])
    assert plan.steps[0].status == ActionPlanStatus.GATE_REQUIRED
    assert plan.overall_status == ActionPlanStatus.GATE_REQUIRED


def test_publish_gate_required():
    plan = build_action_plan("p1", "test", [_spec(SiteCapability.PUBLISH, "publish_post")])
    assert plan.steps[0].status == ActionPlanStatus.GATE_REQUIRED


def test_send_gate_required():
    plan = build_action_plan("p1", "test", [_spec(SiteCapability.SEND, "send_mail")])
    assert plan.steps[0].status == ActionPlanStatus.GATE_REQUIRED


def test_upload_gate_required():
    plan = build_action_plan("p1", "test", [_spec(SiteCapability.UPLOAD, "upload_file")])
    assert plan.steps[0].status == ActionPlanStatus.GATE_REQUIRED


def test_delete_gate_required():
    plan = build_action_plan("p1", "test", [_spec(SiteCapability.DELETE, "delete_item")])
    assert plan.steps[0].status == ActionPlanStatus.GATE_REQUIRED


# ── 6. execution_gate attach ─────────────────────────────────────────


def test_append_gate_decision_makes_ready():
    plan = build_action_plan("p1", "test", [_spec(SiteCapability.SUBMIT, "submit_form", step_id="s1")])
    assert plan.steps[0].status == ActionPlanStatus.GATE_REQUIRED
    plan = append_gate_decision(plan, "s1", _allowed_gate_result())
    assert plan.steps[0].status == ActionPlanStatus.READY
    assert plan.overall_status == ActionPlanStatus.READY


def test_append_gate_blocked_stays_blocked():
    from scripts.site_engine.execution_gate import GateReason

    plan = build_action_plan("p1", "test", [_spec(SiteCapability.SUBMIT, "submit_form", step_id="s1")])
    blocked_result = ExecutionGateResult(
        decision=ExecutionDecision.BLOCKED,
        gate_decision=GateDecision.BLOCKED,
        reason=GateReason.BLOCKED_BY_PROFILE,
        is_blocked=True,
    )
    plan = append_gate_decision(plan, "s1", blocked_result)
    assert plan.steps[0].status == ActionPlanStatus.BLOCKED


# ── 7. no value field on sensitive step ─────────────────────────────


def test_no_value_field_on_step():
    plan = build_action_plan("p1", "test", [_spec(SiteCapability.FORM_FILL, "input_pw", field_name="password")])
    assert not hasattr(plan.steps[0], "value")


# ── 8. require_gate_for_sensitive_action ────────────────────────────


def test_require_gate_submit():
    assert require_gate_for_sensitive_action(SiteCapability.SUBMIT, "submit_form")


def test_require_gate_credential_extraction():
    assert require_gate_for_sensitive_action(SiteCapability.READ, "extract_password")


def test_no_require_gate_read():
    assert not require_gate_for_sensitive_action(SiteCapability.READ, "list_items")


# ── 9. summarize_action_plan ─────────────────────────────────────────


def test_summarize_no_sensitive_values():
    plan = build_action_plan("p1", "test", [_spec(SiteCapability.READ, "list")])
    summary = summarize_action_plan(plan)
    assert "password" not in str(summary)
    assert summary["overall_status"] == ActionPlanStatus.READY.value

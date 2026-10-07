"""Unit tests for scripts.site_engine.validators."""

from scripts.site_engine.action_planner import ActionPlanStatus, build_action_plan
from scripts.site_engine.execution_gate import (
    ExecutionDecision,
    ExecutionGateResult,
    GateReason,
)
from scripts.site_engine.site_types import GateDecision, SiteCapability
from scripts.site_engine.validators import (
    validate_action_plan_safety,
    validate_action_plan_steps,
    validate_no_blocked_step_executable,
    validate_no_executable_sensitive_step_without_gate,
    validate_no_plain_secret,
    validate_workflow_has_profile,
)
from scripts.site_engine.workflow_runner import (
    WorkflowDefinition,
    build_workflow_plan,
)

# ── validate_no_plain_secret ─────────────────────────────────────────


def test_no_plain_secret_clean():
    result = validate_no_plain_secret({"username": "alice", "email": "a@b.com"})
    assert result.is_valid


def test_no_plain_secret_detects_password():
    result = validate_no_plain_secret({"password": "hunter2"})
    assert not result.is_valid
    assert any(i.code == "PLAIN_SECRET_KEY" for i in result.issues)


def test_no_plain_secret_detects_token():
    result = validate_no_plain_secret({"api_token": "abc123"})
    assert not result.is_valid


def test_no_plain_secret_detects_cookie():
    result = validate_no_plain_secret({"cookie": "val"})
    assert not result.is_valid


# ── validate_no_executable_sensitive_step_without_gate ───────────────


def test_submit_step_without_gate_fails():
    plan = build_action_plan("p1", "test", [{"capability": SiteCapability.SUBMIT, "action": "submit", "step_id": "s1"}])
    # gate 없이 GATE_REQUIRED → 검증 통과 (READY 아님)
    result = validate_no_executable_sensitive_step_without_gate(plan)
    assert result.is_valid  # GATE_REQUIRED 상태이므로 READY가 아님 → 통과


def test_submit_step_forced_ready_without_gate_fails():
    plan = build_action_plan("p1", "test", [{"capability": SiteCapability.SUBMIT, "action": "submit", "step_id": "s1"}])
    # 강제로 READY 상태로 만들고 gate_result 없이 → 검증 실패
    plan.steps[0].status = ActionPlanStatus.READY
    plan.steps[0].gate_result = None
    result = validate_no_executable_sensitive_step_without_gate(plan)
    assert not result.is_valid
    assert any(i.code == "APPROVAL_REQUIRED_WITHOUT_GATE" for i in result.issues)


# ── validate_no_blocked_step_executable ──────────────────────────────


def test_blocked_step_not_allowed_passes():
    plan = build_action_plan(
        "p1", "test", [{"capability": SiteCapability.READ, "action": "extract_cookie", "step_id": "s1"}]
    )
    result = validate_no_blocked_step_executable(plan)
    assert result.is_valid


def test_blocked_step_with_allowed_gate_fails():
    plan = build_action_plan(
        "p1", "test", [{"capability": SiteCapability.READ, "action": "extract_cookie", "step_id": "s1"}]
    )
    # 강제로 allowed gate result 붙이기 → 검증 실패해야 함
    plan.steps[0].gate_result = ExecutionGateResult(
        decision=ExecutionDecision.ALLOWED,
        gate_decision=GateDecision.READ_ONLY_ALLOWED,
        reason=GateReason.ALLOWED_READ_ONLY,
    )
    result = validate_no_blocked_step_executable(plan)
    assert not result.is_valid
    assert any(i.code == "BLOCKED_STEP_MARKED_ALLOWED" for i in result.issues)


# ── validate_workflow_has_profile ────────────────────────────────────


def test_workflow_with_site_key_valid():
    defn = WorkflowDefinition(workflow_id="w", name="w", site_key="eum")
    plan = build_workflow_plan(defn)
    result = validate_workflow_has_profile(plan)
    assert result.is_valid


def test_workflow_without_site_key_invalid():
    defn = WorkflowDefinition(workflow_id="w", name="w", site_key="", profile_key="")
    plan = build_workflow_plan(defn)
    result = validate_workflow_has_profile(plan)
    assert not result.is_valid
    assert any(i.code == "MISSING_PROFILE" for i in result.issues)


# ── validate_action_plan_steps ───────────────────────────────────────


def test_action_plan_steps_all_ready_valid():
    plan = build_action_plan("p1", "test", [{"capability": SiteCapability.READ, "action": "list", "step_id": "s1"}])
    result = validate_action_plan_steps(plan)
    assert result.is_valid


def test_validators_detect_dangerous_steps():
    plan = build_action_plan(
        "p1", "test", [{"capability": SiteCapability.READ, "action": "extract_password", "step_id": "s1"}]
    )
    assert plan.steps[0].status == ActionPlanStatus.BLOCKED
    r = validate_no_blocked_step_executable(plan)
    assert r.is_valid  # BLOCKED + gate_result=None → 통과 (실행 안 됨)


# ── no external call ─────────────────────────────────────────────────


def test_validators_no_external_call():
    from scripts.site_engine import validators

    assert callable(validators.validate_no_plain_secret)


# ── validate_action_plan_safety (도구별 validate_<tool>_action_plan 공용 본문) ──


def test_action_plan_safety_merges_three_checks():
    plan = build_action_plan("p1", "test", [{"capability": SiteCapability.SUBMIT, "action": "submit", "step_id": "s1"}])
    plan.steps[0].status = ActionPlanStatus.READY
    plan.steps[0].gate_result = None
    merged = validate_action_plan_safety(plan)
    expected = (
        validate_action_plan_steps(plan).issues
        + validate_no_blocked_step_executable(plan).issues
        + validate_no_executable_sensitive_step_without_gate(plan).issues
    )
    assert [i.code for i in merged.issues] == [i.code for i in expected]
    assert merged.is_valid is (not expected)
    assert not merged.is_valid


def test_tool_action_plan_validators_delegate_to_shared():
    from scripts.gabia.validators import validate_gabia_action_plan
    from scripts.google.validators import validate_google_action_plan
    from scripts.hiworks.validators import validate_hiworks_action_plan
    from scripts.youtube.validators import validate_youtube_action_plan

    plan = build_action_plan("p1", "test", [{"capability": SiteCapability.SUBMIT, "action": "submit", "step_id": "s1"}])
    base = validate_action_plan_safety(plan)
    for fn in (validate_gabia_action_plan, validate_google_action_plan, validate_hiworks_action_plan, validate_youtube_action_plan):
        r = fn(plan)
        assert r.is_valid == base.is_valid
        assert [i.code for i in r.issues] == [i.code for i in base.issues]

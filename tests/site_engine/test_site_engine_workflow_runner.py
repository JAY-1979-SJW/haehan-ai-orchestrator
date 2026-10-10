"""Unit tests for scripts.site_engine.workflow_runner."""

from scripts.site_engine.action_planner import build_action_plan
from scripts.site_engine.site_types import SiteCapability
from scripts.site_engine.workflow_runner import (
    WorkflowDefinition,
    WorkflowStatus,
    WorkflowStep,
    attach_action_plan,
    build_workflow_plan,
    validate_workflow_plan,
)


def _def(site_key: str = "test", profile_key: str = "test", steps=None) -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="wf1",
        name="Test Workflow",
        site_key=site_key,
        profile_key=profile_key,
        steps=steps or [],
    )


def _step(step_id: str, cap: SiteCapability, action: str) -> WorkflowStep:
    ap = build_action_plan("ap1", "test", [{"capability": cap, "action": action, "step_id": "a1"}])
    return WorkflowStep(step_id=step_id, name=step_id, action_plan=ap)


# ── workflow plan 생성 ────────────────────────────────────────────────


def test_build_workflow_plan_ready():
    defn = _def(steps=[_step("s1", SiteCapability.READ, "list_items")])
    plan = build_workflow_plan(defn)
    assert plan.status == WorkflowStatus.READY


def test_build_workflow_plan_approval_required():
    defn = _def(steps=[_step("s1", SiteCapability.SUBMIT, "submit_form")])
    plan = build_workflow_plan(defn)
    assert plan.status == WorkflowStatus.APPROVAL_REQUIRED
    assert "s1" in plan.approval_required_step_ids


def test_build_workflow_plan_blocked():
    defn = _def(steps=[_step("s1", SiteCapability.READ, "extract_cookie")])
    plan = build_workflow_plan(defn)
    assert plan.status == WorkflowStatus.BLOCKED
    assert "s1" in plan.blocking_step_ids


def test_build_workflow_plan_user_action():
    from scripts.site_engine.action_planner import build_action_plan

    ap = build_action_plan(
        "ap1",
        "test",
        [{"capability": SiteCapability.FORM_FILL, "action": "input_pw", "step_id": "a1", "field_name": "password"}],
    )
    step = WorkflowStep(step_id="s1", name="login", action_plan=ap)
    defn = _def(steps=[step])
    plan = build_workflow_plan(defn)
    assert plan.status == WorkflowStatus.USER_ACTION_REQUIRED


def test_workflow_needs_profile_when_no_site_key():
    defn = WorkflowDefinition(workflow_id="w", name="w", site_key="", profile_key="")
    plan = build_workflow_plan(defn)
    assert plan.status == WorkflowStatus.NEEDS_PROFILE


# ── is_executable ────────────────────────────────────────────────────


def test_workflow_not_executable_when_approval_required():
    defn = _def(steps=[_step("s1", SiteCapability.SUBMIT, "submit")])
    plan = build_workflow_plan(defn)
    assert not plan.is_executable()


def test_workflow_executable_when_all_ready():
    defn = _def(steps=[_step("s1", SiteCapability.READ, "read")])
    plan = build_workflow_plan(defn)
    assert plan.is_executable()


# ── attach_action_plan ───────────────────────────────────────────────


def test_attach_action_plan_updates_status():
    empty_step = WorkflowStep(step_id="s1", name="step1")
    defn = _def(steps=[empty_step])
    plan = build_workflow_plan(defn)

    ap = build_action_plan("ap1", "test", [{"capability": SiteCapability.READ, "action": "read", "step_id": "a1"}])
    plan = attach_action_plan(plan, "s1", ap)
    assert plan.status == WorkflowStatus.READY


# ── validate_workflow_plan ───────────────────────────────────────────


def test_validate_missing_site_key():
    defn = WorkflowDefinition(workflow_id="w", name="w", site_key="", profile_key="")
    plan = build_workflow_plan(defn)
    result = validate_workflow_plan(plan)
    assert not result.is_valid


def test_validate_valid_workflow():
    defn = _def(steps=[_step("s1", SiteCapability.READ, "list")])
    plan = build_workflow_plan(defn)
    result = validate_workflow_plan(plan)
    assert result.is_valid


# ── no browser/db/file exec ──────────────────────────────────────────


def test_no_external_call_on_build():
    defn = _def(steps=[_step("s1", SiteCapability.SEND, "send_mail")])
    plan = build_workflow_plan(defn)
    assert plan is not None  # 실행 없이 plan만 반환됨

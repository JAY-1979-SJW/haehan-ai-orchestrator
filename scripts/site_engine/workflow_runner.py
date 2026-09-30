"""site_engine workflow runner — 업무 흐름 plan 조합 foundation.

실제 실행 없음. 브라우저 호출 없음. DB/file write 없음.
approval required step은 gate 없이 executable 상태가 될 수 없다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from scripts.site_engine.action_planner import ActionPlan, ActionPlanStatus
from scripts.site_engine.execution_gate import ExecutionGateResult


class WorkflowStatus(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    USER_ACTION_REQUIRED = "USER_ACTION_REQUIRED"
    BLOCKED = "BLOCKED"
    NEEDS_PROFILE = "NEEDS_PROFILE"


@dataclass
class WorkflowStep:
    step_id: str
    name: str
    action_plan: ActionPlan | None = None
    gate_result: ExecutionGateResult | None = None
    order: int = 0
    is_optional: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowDefinition:
    workflow_id: str
    name: str
    site_key: str
    profile_key: str | None = None
    steps: list[WorkflowStep] = field(default_factory=list)
    description: str = ""


@dataclass
class WorkflowRunPlan:
    definition: WorkflowDefinition
    status: WorkflowStatus = WorkflowStatus.PENDING
    blocking_step_ids: list[str] = field(default_factory=list)
    approval_required_step_ids: list[str] = field(default_factory=list)
    user_action_step_ids: list[str] = field(default_factory=list)

    def is_executable(self) -> bool:
        return self.status == WorkflowStatus.READY


@dataclass
class WorkflowRunResult:
    run_plan: WorkflowRunPlan
    validation_errors: list[str] = field(default_factory=list)
    is_valid: bool = True


def build_workflow_plan(definition: WorkflowDefinition) -> WorkflowRunPlan:
    """workflow 실행 계획을 만든다. 실제 실행 없음."""
    plan = WorkflowRunPlan(definition=definition)

    if not definition.profile_key and not definition.site_key:
        plan.status = WorkflowStatus.NEEDS_PROFILE
        return plan

    _recompute_status(plan)
    return plan


def _recompute_status(plan: WorkflowRunPlan) -> None:
    blocked: list[str] = []
    approval: list[str] = []
    user_action: list[str] = []

    for step in plan.definition.steps:
        ap = step.action_plan
        if ap is None:
            continue
        if ap.overall_status == ActionPlanStatus.BLOCKED:
            blocked.append(step.step_id)
        elif ap.overall_status == ActionPlanStatus.GATE_REQUIRED:
            approval.append(step.step_id)
        elif ap.overall_status == ActionPlanStatus.USER_ACTION_REQUIRED:
            user_action.append(step.step_id)

    plan.blocking_step_ids = blocked
    plan.approval_required_step_ids = approval
    plan.user_action_step_ids = user_action

    if blocked:
        plan.status = WorkflowStatus.BLOCKED
    elif user_action:
        plan.status = WorkflowStatus.USER_ACTION_REQUIRED
    elif approval:
        plan.status = WorkflowStatus.APPROVAL_REQUIRED
    else:
        plan.status = WorkflowStatus.READY


def validate_workflow_plan(plan: WorkflowRunPlan) -> WorkflowRunResult:
    errors: list[str] = []

    if not plan.definition.site_key:
        errors.append("workflow definition must have a site_key")

    for step in plan.definition.steps:
        ap = step.action_plan
        if ap is None:
            continue
        # approval required step이 approval 없이 executable 상태면 오류
        for s in ap.steps:
            if (
                s.required_gate.value in ("APPROVAL_REQUIRED",)
                and s.status == ActionPlanStatus.READY
                and s.gate_result is None
            ):
                errors.append(f"step {s.step_id!r} is READY but has no gate_result for APPROVAL_REQUIRED action")

    return WorkflowRunResult(
        run_plan=plan,
        validation_errors=errors,
        is_valid=len(errors) == 0,
    )


def attach_action_plan(
    plan: WorkflowRunPlan,
    step_id: str,
    action_plan: ActionPlan,
) -> WorkflowRunPlan:
    for step in plan.definition.steps:
        if step.step_id == step_id:
            step.action_plan = action_plan
            break
    _recompute_status(plan)
    return plan


def attach_gate_result(
    plan: WorkflowRunPlan,
    step_id: str,
    gate_result: ExecutionGateResult,
) -> WorkflowRunPlan:
    for step in plan.definition.steps:
        if step.step_id == step_id:
            step.gate_result = gate_result
            break
    _recompute_status(plan)
    return plan

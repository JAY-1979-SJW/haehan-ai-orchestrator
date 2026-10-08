"""site_engine action planner — 브라우저 action 계획 조합 foundation.

실제 실행 없음. 브라우저 호출 없음. 파일/DB write 없음.
execution_gate 결과가 있어야 비가역 action이 executable 상태가 된다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from scripts.site_engine.execution_gate import (
    ExecutionDecision,
    ExecutionGateResult,
    matches_credential_extraction,
)
from scripts.site_engine.site_types import GateDecision, SiteCapability


class ActionPlanStatus(str, Enum):
    PENDING = "PENDING"
    GATE_REQUIRED = "GATE_REQUIRED"
    USER_ACTION_REQUIRED = "USER_ACTION_REQUIRED"
    BLOCKED = "BLOCKED"
    READY = "READY"


class ActionPlanRisk(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


_IRREVERSIBLE_CAPABILITIES = frozenset(
    {
        SiteCapability.SUBMIT,
        SiteCapability.UPLOAD,
        SiteCapability.DELETE,
        SiteCapability.PUBLISH,
        SiteCapability.SEND,
        SiteCapability.SIGN,
    }
)

_USER_DIRECT_CAPABILITIES = frozenset(
    {
        SiteCapability.SIGN,
    }
)

_SENSITIVE_FIELD_KEYWORDS = frozenset(
    {
        "password",
        "passwd",
        "otp",
        "pin",
        "secret",
        "token",
        "certificate",
        "cert",
        "private_key",
        "credential",
        "session",
        "cookie",
        "비밀번호",
        "인증서",
        "쿠키",
        "세션",
    }
)

_CREDENTIAL_EXTRACT_KEYWORDS = frozenset(
    {
        "extract",
        "get",
        "read",
        "dump",
        "export",
        "fetch",
        "추출",
        "가져오기",
        "읽기",
        "내보내기",
    }
)


def _is_credential_extraction(action: str) -> bool:
    return matches_credential_extraction(action, _SENSITIVE_FIELD_KEYWORDS, _CREDENTIAL_EXTRACT_KEYWORDS)


def _is_sensitive_field(field_name: str) -> bool:
    lower = field_name.lower()
    return any(k in lower for k in _SENSITIVE_FIELD_KEYWORDS)


def _capability_risk(cap: SiteCapability) -> ActionPlanRisk:
    if cap in (SiteCapability.DELETE, SiteCapability.SIGN):
        return ActionPlanRisk.CRITICAL
    if cap in _IRREVERSIBLE_CAPABILITIES:
        return ActionPlanRisk.HIGH
    if cap in (SiteCapability.FORM_FILL,):
        return ActionPlanRisk.MEDIUM
    return ActionPlanRisk.LOW


@dataclass
class ActionPlanStep:
    step_id: str
    capability: SiteCapability
    action: str
    status: ActionPlanStatus
    risk: ActionPlanRisk
    required_gate: GateDecision
    is_sensitive: bool = False
    sensitive_reason: str = ""
    gate_result: ExecutionGateResult | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    # value 필드 없음 — 민감값 저장 금지


@dataclass
class ActionPlan:
    plan_id: str
    site_key: str
    steps: list[ActionPlanStep] = field(default_factory=list)
    overall_status: ActionPlanStatus = ActionPlanStatus.PENDING

    def is_executable(self) -> bool:
        return self.overall_status == ActionPlanStatus.READY

    def has_blocked_steps(self) -> bool:
        return any(s.status == ActionPlanStatus.BLOCKED for s in self.steps)

    def has_gate_required_steps(self) -> bool:
        return any(s.status == ActionPlanStatus.GATE_REQUIRED for s in self.steps)


@dataclass
class ActionPlanResult:
    plan: ActionPlan
    validation_errors: list[str] = field(default_factory=list)
    is_valid: bool = True


def build_action_plan(
    plan_id: str,
    site_key: str,
    steps_spec: list[dict[str, Any]],
) -> ActionPlan:
    """action plan 생성.

    steps_spec 항목: {"step_id": str, "capability": SiteCapability,
                      "action": str, "field_name": str (optional)}
    """
    steps: list[ActionPlanStep] = []
    for spec in steps_spec:
        cap = spec["capability"]
        action = spec.get("action", "")
        field_name = spec.get("field_name", "")
        step_id = spec.get("step_id", f"step_{len(steps)}")

        # 자격증명 추출 시도 → BLOCKED
        if _is_credential_extraction(action):
            steps.append(
                ActionPlanStep(
                    step_id=step_id,
                    capability=cap,
                    action=action,
                    status=ActionPlanStatus.BLOCKED,
                    risk=ActionPlanRisk.CRITICAL,
                    required_gate=GateDecision.BLOCKED,
                    is_sensitive=True,
                    sensitive_reason="credential extraction is forbidden",
                )
            )
            continue

        # 민감 필드 입력 → USER_ACTION_REQUIRED
        if cap == SiteCapability.FORM_FILL and _is_sensitive_field(field_name):
            steps.append(
                ActionPlanStep(
                    step_id=step_id,
                    capability=cap,
                    action=action,
                    status=ActionPlanStatus.USER_ACTION_REQUIRED,
                    risk=ActionPlanRisk.HIGH,
                    required_gate=GateDecision.USER_DIRECT_REQUIRED,
                    is_sensitive=True,
                    sensitive_reason=f"sensitive field: {field_name!r}",
                    metadata={"field_name": field_name},
                )
            )
            continue

        # 비가역 작업 → GATE_REQUIRED
        if cap in _IRREVERSIBLE_CAPABILITIES:
            steps.append(
                ActionPlanStep(
                    step_id=step_id,
                    capability=cap,
                    action=action,
                    status=ActionPlanStatus.GATE_REQUIRED,
                    risk=_capability_risk(cap),
                    required_gate=GateDecision.APPROVAL_REQUIRED,
                    metadata=spec.get("metadata", {}),
                )
            )
            continue

        # USER_DIRECT only
        if cap in _USER_DIRECT_CAPABILITIES:
            steps.append(
                ActionPlanStep(
                    step_id=step_id,
                    capability=cap,
                    action=action,
                    status=ActionPlanStatus.USER_ACTION_REQUIRED,
                    risk=ActionPlanRisk.CRITICAL,
                    required_gate=GateDecision.USER_DIRECT_REQUIRED,
                )
            )
            continue

        # 일반 읽기/탐색
        steps.append(
            ActionPlanStep(
                step_id=step_id,
                capability=cap,
                action=action,
                status=ActionPlanStatus.READY,
                risk=_capability_risk(cap),
                required_gate=GateDecision.READ_ONLY_ALLOWED
                if cap in (SiteCapability.READ, SiteCapability.SEARCH)
                else GateDecision.SERVER_BROWSER_ALLOWED,
                metadata=spec.get("metadata", {}),
            )
        )

    plan = ActionPlan(plan_id=plan_id, site_key=site_key, steps=steps)
    _update_overall_status(plan)
    return plan


def _update_overall_status(plan: ActionPlan) -> None:
    if any(s.status == ActionPlanStatus.BLOCKED for s in plan.steps):
        plan.overall_status = ActionPlanStatus.BLOCKED
    elif any(s.status == ActionPlanStatus.USER_ACTION_REQUIRED for s in plan.steps):
        plan.overall_status = ActionPlanStatus.USER_ACTION_REQUIRED
    elif any(s.status == ActionPlanStatus.GATE_REQUIRED for s in plan.steps):
        plan.overall_status = ActionPlanStatus.GATE_REQUIRED
    else:
        plan.overall_status = ActionPlanStatus.READY


def append_gate_decision(
    plan: ActionPlan,
    step_id: str,
    gate_result: ExecutionGateResult,
) -> ActionPlan:
    """gate 결과를 특정 step에 attach하고 plan 상태를 재계산한다."""
    for step in plan.steps:
        if step.step_id == step_id:
            step.gate_result = gate_result
            if gate_result.decision == ExecutionDecision.ALLOWED:
                step.status = ActionPlanStatus.READY
            elif gate_result.decision == ExecutionDecision.BLOCKED:
                step.status = ActionPlanStatus.BLOCKED
            elif gate_result.decision in (
                ExecutionDecision.USER_DIRECT_REQUIRED,
                ExecutionDecision.LOCAL_AGENT_REQUIRED,
            ):
                step.status = ActionPlanStatus.USER_ACTION_REQUIRED
            break
    _update_overall_status(plan)
    return plan


def require_gate_for_sensitive_action(
    capability: SiteCapability,
    action: str,
) -> bool:
    """이 action이 gate 필수 여부를 반환."""
    if capability in _IRREVERSIBLE_CAPABILITIES:
        return True
    if _is_credential_extraction(action):
        return True
    return False


def summarize_action_plan(plan: ActionPlan) -> dict[str, Any]:
    """plan 요약 반환. 민감값 미포함."""
    return {
        "plan_id": plan.plan_id,
        "site_key": plan.site_key,
        "overall_status": plan.overall_status.value,
        "step_count": len(plan.steps),
        "blocked": sum(1 for s in plan.steps if s.status == ActionPlanStatus.BLOCKED),
        "gate_required": sum(1 for s in plan.steps if s.status == ActionPlanStatus.GATE_REQUIRED),
        "user_action_required": sum(1 for s in plan.steps if s.status == ActionPlanStatus.USER_ACTION_REQUIRED),
        "ready": sum(1 for s in plan.steps if s.status == ActionPlanStatus.READY),
    }

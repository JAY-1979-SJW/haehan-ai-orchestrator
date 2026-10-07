from typing import Literal, cast

from orchestrator_v1.core.models import RiskAssessment, TaskRequest
from orchestrator_v1.tasks.policy_engine import (
    get_risk_level_for_action,
    is_command_blocked,
    load_policy,
)


def assess_risk(task: TaskRequest, policy: dict | None = None) -> RiskAssessment:
    if policy is None:
        policy = load_policy()

    reasons = []

    if is_command_blocked(task.action_type, policy) or is_command_blocked(task.target, policy):
        reasons.append("blocked keyword detected in action_type or target")
        return RiskAssessment(risk_level="critical", reasons=reasons, requires_approval=True)

    level = get_risk_level_for_action(task.action_type, policy)
    if level is None:
        reasons.append(f"unknown action_type '{task.action_type}' — defaulting to high")
        level = "high"

    level_cfg = policy["risk_levels"].get(level, {})
    requires_approval = level_cfg.get("requires_approval", True)

    if level == "critical":
        reasons.append("critical action — always blocked by default")

    return RiskAssessment(
        risk_level=cast(Literal["low", "medium", "high", "critical"], level),
        reasons=reasons,
        requires_approval=requires_approval,
    )

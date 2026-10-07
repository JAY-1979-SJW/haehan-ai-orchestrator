from dataclasses import dataclass, field
from typing import Literal


@dataclass
class TaskRequest:
    task_id: str
    source: Literal["pc", "server", "manual"]
    action_type: str
    target: str
    description: str
    payload: dict = field(default_factory=dict)
    requested_by: str = "system"


@dataclass
class RiskAssessment:
    risk_level: Literal["low", "medium", "high", "critical"]
    reasons: list = field(default_factory=list)
    requires_approval: bool = False


@dataclass
class ExecutionPlan:
    task_id: str
    allowed: bool
    requires_approval: bool
    steps: list = field(default_factory=list)
    blocked_reasons: list = field(default_factory=list)

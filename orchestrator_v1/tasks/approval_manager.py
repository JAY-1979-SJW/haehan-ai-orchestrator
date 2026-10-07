import time
import uuid

from models import ExecutionPlan, RiskAssessment, TaskRequest

_store: dict[str, dict] = {}

TOKEN_TTL_SECONDS = 600  # 10 minutes


def issue_token(task: TaskRequest, risk: RiskAssessment) -> str | None:
    if risk.risk_level == "critical":
        return None
    token_id = str(uuid.uuid4())
    _store[token_id] = {
        "task_id": task.task_id,
        "risk_level": risk.risk_level,
        "issued_at": time.time(),
        "approved": False,
        "rejected": False,
    }
    return token_id


def approve_token(token_id: str) -> bool:
    entry = _store.get(token_id)
    if not entry:
        return False
    if time.time() - entry["issued_at"] > TOKEN_TTL_SECONDS:
        return False
    entry["approved"] = True
    return True


def reject_token(token_id: str) -> bool:
    entry = _store.get(token_id)
    if not entry:
        return False
    entry["rejected"] = True
    return True


def is_token_valid(token_id: str) -> bool:
    entry = _store.get(token_id)
    if not entry:
        return False
    if time.time() - entry["issued_at"] > TOKEN_TTL_SECONDS:
        return False
    if entry.get("rejected"):
        return False
    return entry.get("approved", False)


def build_execution_plan(task: TaskRequest, risk: RiskAssessment, token_id: str | None) -> ExecutionPlan:
    level = risk.risk_level
    blocked_reasons = list(risk.reasons)

    if level == "critical":
        blocked_reasons.append("critical actions are always blocked")
        return ExecutionPlan(
            task_id=task.task_id,
            allowed=False,
            requires_approval=True,
            steps=[],
            blocked_reasons=blocked_reasons,
        )

    if level == "high":
        blocked_reasons.append("high actions require approval and cannot be auto-executed")
        return ExecutionPlan(
            task_id=task.task_id,
            allowed=False,
            requires_approval=True,
            steps=["send approval request", "await human confirmation"],
            blocked_reasons=blocked_reasons,
        )

    if level == "medium":
        requires_approval = True
        steps = ["preview_patch only — no actual write"]
        allowed = bool(token_id)
        if not token_id:
            blocked_reasons.append("medium action requires approval token")
        return ExecutionPlan(
            task_id=task.task_id,
            allowed=allowed,
            requires_approval=requires_approval,
            steps=steps,
            blocked_reasons=blocked_reasons,
        )

    # low
    return ExecutionPlan(
        task_id=task.task_id,
        allowed=True,
        requires_approval=False,
        steps=[f"execute {task.action_type} on {task.target}"],
        blocked_reasons=[],
    )

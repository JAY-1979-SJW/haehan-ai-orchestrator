import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_LOG_PATH = Path(__file__).parent / "storage" / "audit_logs.jsonl"

EVENT_TYPES = {
    "TASK_RECEIVED",
    "RISK_ASSESSED",
    "PLAN_CREATED",
    "APPROVAL_ISSUED",
    "APPROVAL_GRANTED",
    "APPROVAL_REJECTED",
    "EXECUTION_BLOCKED",
    "EXECUTION_PENDING",
    "DRY_RUN_RETURNED",
}


def log_event(
    event_type: str,
    task_id: str,
    risk_level: str = "",
    action_type: str = "",
    target: str = "",
    allowed: Optional[bool] = None,
    requires_approval: Optional[bool] = None,
    decision: str = "",
    actor: str = "system",
    note: str = "",
) -> None:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "task_id": task_id,
        "risk_level": risk_level,
        "action_type": action_type,
        "target": target,
        "allowed": allowed,
        "requires_approval": requires_approval,
        "decision": decision,
        "actor": actor,
        "note": note,
    }
    with open(_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_recent_logs(limit: int = 20) -> list[dict]:
    if not _LOG_PATH.exists():
        return []
    lines = _LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
    recent = lines[-limit:] if len(lines) > limit else lines
    result = []
    for line in recent:
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return result

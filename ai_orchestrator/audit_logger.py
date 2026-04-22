import json
import logging
from datetime import datetime, timezone
from typing import Optional

from .config import AUDIT_LOG_PATH as _LOG_PATH

logger = logging.getLogger(__name__)

EVENT_TYPES = {
    "TASK_RECEIVED",
    "RISK_ASSESSED",
    "PLAN_CREATED",
    "APPROVAL_ISSUED",
    "APPROVAL_GRANTED",
    "APPROVAL_DENIED",
    "APPROVAL_REJECTED",
    "APPROVAL_INVALID_TOKEN",
    "APPROVAL_EXPIRED",
    "APPROVAL_ALREADY_USED",
    "APPROVAL_RATE_LIMITED",
    "APPROVAL_REJECT_FORBIDDEN",
    "APPROVAL_REJECT_INVALID_TOKEN",
    "EXECUTION_BLOCKED",
    "EXECUTION_PENDING",
    "EXECUTION_RATE_LIMITED",
    "EXECUTION_TIMEOUT",
    "DRY_RUN_RETURNED",
    "SITE_CONNECTORS_LISTED",
    "SITE_HEALTH_CHECK",
    "SITE_TASK_DRY_RUN",
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
    role: str = "",
    token_id: str = "",
    note: str = "",
) -> None:
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
        "role": role,
        "token_id": token_id,
        "note": note,
    }

    logger.info("[AUDIT] %s | task=%s | actor=%s | role=%s | decision=%s%s",
                event_type, task_id, actor, role or "-", decision,
                f" | {note}" if note else "")

    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.error("감사 로그 파일 기록 실패: %s | entry=%s", e, entry)


def read_recent_logs(limit: int = 20) -> list[dict]:
    if not _LOG_PATH.exists():
        return []
    try:
        lines = _LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
    except OSError as e:
        logger.error("감사 로그 읽기 실패: %s", e)
        return []
    recent = lines[-limit:] if len(lines) > limit else lines
    result = []
    for line in recent:
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError as e:
            logger.warning("감사 로그 파싱 실패: %s | line=%r", e, line)
    return result

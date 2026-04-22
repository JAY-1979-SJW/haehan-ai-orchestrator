import logging
from .models import TaskRequest, RiskAssessment

logger = logging.getLogger(__name__)

SENSITIVE_PATHS = ["/etc/", "/var/lib/", "~/.ssh/", "~/.secrets/", "C:/Windows/", "C:/Users/skyjw/.ssh/"]
DESTRUCTIVE_COMMANDS = ["rm -rf", "dd if=", "mkfs", "shutdown", "reboot", "DROP TABLE", "DELETE FROM", "fdisk"]


def classify_risk(req: TaskRequest) -> RiskAssessment:
    action = req.action_type.lower()
    target = req.target.lower()
    payload_str = str(req.payload).lower()

    level = _base_level(action)
    reasons = [f"action_type '{req.action_type}' → base level: {level}"]

    # 민감 경로 감지
    for path in SENSITIVE_PATHS:
        if path.lower() in target:
            if level in ("low", "medium"):
                level = "high"
            reasons.append(f"민감 경로 감지: {path}")
            break

    # 파괴적 명령어 감지
    for cmd in DESTRUCTIVE_COMMANDS:
        if cmd.lower() in payload_str or cmd.lower() in target:
            level = "critical"
            reasons.append(f"파괴적 명령어 감지: {cmd}")
            break

    requires_approval = level in ("medium", "high", "critical")
    return RiskAssessment(risk_level=level, reasons=reasons, requires_approval=requires_approval)


def _base_level(action: str) -> str:
    if any(k in action for k in ("read", "list", "inspect", "summarize", "status")):
        return "low"
    if any(k in action for k in ("write", "edit", "create_patch", "generate")):
        return "medium"
    if any(k in action for k in ("shell", "restart", "deploy", "push", "send", "db_write")):
        return "high"
    if any(k in action for k in ("delete", "drop", "revoke", "rm_recursive", "bulk")):
        return "critical"
    return "medium"

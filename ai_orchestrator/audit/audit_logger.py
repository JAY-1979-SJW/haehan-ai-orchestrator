import json
import logging
from datetime import UTC, datetime

from ai_orchestrator.core.logging_utils import mask_sensitive

from ..core.config import AUDIT_LOG_PATH as _LOG_PATH

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
    # CAD 프록시 — /api/v1/cad/* 호출 감사
    "CAD_PROXY_CALL",
    "CAD_PROXY_DENIED",
    "CAD_PROXY_UPSTREAM_ERROR",
    # 웹 작업 레지스트리 + 표준 실행 API
    "WEB_TASK_RUN_REQUESTED",
    "WEB_TASK_DRY_RUN_COMPLETED",
    "WEB_TASK_PENDING_APPROVAL_CREATED",
    "WEB_TASK_REJECTED_UNKNOWN_TASK",
    "WEB_TASK_VALIDATION_FAILED",
    "WEB_TASK_REGISTRY_LISTED",
    "WEB_TASK_TEMPLATE_USED",
    "WEB_TASK_TEMPLATE_NOT_FOUND",
    # 로컬 에이전트 (Stage 1)
    "LOCAL_AGENT_REGISTERED",
    "LOCAL_AGENT_TASK_QUEUED",
    "LOCAL_AGENT_TASK_WAITING_APPROVAL",
    "LOCAL_AGENT_TASK_COMPLETED",
    "LOCAL_AGENT_TASK_FAILED",
    "LOCAL_AGENT_TASK_REJECTED",
    "LOCAL_AGENT_TASK_REQUEUED",  # 2026-09-30: WS 연결 끊김 시 즉시 실패 대신 재큐잉(재시도)
    # 로컬 에이전트 (Stage 2 — WebSocket)
    "LOCAL_AGENT_WS_CONNECTED",
    "LOCAL_AGENT_WS_DISCONNECTED",
    "LOCAL_AGENT_WS_AUTH_FAILED",
    "LOCAL_AGENT_TASK_DELIVERED",
    "LOCAL_AGENT_TASK_RUNNING",
    "LOCAL_AGENT_TASK_TIMEOUT",
    # 로컬 에이전트 (Stage 11-7B — 취소)
    "LOCAL_AGENT_TASK_CANCEL_REQUESTED",
    "LOCAL_AGENT_TASK_CANCELLED",
    # EUM 견적서
    "EUM_QUOTE_GENERATE",
    "EUM_QUOTE_SAVE_FAIL",
    # 개발자 등록 승인 게이트 (web_task_router 가 dev_reg_approval 재사용)
    "DEV_REG_TASK_CREATED",
    "DEV_REG_TELEGRAM_SENT",
    "DEV_REG_APPROVED",
    "DEV_REG_REJECTED",
    "DEV_REG_EXPIRED",
    "DEV_REG_EXECUTED",
    "DEV_REG_FAILED",
}


def log_event(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수, 인자 묶음 변경 시 API 영향)
    event_type: str,
    task_id: str,
    risk_level: str = "",
    action_type: str = "",
    target: str = "",
    allowed: bool | None = None,
    requires_approval: bool | None = None,
    decision: str = "",
    actor: str = "system",
    role: str = "",
    token_id: str = "",
    note: str = "",
) -> None:
    masked_note = mask_sensitive(note) if note else note
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
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
        "note": masked_note,
    }

    logger.info(
        "[AUDIT] %s | task=%s | actor=%s | role=%s | decision=%s%s",
        event_type,
        task_id,
        actor,
        role or "-",
        decision,
        f" | {masked_note}" if masked_note else "",
    )

    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_PATH.open("a", encoding="utf-8") as f:
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

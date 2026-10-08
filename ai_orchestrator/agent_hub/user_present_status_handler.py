"""
서버 측 User-Present Status Event Handler

로컬 Agent로부터 수신한 USER_PRESENT_STATUS event를 검증하고
workflow 상태를 in-memory로 업데이트한다.

운영 DB write 없음.
task_executor/dispatcher 호출 없음.
실제 브라우저 실행 코드 없음.
safe_to_execute=true 포함 event는 reject.
민감정보(token/cookie/session) 포함 event는 reject.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

try:
    from ai_orchestrator.contracts.user_present_ws_contract import (
        MSG_USER_PRESENT_STATUS,
        STATUS_BLOCKED,
        STATUS_CANCELLED,
        STATUS_FAILED,
        STATUS_USER_CONFIRMED,
        STATUS_WAITING_FOR_USER,
        validate_user_present_ws_status_event,
    )
except ImportError:
    MSG_USER_PRESENT_STATUS = "USER_PRESENT_STATUS"
    STATUS_WAITING_FOR_USER = "WAITING_FOR_USER"
    STATUS_USER_CONFIRMED = "USER_CONFIRMED"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_BLOCKED = "BLOCKED"
    STATUS_FAILED = "FAILED"

    def validate_user_present_ws_status_event(event: dict[str, Any]) -> list[str]:
        errors = []
        for f in ["message_type", "workflow_run_id", "status", "safe_to_execute"]:
            if f not in event:
                errors.append(f"필수 필드 누락: {f}")
        return errors

try:
    from ai_orchestrator.agent_hub.user_present_status_store import (
        record_user_present_status as _record_status,
    )
    _STORE_AVAILABLE = True
except ImportError:
    _STORE_AVAILABLE = False

try:
    from ai_orchestrator.audit.audit_logger import log_event as _log_event
    _AUDIT_AVAILABLE = True
except ImportError:
    _AUDIT_AVAILABLE = False

# ── 허용 status 값 ────────────────────────────────────────────────────────────

_ACCEPTED_STATUSES: frozenset[str] = frozenset({
    STATUS_WAITING_FOR_USER,
    STATUS_USER_CONFIRMED,
    STATUS_CANCELLED,
    STATUS_BLOCKED,
    STATUS_FAILED,
})

# ── 민감정보 reject 필드 ─────────────────────────────────────────────────────

_REJECT_FIELDS: frozenset[str] = frozenset({
    "password", "otp", "certificate_password", "financial_certificate_password",
    "token", "access_token", "refresh_token", "api_key", "device_token",
    "cookie", "session", "localStorage", "sessionStorage",
})

# ── in-memory 상태 레지스트리 (운영 DB 미사용) ────────────────────────────────
# workflow_run_id → {status, accepted_at, ...}
_status_registry: dict[str, dict[str, Any]] = {}


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _reject_status_event(
    workflow_run_id: str,
    agent_id: str,
    audit_reason: str,
    error: str,
    message_ko: str,
    validation_errors: list[str] | None = None,
) -> dict[str, Any]:
    """거부 audit 기록 + 거부 응답 dict 생성 (기존 인라인 로직과 동일)."""
    if _AUDIT_AVAILABLE:
        _log_event(
            "LOCAL_AGENT_USER_PRESENT_STATUS_REJECTED", workflow_run_id,
            actor=agent_id or "ws-agent",
            note=f"reason={audit_reason}",
        )
    result: dict[str, Any] = {
        "ok": False,
        "workflow_run_id": workflow_run_id,
        "accepted_status": None,
        "safe_to_execute": False,
        "error": error,
    }
    if validation_errors is not None:
        result["validation_errors"] = validation_errors
    result["message_ko"] = message_ko
    return result


def handle_user_present_status_event(
    event: dict[str, Any],
    agent_id: str = "",
) -> dict[str, Any]:
    """
    USER_PRESENT_STATUS event를 수신하여 검증하고 in-memory 상태를 업데이트한다.

    safe_to_execute=true → reject
    민감 필드 포함 → reject
    알 수 없는 status → reject
    """
    workflow_run_id = event.get("workflow_run_id", "")

    # safe_to_execute=true 강제 reject
    if event.get("safe_to_execute") is True:
        return _reject_status_event(
            workflow_run_id, agent_id,
            "SAFE_TO_EXECUTE_MUST_BE_FALSE",
            "SAFE_TO_EXECUTE_MUST_BE_FALSE",
            "safe_to_execute=true는 허용되지 않습니다.",
        )

    # 민감 필드 포함 reject
    for field in _REJECT_FIELDS:
        if field in event:
            return _reject_status_event(
                workflow_run_id, agent_id,
                f"FORBIDDEN_FIELD field={field}",
                f"FORBIDDEN_FIELD_PRESENT: {field}",
                f"금지 필드 포함: {field}",
            )

    # contract validation
    errors = validate_user_present_ws_status_event(event)
    if errors:
        return _reject_status_event(
            workflow_run_id, agent_id,
            f"VALIDATION_FAILED errors={errors}",
            "VALIDATION_FAILED",
            "event 검증 실패.",
            validation_errors=errors,
        )

    status = event.get("status", "")
    if status not in _ACCEPTED_STATUSES:
        return _reject_status_event(
            workflow_run_id, agent_id,
            f"UNKNOWN_STATUS status={status}",
            f"UNKNOWN_STATUS: {status}",
            f"알 수 없는 status: {status}",
        )

    received_at = _now_iso()

    # in-memory 레지스트리 업데이트 (기존 호환 유지)
    _status_registry[workflow_run_id] = {
        "workflow_run_id": workflow_run_id,
        "agent_id": agent_id,
        "tenant_id": event.get("tenant_id", ""),
        "user_id": event.get("user_id", ""),
        "site_id": event.get("site_id", ""),
        "status": status,
        "status_reason": event.get("status_reason", ""),
        "safe_to_execute": False,
        "accepted_at": received_at,
        "received_at": received_at,
    }

    # status store에도 기록 (조회 API용)
    if _STORE_AVAILABLE:
        _record_status(event, agent_id=agent_id)

    # audit log
    if _AUDIT_AVAILABLE:
        _log_event(
            "LOCAL_AGENT_USER_PRESENT_STATUS_RECEIVED", workflow_run_id,
            actor=agent_id or "ws-agent",
            note=f"status={status} site_id={event.get('site_id', '')}",
        )

    logger.info(
        "[status-handler] USER_PRESENT_STATUS 수신 wf=%s status=%s agent=%s",
        workflow_run_id, status, agent_id,
    )

    return {
        "ok": True,
        "workflow_run_id": workflow_run_id,
        "accepted_status": status,
        "safe_to_execute": False,
        "received_at": received_at,
        "message_ko": f"USER_PRESENT_STATUS '{status}' 수신 완료.",
    }


def get_user_present_status(workflow_run_id: str) -> dict[str, Any] | None:
    """workflow_run_id 기준 최근 수신된 status를 반환한다."""
    entry = _status_registry.get(workflow_run_id)
    return dict(entry) if entry else None


def validate_user_present_status_event(event: dict[str, Any]) -> list[str]:
    """handle_user_present_status_event 전 사전 검증. 오류 목록 반환."""
    errors = validate_user_present_ws_status_event(event)

    if event.get("safe_to_execute") is True:
        errors.append("safe_to_execute는 항상 False여야 한다")

    for field in _REJECT_FIELDS:
        if field in event:
            errors.append(f"금지 필드 포함: {field}")

    return errors


def clear_status_registry() -> None:
    """테스트 전용: in-memory 레지스트리 초기화."""
    _status_registry.clear()

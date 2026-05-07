"""
서버 측 User-Present Status Store

local_agent로부터 수신한 USER_PRESENT_STATUS 이벤트를 in-memory 저장하고
workflow_run_id / agent_id 기준 조회를 제공한다.

원칙:
- 운영 DB write 없음
- 민감정보(password/otp/token/cookie/session/device_token) 저장 금지
- safe_to_execute 항상 False
- task_executor/browser_worker 호출 없음
- 실제 브라우저 실행 코드 없음
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# ── 저장 허용 필드 ─────────────────────────────────────────────────────────────
_STORED_FIELDS: frozenset[str] = frozenset({
    "workflow_run_id",
    "agent_id",
    "tenant_id",
    "user_id",
    "site_id",
    "status",
    "status_reason",
    "safe_to_execute",
    "received_at",
    "message_ko",
})

# ── 저장 금지 필드 ─────────────────────────────────────────────────────────────
_FORBIDDEN_STORE_FIELDS: frozenset[str] = frozenset({
    "password", "otp", "certificate_password", "financial_certificate_password",
    "token", "access_token", "refresh_token", "api_key", "device_token",
    "cookie", "session", "localStorage", "sessionStorage",
    "secret", "target_url", "registration_code",
})

# ── 허용 status 값 ─────────────────────────────────────────────────────────────
_VALID_STATUSES: frozenset[str] = frozenset({
    "WAITING_FOR_USER",
    "USER_CONFIRMED",
    "CANCELLED",
    "BLOCKED",
    "FAILED",
})

# ── in-memory store ────────────────────────────────────────────────────────────
# workflow_run_id → record
_store: dict[str, dict[str, Any]] = {}


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def validate_stored_user_present_status(record: dict[str, Any]) -> list[str]:
    """저장 레코드 검증. 오류 목록 반환."""
    errors: list[str] = []
    for field in ["workflow_run_id", "status", "received_at"]:
        if not record.get(field):
            errors.append(f"필수 필드 누락: {field}")
    if record.get("status") and record["status"] not in _VALID_STATUSES:
        errors.append(f"알 수 없는 status: {record['status']}")
    if record.get("safe_to_execute") is True:
        errors.append("safe_to_execute는 항상 False여야 한다")
    for field in _FORBIDDEN_STORE_FIELDS:
        if field in record:
            errors.append(f"저장 금지 필드 포함: {field}")
    return errors


def record_user_present_status(
    event: dict[str, Any],
    agent_id: str = "",
) -> dict[str, Any]:
    """
    USER_PRESENT_STATUS 이벤트를 store에 기록한다.

    민감 필드 포함 → reject
    safe_to_execute=true → reject
    """
    workflow_run_id = event.get("workflow_run_id", "")
    if not workflow_run_id:
        return {
            "ok": False,
            "error": "MISSING_WORKFLOW_RUN_ID",
            "message_ko": "workflow_run_id 누락.",
        }

    if event.get("safe_to_execute") is True:
        return {
            "ok": False,
            "workflow_run_id": workflow_run_id,
            "error": "SAFE_TO_EXECUTE_MUST_BE_FALSE",
            "message_ko": "safe_to_execute=true는 저장할 수 없습니다.",
        }

    for field in _FORBIDDEN_STORE_FIELDS:
        if field in event:
            return {
                "ok": False,
                "workflow_run_id": workflow_run_id,
                "error": f"FORBIDDEN_FIELD: {field}",
                "message_ko": f"금지 필드 포함: {field}",
            }

    status = event.get("status", "")
    received_at = _now_iso()

    record: dict[str, Any] = {
        "workflow_run_id": workflow_run_id,
        "agent_id": agent_id or event.get("agent_id", ""),
        "tenant_id": event.get("tenant_id", ""),
        "user_id": event.get("user_id", ""),
        "site_id": event.get("site_id", ""),
        "status": status,
        "status_reason": event.get("status_reason", ""),
        "safe_to_execute": False,
        "received_at": received_at,
        "message_ko": event.get("message_ko", f"USER_PRESENT_STATUS '{status}' 수신."),
    }

    errors = validate_stored_user_present_status(record)
    if errors:
        return {
            "ok": False,
            "workflow_run_id": workflow_run_id,
            "error": "VALIDATION_FAILED",
            "validation_errors": errors,
            "message_ko": "저장 검증 실패.",
        }

    _store[workflow_run_id] = record
    return {
        "ok": True,
        "workflow_run_id": workflow_run_id,
        "status": status,
        "received_at": received_at,
        "safe_to_execute": False,
        "message_ko": f"USER_PRESENT_STATUS '{status}' 저장 완료.",
    }


def get_user_present_status(workflow_run_id: str) -> dict[str, Any] | None:
    """workflow_run_id 기준 최신 status record 반환. 없으면 None."""
    entry = _store.get(workflow_run_id)
    return dict(entry) if entry else None


def list_user_present_statuses(
    agent_id: str | None = None,
) -> list[dict[str, Any]]:
    """agent_id 기준 status 목록 반환. agent_id 없으면 전체 반환."""
    records = list(_store.values())
    if agent_id:
        records = [r for r in records if r.get("agent_id") == agent_id]
    return sorted(records, key=lambda r: r.get("received_at", ""), reverse=True)


def clear_store_for_testing() -> None:
    """테스트 전용: store 초기화."""
    _store.clear()


__all__ = [
    "record_user_present_status",
    "get_user_present_status",
    "list_user_present_statuses",
    "validate_stored_user_present_status",
    "clear_store_for_testing",
]

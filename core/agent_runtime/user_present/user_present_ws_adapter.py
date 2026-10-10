"""
Local Agent User-Present WebSocket Adapter

서버로부터 수신한 USER_PRESENT_TASK message를
local user_present_state_store에 등록하고
상태 전이 후 USER_PRESENT_STATUS event를 생성한다.

실제 WebSocket 운영 송신 없음.
browser action/click/type/submit 실행 없음.
safe_to_execute는 항상 False.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ai_orchestrator.contracts.user_present_ws_contract import (
    STATUS_BLOCKED,
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_USER_CONFIRMED,
    STATUS_WAITING_FOR_USER,
    build_user_present_ws_status_event,
    sanitize_user_present_ws_payload,
    validate_user_present_ws_task_message,
)
from core.agent_runtime.user_present.user_present_state_store import (
    _CANCELLABLE_STATES,
    _CONFIRMABLE_STATES,
    STATE_BLOCKED,
    STATE_CANCELLED,
    STATE_FAILED,
    STATE_USER_CONFIRMED,
    STATE_WAITING_FOR_USER,
    UserPresentStateStore,
    default_store,
)


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def receive_user_present_task_message(
    message: dict[str, Any],
    store: UserPresentStateStore | None = None,
) -> dict[str, Any]:
    """
    서버로부터 수신한 USER_PRESENT_TASK message를 검증하고
    local state_store에 등록할 수 있는 payload로 변환한다.

    sanitize 후 validation을 수행한다.
    validation 실패 시 task를 생성하지 않고 오류를 반환한다.
    """
    # sanitize 먼저 수행 (금지 필드 제거, raw URL 변환)
    clean = sanitize_user_present_ws_payload(message)

    errors = validate_user_present_ws_task_message(clean)
    if errors:
        return {
            "ok": False,
            "errors": errors,
            "safe_to_execute": False,
            "status": STATUS_BLOCKED,
        }

    return {
        "ok": True,
        "errors": [],
        "safe_to_execute": False,
        "payload": clean,
    }


def create_local_user_present_task_from_ws(
    message: dict[str, Any],
    store: UserPresentStateStore | None = None,
) -> dict[str, Any]:
    """
    검증된 USER_PRESENT_TASK message로부터 local state_store에 task를 생성한다.
    message validation 실패 시 task를 생성하지 않는다.
    """
    _store = store or default_store

    result = receive_user_present_task_message(message)
    if not result["ok"]:
        return {
            "ok": False,
            "errors": result["errors"],
            "task": None,
            "safe_to_execute": False,
        }

    payload = result["payload"]
    task = _store.create_user_present_task(payload)
    task = _store.mark_waiting_for_user(task["workflow_run_id"])

    return {
        "ok": True,
        "errors": [],
        "task": task,
        "safe_to_execute": False,
    }


def build_ws_status_event_from_local_task(task: dict[str, Any]) -> dict[str, Any]:
    """
    local task dict → USER_PRESENT_STATUS event 변환.
    상태 전이 없이 현재 상태를 event로 변환만 수행한다.
    """
    state = task.get("state", STATE_BLOCKED)
    # state_store state → ws status 매핑
    _state_to_status: dict[str, str] = {
        STATE_WAITING_FOR_USER: STATUS_WAITING_FOR_USER,
        STATE_USER_CONFIRMED: STATUS_USER_CONFIRMED,
        STATE_CANCELLED: STATUS_CANCELLED,
        STATE_BLOCKED: STATUS_BLOCKED,
        STATE_FAILED: STATUS_FAILED,
    }
    status = _state_to_status.get(state, STATUS_BLOCKED)

    return build_user_present_ws_status_event({
        "workflow_run_id": task.get("workflow_run_id", ""),
        "tenant_id": task.get("tenant_id", ""),
        "user_id": task.get("user_id", ""),
        "site_id": task.get("site_id", ""),
        "status": status,
        "status_reason": task.get("status_reason", ""),
        "created_at": _now_iso(),
    })


def mark_local_user_confirmed_and_build_event(
    workflow_run_id: str,
    store: UserPresentStateStore | None = None,
) -> dict[str, Any]:
    """
    USER_CONFIRMED 상태 전이를 수행하고 status event를 반환한다.
    browser action/click/type/submit을 실행하지 않는다.
    WAITING_FOR_USER 상태일 때만 가능하다.
    """
    _store = store or default_store

    task = _store.get_user_present_task(workflow_run_id)
    if task is None:
        return {
            "ok": False,
            "errors": [f"task not found: {workflow_run_id}"],
            "event": None,
            "safe_to_execute": False,
        }

    if task["state"] not in _CONFIRMABLE_STATES:
        return {
            "ok": False,
            "errors": [f"상태 전이 불가: {task['state']} → USER_CONFIRMED"],
            "event": None,
            "safe_to_execute": False,
        }

    updated = _store.mark_user_confirmed(workflow_run_id)
    event = build_ws_status_event_from_local_task(updated)

    return {
        "ok": True,
        "errors": [],
        "event": event,
        "safe_to_execute": False,
    }


def mark_local_user_cancelled_and_build_event(
    workflow_run_id: str,
    store: UserPresentStateStore | None = None,
) -> dict[str, Any]:
    """
    CANCELLED 상태 전이를 수행하고 status event를 반환한다.
    """
    _store = store or default_store

    task = _store.get_user_present_task(workflow_run_id)
    if task is None:
        return {
            "ok": False,
            "errors": [f"task not found: {workflow_run_id}"],
            "event": None,
            "safe_to_execute": False,
        }

    if task["state"] not in _CANCELLABLE_STATES:
        return {
            "ok": False,
            "errors": [f"상태 전이 불가: {task['state']} → CANCELLED"],
            "event": None,
            "safe_to_execute": False,
        }

    updated = _store.mark_user_cancelled(workflow_run_id)
    event = build_ws_status_event_from_local_task(updated)

    return {
        "ok": True,
        "errors": [],
        "event": event,
        "safe_to_execute": False,
    }


# ── status event builder helpers ─────────────────────────────────────────────

def _get_task_context(
    workflow_run_id: str,
    store: UserPresentStateStore | None = None,
) -> dict[str, Any]:
    _store = store or default_store
    task = _store.get_user_present_task(workflow_run_id)
    if task is None:
        return {"workflow_run_id": workflow_run_id}
    return {
        "workflow_run_id": workflow_run_id,
        "tenant_id": task.get("tenant_id", ""),
        "user_id": task.get("user_id", ""),
        "site_id": task.get("site_id", ""),
    }


def build_waiting_status_event(
    workflow_run_id: str,
    store: UserPresentStateStore | None = None,
) -> dict[str, Any]:
    """WAITING_FOR_USER status event를 생성한다."""
    ctx = _get_task_context(workflow_run_id, store)
    return build_user_present_ws_status_event({
        **ctx,
        "status": STATUS_WAITING_FOR_USER,
        "status_reason": "사용자 직접 인증 대기 중",
    })


def build_confirmed_status_event(
    workflow_run_id: str,
    store: UserPresentStateStore | None = None,
) -> dict[str, Any]:
    """USER_CONFIRMED status event를 생성한다. 상태 전이는 수행하지 않는다."""
    ctx = _get_task_context(workflow_run_id, store)
    return build_user_present_ws_status_event({
        **ctx,
        "status": STATUS_USER_CONFIRMED,
        "status_reason": "사용자 인증 완료",
    })


def build_cancelled_status_event(
    workflow_run_id: str,
    store: UserPresentStateStore | None = None,
) -> dict[str, Any]:
    """CANCELLED status event를 생성한다. 상태 전이는 수행하지 않는다."""
    ctx = _get_task_context(workflow_run_id, store)
    return build_user_present_ws_status_event({
        **ctx,
        "status": STATUS_CANCELLED,
        "status_reason": "사용자 취소",
    })


def build_failed_status_event(
    workflow_run_id: str,
    reason: str = "",
    store: UserPresentStateStore | None = None,
) -> dict[str, Any]:
    """FAILED status event를 생성한다. 상태 전이는 수행하지 않는다."""
    ctx = _get_task_context(workflow_run_id, store)
    return build_user_present_ws_status_event({
        **ctx,
        "status": STATUS_FAILED,
        "status_reason": reason or "처리 실패",
    })

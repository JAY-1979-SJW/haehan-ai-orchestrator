"""
Local Agent User-Present Status Auto-Sender

state_store에서 FINAL 상태(USER_CONFIRMED/CANCELLED/BLOCKED/FAILED) task를 감지하고
USER_PRESENT_STATUS 메시지를 WebSocket으로 자동 전송한다.

원칙:
- safe_to_execute는 항상 False
- 민감정보(password/otp/token/cookie/session) 포함 event 전송 거부
- 실제 브라우저/Playwright 실행 없음
- browser automation 모듈 호출 없음
- 별도 background thread 없음 — 호출자(heartbeat)가 주기적으로 실행
- 중복 전송 방지: workflow_run_id+status 기준 sent marker
"""

from __future__ import annotations

import logging
from typing import Any

from core.agent_runtime.user_present.user_present_state_store import (
    STATE_BLOCKED,
    STATE_CANCELLED,
    STATE_FAILED,
    STATE_USER_CONFIRMED,
    UserPresentStateStore,
    default_store,
)
from core.agent_runtime.user_present.user_present_ws_adapter import build_ws_status_event_from_local_task

logger = logging.getLogger(__name__)

# 전송 대상 FINAL 상태
_SEND_TARGET_STATES: frozenset[str] = frozenset(
    {
        STATE_USER_CONFIRMED,
        STATE_CANCELLED,
        STATE_BLOCKED,
        STATE_FAILED,
    }
)

# 민감정보 금지 필드 — event 포함 시 전송 거부
_FORBIDDEN_EVENT_FIELDS: frozenset[str] = frozenset(
    {
        "password",
        "otp",
        "certificate_password",
        "financial_certificate_password",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "device_token",
        "cookie",
        "session",
        "localStorage",
        "sessionStorage",
        "secret",
        "target_url",
    }
)

# 중복 전송 방지 — {workflow_run_id: last_sent_status}
# in-memory: 프로세스 재시작 시 초기화(재전송 허용)
_sent_statuses: dict[str, str] = {}


def _is_sensitive(event: dict[str, Any]) -> bool:
    """event에 민감정보 필드가 있으면 True."""
    return bool(_FORBIDDEN_EVENT_FIELDS & set(event.keys()))


def collect_pending_user_present_status_events(
    store: UserPresentStateStore | None = None,
) -> list[dict[str, Any]]:
    """
    FINAL 상태 task 중 아직 전송하지 않은 것의 status event 목록을 반환한다.

    WAITING_FOR_USER는 포함하지 않는다.
    이미 sent marker가 있는 항목은 제외한다.
    """
    _store = store or default_store
    tasks = _store.list_user_present_tasks()
    pending: list[dict[str, Any]] = []
    for task in tasks:
        state = task.get("state", "")
        if state not in _SEND_TARGET_STATES:
            continue
        wf_id = task.get("workflow_run_id", "")
        if _sent_statuses.get(wf_id) == state:
            continue
        event = build_ws_status_event_from_local_task(task)
        pending.append(event)
    return pending


def mark_user_present_status_sent(
    workflow_run_id: str,
    status: str,
) -> dict[str, Any]:
    """
    전송 완료된 workflow_run_id + status를 sent marker에 기록한다.
    같은 상태의 중복 전송을 방지한다.
    """
    _sent_statuses[workflow_run_id] = status
    return {"ok": True, "workflow_run_id": workflow_run_id, "marked_status": status}


def _validate_event_for_send(event: dict[str, Any]) -> list[str]:
    """전송 전 event 검증. 오류 목록 반환(비면 OK)."""
    errors: list[str] = []
    if event.get("safe_to_execute") is True:
        errors.append("BLOCKED_SAFE_TO_EXECUTE_TRUE: safe_to_execute=true 이벤트 전송 거부")
    if _is_sensitive(event):
        found = [f for f in _FORBIDDEN_EVENT_FIELDS if f in event]
        errors.append(f"BLOCKED_SENSITIVE_FIELD: 민감 필드 포함 — {found}")
    if not event.get("workflow_run_id"):
        errors.append("BLOCKED_MISSING_WORKFLOW_RUN_ID")
    if not event.get("status"):
        errors.append("BLOCKED_MISSING_STATUS")
    return errors


async def send_user_present_status_event(
    ws: Any,
    event: dict[str, Any],
) -> dict[str, Any]:
    """
    검증 후 USER_PRESENT_STATUS event를 WebSocket으로 전송한다 (fire-and-forget).

    - safe_to_execute=true / 민감필드 포함 시 전송 거부
    - send() 성공 시 즉시 sent marker 기록 (서버 ack 대기 없음)
      → WS duplex 스트림에서 ack 대기 시 다른 메시지와 순서 충돌 방지
    - send() 실패 시 sent marker 미기록 (다음 heartbeat 재시도)

    서버는 "type": "user_present_status" 메시지를 event 필드들이 flat하게
    포함된 형태로 수신한다: {"type": "user_present_status", **event_fields}
    """
    errors = _validate_event_for_send(event)
    if errors:
        logger.warning("[status-sender] 전송 거부: %s", errors)
        return {"ok": False, "errors": errors, "sent": False}

    wf_id = event.get("workflow_run_id", "")
    status = event.get("status", "")

    import json

    # 서버 WS 핸들러는 msg.get("type") == "user_present_status" 로 분기,
    # 이후 msg 전체를 handler에 전달 — event 필드를 flat하게 포함해야 함
    payload = {"type": "user_present_status", **event}
    try:
        await ws.send(json.dumps(payload))
    except Exception as exc:  # noqa: BLE001 - WebSocket status 전송 실패를 캡처해 ok=False, sent=False 로 안전하게 반환 - 전송 실패를 성공으로 위장하지 않음
        logger.warning("[status-sender] WS send 실패 wf=%s: %s", wf_id, type(exc).__name__)
        return {"ok": False, "errors": [f"SEND_ERROR: {type(exc).__name__}"], "sent": False}

    # send 성공 → sent marker 기록 (fire-and-forget)
    mark_user_present_status_sent(wf_id, status)
    logger.info("[status-sender] USER_PRESENT_STATUS 전송 wf=%s status=%s", wf_id, status)
    return {"ok": True, "errors": [], "sent": True}


async def run_user_present_status_send_once(
    ws: Any,
    store: UserPresentStateStore | None = None,
) -> dict[str, Any]:
    """
    pending event 전부를 한 번씩 전송 시도한다.
    heartbeat 이후 또는 receive loop에서 주기적으로 호출한다.

    반환: {"sent": int, "failed": int, "skipped": int}
    """
    pending = collect_pending_user_present_status_events(store)
    sent = failed = 0
    for event in pending:
        result = await send_user_present_status_event(ws, event)
        if result.get("sent"):
            sent += 1
        elif result.get("ok") is False and result.get("errors"):
            # 검증 거부(민감필드/safe_to_execute)는 재시도 없이 영구 skip
            _errs = result["errors"]
            if any("BLOCKED_" in e for e in _errs):
                wf_id = event.get("workflow_run_id", "")
                _sent_statuses[wf_id] = event.get("status", "BLOCKED")
                logger.warning("[status-sender] 영구 skip wf=%s errors=%s", wf_id, _errs)
            failed += 1
    return {"sent": sent, "failed": failed, "skipped": 0}


def reset_sent_statuses_for_testing() -> None:
    """테스트 전용: sent marker 초기화."""
    _sent_statuses.clear()


__all__ = [
    "collect_pending_user_present_status_events",
    "mark_user_present_status_sent",
    "reset_sent_statuses_for_testing",
    "run_user_present_status_send_once",
    "send_user_present_status_event",
]

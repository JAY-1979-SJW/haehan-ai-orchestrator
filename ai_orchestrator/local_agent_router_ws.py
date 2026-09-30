"""local_agent WebSocket 엔드포인트 (Stage 2) — leaf 서브라우터.

에이전트 ↔ 서버 WS 프로토콜(auth/heartbeat/pull/running/result) 핸들러와 보조함수.
컴포지션 루트(local_agent_router)가 include_router 로 관리.
공유 leaf(up_queue/guards) + registry/auth 사용. [docs/module_separation_standard.md]
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from . import local_agent_registry as _reg
from . import local_agent_router_guards as _guards  # 공유 leaf
from .audit_logger import log_event
from .local_agent_router_up_queue import _drain_up_tasks  # 공유 leaf

try:
    from .browser_tool.local_agent_user_present_status_handler import (
        handle_user_present_status_event as _handle_up_status_event,
    )

    _UP_STATUS_HANDLER_AVAILABLE = True
except ImportError:
    _UP_STATUS_HANDLER_AVAILABLE = False

logger = logging.getLogger(__name__)

ws_router = APIRouter()


# ── WebSocket (Stage 2) ────────────────────────────────────────────────
#
# 인증 흐름:
#   1. 클라이언트가 연결 후 첫 메시지로 {"type":"auth","agent_id","device_token"} 전송
#   2. 서버는 authenticate_agent() 로 검증. 실패 시 즉시 close(4401) — 이후 통신 없음
#   3. 성공 시 agent_id 소유 큐의 queued 작업을 모두 push (mark_delivered)
#
# 허용 메시지 타입 (클라→서버):
#   - auth       (1회만)
#   - heartbeat  → heartbeat_ack + 신규 queued 작업 push
#   - pull       → 신규 queued 작업 push
#   - running    {task_id}
#   - result     {task_id, success, summary, error_code, error}
#
# 서버→클라:
#   - auth_ok   {agent_id}
#   - task      {task}                 (queued → delivered 로 전환된 작업)
#   - running_ack {task_id}
#   - result_ack  {task_id, status}
#   - idle       (keepalive timeout)
#   - error      {error, message}
#
# 보안:
#   - device_token 원문은 authenticate_agent() 의 로컬 변수로만 존재, 로그 금지
#   - agent_id 불일치 (auth 이후 message 의 agent_id 가 다름) 는 error 응답
#   - high risk 작업은 애초에 status=waiting_approval 로 큐에 남아있지 않으므로
#     WS 로 전달되지 않는다 (queued 상태만 전달).

_WS_RECV_TIMEOUT_SEC = 30  # keepalive/idle push 주기


def _safe_str(value) -> str:
    return "" if value is None else str(value)


async def _push_queued(ws: WebSocket, agent_id: str) -> int:
    """해당 에이전트의 queued 작업을 최대 1개 delivered 로 전환하며 push. 전송 개수 반환."""
    # A single local-agent WebSocket session is sequential:
    # task -> running_ack -> result -> next task.
    if _reg.get_active_task_count(agent_id) > 0:
        return 0
    pending = _reg.list_pending_for_agent(agent_id)
    sent = 0
    for t in pending[:1]:
        updated = _reg.mark_delivered(agent_id, t.task_id)
        if updated is None or updated.status != "delivered":
            continue
        await ws.send_json(
            {
                "type": "task",
                "task": updated.to_dispatch(),
            }
        )
        log_event(
            "LOCAL_AGENT_TASK_DELIVERED",
            updated.task_id,
            risk_level=updated.risk_level,
            action_type=updated.action,
            actor="ws-dispatch",
            note=f"agent_id={agent_id}",
        )
        sent += 1
    return sent


async def _push_user_present_tasks(ws: WebSocket, agent_id: str) -> int:
    """USER_PRESENT_TASK 전송 대기 큐를 드레인하여 push. 전송 개수 반환."""
    tasks = _drain_up_tasks(agent_id)
    for task_msg in tasks:
        await ws.send_json(
            {
                "type": "user_present_task",
                "task": task_msg,
            }
        )
    return len(tasks)


async def _send_task_blocked(
    ws: WebSocket,
    *,
    task_id: str = "",
    workflow_run_id: str = "",
    reason: str = "",
    message_ko: str = "",
) -> None:
    """정책/dispatcher 차단을 클라이언트에 통지한다.

    task_blocked 는 실행 명령이 아닌 상태/사유 통지 메시지다.
    UI 측에서 차단 사유를 사용자에게 표시할 수 있도록 한다.
    민감 필드(token/cookie/authorization 등)는 포함 금지.
    """
    # 로컬 에이전트 WebSocket 서버(인증 후 통신) — 인증(authenticate_agent) 검증은 이 함수 호출 이전
    # 로직에서 처리되며 실패 시 close(4401)로 명확히 거부된다. 여기서 억제하는 예외는 상태 통지 전송
    # 실패뿐으로, 인증을 우회하지 않는다.
    with contextlib.suppress(Exception):
        await ws.send_json(
            {
                "type": "task_blocked",
                "task_id": _safe_str(task_id)[:80],
                "workflow_run_id": _safe_str(workflow_run_id)[:120],
                "reason": _safe_str(reason)[:80],
                "message_ko": _safe_str(message_ko)[:200],
                "safe_to_execute": False,
            }
        )


async def _handle_result(ws: WebSocket, agent_id: str, msg: dict) -> None:
    task_id = _safe_str(msg.get("task_id"))
    if not task_id:
        await ws.send_json(
            {
                "type": "error",
                "error": "MISSING_TASK_ID",
                "message": "result 메시지에 task_id 가 없습니다",
            }
        )
        return

    existing = _reg.get_task(agent_id, task_id)
    if existing is None:
        # 다른 agent 의 task_id 를 주장하거나 존재하지 않는 작업 — 거절
        await ws.send_json(
            {
                "type": "error",
                "error": "TASK_NOT_FOUND",
                "task_id": task_id,
            }
        )
        log_event(
            "LOCAL_AGENT_TASK_REJECTED",
            task_id,
            actor="ws-dispatch",
            note=f"agent_id={agent_id} reason=UNKNOWN_TASK_IN_RESULT",
        )
        return

    # 멱등 보강: 이미 최종 상태인 task 에 대한 result 재수신은 상태 재변경/이벤트
    # 재발행 없이 ack 만 반환한다. result_ack 손실로 인한 재실행을 방지한다.
    _FINAL_RESULT_STATES = ("completed", "failed", "rejected", "cancelled")
    if existing.status in _FINAL_RESULT_STATES:
        await ws.send_json(
            {
                "type": "result_ack",
                "task_id": task_id,
                "status": existing.status,
                "idempotent": True,
            }
        )
        return

    success = bool(msg.get("success", False))
    summary = _safe_str(msg.get("summary"))[:500]
    error = _safe_str(msg.get("error"))[:500]
    error_code = _safe_str(msg.get("error_code"))[:80]
    raw_observe = msg.get("observe_summary")
    observe_summary = raw_observe if isinstance(raw_observe, dict) else None
    raw_audit = msg.get("audit_summary")
    audit_summary = raw_audit if isinstance(raw_audit, dict) else None
    raw_data = msg.get("data")
    result_data = raw_data if isinstance(raw_data, dict) else None

    updated = _reg.apply_result(
        agent_id=agent_id,
        task_id=task_id,
        success=success,
        summary=summary,
        error=error,
        error_code=error_code,
        observe_summary=observe_summary,
        audit_summary=audit_summary,
        data=result_data,
    )
    if updated is None:
        await ws.send_json(
            {
                "type": "error",
                "error": "TASK_NOT_FOUND",
                "task_id": task_id,
            }
        )
        return

    if updated.status == "completed":
        log_event(
            "LOCAL_AGENT_TASK_COMPLETED",
            task_id,
            risk_level=updated.risk_level,
            action_type=updated.action,
            actor="ws-agent",
            note=f"agent_id={agent_id}",
        )
        if _guards.is_capture_screenshot_task(updated):
            dry = _guards.task_is_dry_run(updated)
            # summary 도 fallback 으로 검사 — task.params 가 어떤 이유로 손실돼도
            # client 가 보낸 summary 접두("dry_run:true") 로 분기할 수 있다.
            if not dry and updated.result_summary.startswith("dry_run:true"):
                dry = True
            log_event(
                ("CAPTURE_SCREENSHOT_DRY_RUN_COMPLETED" if dry else "CAPTURE_SCREENSHOT_COMPLETED"),
                task_id,
                risk_level=updated.risk_level,
                action_type=updated.action,
                actor="ws-agent",
                note=f"agent_id={agent_id}",
            )
    elif updated.status == "failed":
        log_event(
            "LOCAL_AGENT_TASK_FAILED",
            task_id,
            risk_level=updated.risk_level,
            action_type=updated.action,
            actor="ws-agent",
            decision=error_code or "failed",
            note=f"agent_id={agent_id}",
        )
        if _guards.is_capture_screenshot_task(updated):
            log_event(
                "CAPTURE_SCREENSHOT_FAILED",
                task_id,
                risk_level=updated.risk_level,
                action_type=updated.action,
                actor="ws-agent",
                decision=error_code or "failed",
                note=f"agent_id={agent_id}",
            )

    await ws.send_json(
        {
            "type": "result_ack",
            "task_id": task_id,
            "status": updated.status,
        }
    )


async def _handle_running(ws: WebSocket, agent_id: str, msg: dict) -> None:
    task_id = _safe_str(msg.get("task_id"))
    if not task_id:
        await ws.send_json(
            {
                "type": "error",
                "error": "MISSING_TASK_ID",
            }
        )
        return
    updated = _reg.mark_running(agent_id, task_id)
    if updated is None:
        await ws.send_json(
            {
                "type": "error",
                "error": "TASK_NOT_FOUND",
                "task_id": task_id,
            }
        )
        return
    if updated.status == "running":
        log_event(
            "LOCAL_AGENT_TASK_RUNNING",
            task_id,
            risk_level=updated.risk_level,
            action_type=updated.action,
            actor="ws-agent",
            note=f"agent_id={agent_id}",
        )
    await ws.send_json(
        {
            "type": "running_ack",
            "task_id": task_id,
            "status": updated.status,
        }
    )


@ws_router.websocket("/ws")
async def agent_websocket(websocket: WebSocket):
    """로컬 에이전트 WebSocket 엔드포인트.

    - 최초 메시지로 auth 를 받아 device_token 을 검증한다.
    - 인증 실패 시 code=4401 로 close. HTTP 상태/본문 노출 없음.
    - 이후 heartbeat / pull / running / result 메시지를 처리.
    - 민감한 device_token 원문은 로컬 변수 범위를 벗어나지 않는다.
    """
    await websocket.accept()
    agent_id: str = ""
    try:
        # 1) 인증 메시지 수신 (10초 내)
        try:
            auth_msg = await asyncio.wait_for(
                websocket.receive_json(),
                timeout=10.0,
            )
        except TimeoutError:
            log_event(
                "LOCAL_AGENT_WS_AUTH_FAILED",
                "local-agent",
                actor="ws-dispatch",
                note="reason=AUTH_TIMEOUT",
            )
            await websocket.close(code=4401)
            return
        except WebSocketDisconnect:
            return

        if not isinstance(auth_msg, dict) or auth_msg.get("type") != "auth":
            log_event(
                "LOCAL_AGENT_WS_AUTH_FAILED",
                "local-agent",
                actor="ws-dispatch",
                note="reason=AUTH_MESSAGE_REQUIRED",
            )
            await websocket.close(code=4401)
            return

        claimed_agent_id = _safe_str(auth_msg.get("agent_id"))
        device_token = _safe_str(auth_msg.get("device_token"))
        # device_token 원문을 로그에 남기지 않기 위해 별도 변수 없이 바로 전달
        authed = _reg.authenticate_agent(claimed_agent_id, device_token)
        # 참조 제거 (메모리상 흔적 최소화)
        device_token = ""
        if authed is None:
            log_event(
                "LOCAL_AGENT_WS_AUTH_FAILED",
                claimed_agent_id or "local-agent",
                actor="ws-dispatch",
                note=f"agent_id={claimed_agent_id or '-'} reason=BAD_CREDENTIALS",
            )
            await websocket.close(code=4401)
            return

        agent_id = authed.agent_id
        now_connected = _reg._now_iso()
        _reg.set_agent_connected(agent_id, now_connected)
        log_event(
            "LOCAL_AGENT_WS_CONNECTED",
            agent_id,
            actor="ws-dispatch",
            note=f"host={authed.host} ver={authed.version}",
        )
        await websocket.send_json(
            {
                "type": "auth_ok",
                "agent_id": agent_id,
            }
        )

        # 2) 초기 큐 드레인
        await _push_queued(websocket, agent_id)

        # 3) 메시지 루프
        while True:
            try:
                msg = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=_WS_RECV_TIMEOUT_SEC,
                )
            except TimeoutError:
                # 유휴 — 신규 큐 작업 push + keepalive
                _reg.set_agent_last_seen(agent_id)
                await _push_queued(websocket, agent_id)
                expired = _reg.expire_stale_tasks()
                for t in expired:
                    log_event(
                        "LOCAL_AGENT_TASK_TIMEOUT",
                        t.task_id,
                        actor="ws-timeout",
                        note=(
                            f"agent_id={t.agent_id}"
                            f" failure_reason={t.failure_reason}"
                            f" status=failed"
                            f" timed_out_at={t.timed_out_at}"
                        ),
                    )
                try:
                    await websocket.send_json({"type": "idle"})
                except Exception as exc:
                    raise WebSocketDisconnect() from exc
                continue

            if not isinstance(msg, dict):
                await websocket.send_json(
                    {
                        "type": "error",
                        "error": "INVALID_MESSAGE",
                    }
                )
                continue

            # auth 이후 메시지의 agent_id 는 반드시 일치해야 한다.
            msg_agent_id = _safe_str(msg.get("agent_id"))
            if msg_agent_id and msg_agent_id != agent_id:
                await websocket.send_json(
                    {
                        "type": "error",
                        "error": "AGENT_ID_MISMATCH",
                    }
                )
                continue

            mtype = _safe_str(msg.get("type"))
            if mtype == "heartbeat":
                _reg.set_agent_last_seen(agent_id)
                await websocket.send_json({"type": "heartbeat_ack"})
                await _push_queued(websocket, agent_id)
                await _push_user_present_tasks(websocket, agent_id)
            elif mtype == "pull":
                await _push_queued(websocket, agent_id)
                await _push_user_present_tasks(websocket, agent_id)
            elif mtype == "running":
                _reg.set_agent_last_seen(agent_id)
                await _handle_running(websocket, agent_id, msg)
            elif mtype == "result":
                _reg.set_agent_last_seen(agent_id)
                await _handle_result(websocket, agent_id, msg)
                await _push_queued(websocket, agent_id)
            elif mtype == "user_present_status":
                _reg.set_agent_last_seen(agent_id)
                if _UP_STATUS_HANDLER_AVAILABLE:
                    _result = _handle_up_status_event(msg, agent_id=agent_id)
                    await websocket.send_json(
                        {
                            "type": "user_present_status_ack",
                            "ok": _result.get("ok", False),
                            "workflow_run_id": _result.get("workflow_run_id", ""),
                            "accepted_status": _result.get("accepted_status"),
                            "safe_to_execute": False,
                            "received_at": _result.get("received_at", ""),
                            "error": _result.get("error", ""),
                        }
                    )
                    # 정책상 BLOCKED 로 수렴된 경우 클라이언트에 차단 사유를 추가 통지.
                    if _result.get("accepted_status") == "BLOCKED":
                        await _send_task_blocked(
                            websocket,
                            workflow_run_id=_safe_str(_result.get("workflow_run_id", "")),
                            reason=_safe_str(_result.get("block_reason", "POLICY_BLOCKED")),
                            message_ko=_safe_str(_result.get("message_ko", "")),
                        )
                else:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "error": "USER_PRESENT_HANDLER_UNAVAILABLE",
                        }
                    )
            elif mtype == "user_present_ack":
                # 로컬 Agent의 USER_PRESENT_TASK 수신 확인 — 로그만
                _reg.set_agent_last_seen(agent_id)
            elif mtype == "auth":
                # 재인증 요청은 거절 (이미 인증된 세션)
                await websocket.send_json(
                    {
                        "type": "error",
                        "error": "ALREADY_AUTHENTICATED",
                    }
                )
            else:
                await websocket.send_json(
                    {
                        "type": "error",
                        "error": "UNKNOWN_MESSAGE_TYPE",
                        "received": mtype[:40],
                    }
                )
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.exception("agent websocket 예외: %s", e)
        # 이미 예외로 종료 중인 연결의 close() 실패는 무시해도 안전(인증 우회 아님)
        with contextlib.suppress(Exception):
            await websocket.close(code=1011)
    finally:
        if agent_id:
            _reg.set_agent_disconnected(agent_id)
            failed_on_disconnect, requeued_on_disconnect = _reg.fail_active_tasks_for_agent(agent_id)
            for t in failed_on_disconnect:
                log_event(
                    "LOCAL_AGENT_TASK_FAILED",
                    t.task_id,
                    risk_level=t.risk_level,
                    action_type=t.action,
                    actor="ws-disconnect",
                    decision="failed",
                    note=(f"agent_id={agent_id} failure_reason={t.failure_reason} status=failed"),
                )
            for t in requeued_on_disconnect:
                # 2026-09-30: 연결 끊김 자체는 실패가 아니라 재큐잉 — 재연결 시
                # _push_queued()가 자동으로 다시 전달한다(local_agent_registry_task_lifecycle.py
                # fail_active_tasks_for_agent 참고).
                log_event(
                    "LOCAL_AGENT_TASK_REQUEUED",
                    t.task_id,
                    risk_level=t.risk_level,
                    action_type=t.action,
                    actor="ws-disconnect",
                    decision="requeued",
                    note=(f"agent_id={agent_id} retry_count={t.retry_count}"),
                )
            log_event(
                "LOCAL_AGENT_WS_DISCONNECTED",
                agent_id,
                actor="ws-dispatch",
            )


__all__ = [
    "ws_router"
]  # 2026-09-29 defect_index #38: 실제 정의된 이름과 다른 이름을 선언하고 있었음(존재한 적 없는 local_agent_router)

"""로컬 에이전트 등록·조회·작업 큐 API (Stage 1/2).

엔드포인트:
  POST /api/v1/local-agents/register                    (admin/owner)
  GET  /api/v1/local-agents                             (admin/owner/viewer)
  POST /api/v1/local-agents/{agent_id}/tasks            (admin/owner)
  GET  /api/v1/local-agents/{agent_id}/tasks            (admin/owner/viewer)
  GET  /api/v1/local-agents/{agent_id}/tasks/{task_id}  (admin/owner/viewer)
  WS   /api/v1/local-agents/ws                          (device_token 인증)

작업 흐름:
  - low + 서버 자동완료 (ping/system_info/list_allowed_apps) → status=completed
  - low + PC 의존 (open_url) → status=queued → (WS) delivered → running → completed/failed
  - medium (list_files_readonly) → status=queued → (WS) delivered → running → completed/failed
  - high (capture_screenshot) → issue_token_for_dev_reg + status=waiting_approval
    (Stage 2 에서도 실제 실행은 하지 않음 — 에이전트가 NOT_IMPLEMENTED_STAGE2 반환)

보안:
  - device_token 원문은 register 응답에 1회만 노출
  - params 의 민감 키는 등록 시점에 제거 (registry._strip_sensitive)
  - audit log 에 token 원문 / device_token 원문 절대 기록 금지
  - WS 인증 실패는 로그에 agent_id / 원인 코드만, token 원문은 기록/반영 금지
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import (
    APIRouter, Body, Depends, HTTPException, Query,
    WebSocket, WebSocketDisconnect,
)
from pydantic import BaseModel

from .auth import require_role
from .audit_logger import log_event
from .approval import issue_token_for_dev_reg, approve_token, reject_token
from . import local_agent_registry as _reg

logger = logging.getLogger(__name__)

local_agent_router = APIRouter(prefix="/local-agents", tags=["local-agents"])


# ── 요청 모델 ────────────────────────────────────────────────────────────

class AgentRegisterRequest(BaseModel):
    host: str = ""
    os_name: str = ""
    version: str = "0.1.0"


class AgentTaskRequest(BaseModel):
    action: str
    params: dict = {}


class AgentTaskApprovalRequest(BaseModel):
    token_id: str
    reason: str = ""


class CaptureScreenshotRequest(BaseModel):
    """운영자 capture_screenshot 요청 body.

    - dry_run 기본값은 True. 생략/빈 body/{} 는 모두 dry_run=True 로 처리.
    - dry_run=False 는 명시적으로 false 를 전달한 경우에만 적용.
    - reason/note 는 감사 메모용 텍스트 (민감값 제거 로직을 거친 뒤 저장).
    """
    dry_run: bool = True
    reason: str = ""
    note: str = ""


_APPROVE_STATUS_HTTP = {
    "approved": 200, "not_found": 404, "task_mismatch": 400,
    "already_used": 409, "expired": 410, "forbidden": 403,
    "rate_limited": 429,
}
_REJECT_STATUS_HTTP = {
    "rejected": 200, "not_found": 404, "task_mismatch": 400,
    "already_used": 409, "expired": 410, "forbidden": 403,
    "rate_limited": 429,
}
_APPROVE_AUDIT_EVENT = {
    "approved": "LOCAL_AGENT_TASK_APPROVED",
    "not_found": "APPROVAL_INVALID_TOKEN",
    "task_mismatch": "APPROVAL_INVALID_TOKEN",
    "already_used": "APPROVAL_ALREADY_USED",
    "expired": "LOCAL_AGENT_TASK_APPROVAL_EXPIRED",
    "forbidden": "APPROVAL_DENIED",
    "rate_limited": "APPROVAL_RATE_LIMITED",
}
_REJECT_AUDIT_EVENT = {
    "rejected": "LOCAL_AGENT_TASK_REJECTED_BY_APPROVER",
    "not_found": "APPROVAL_REJECT_INVALID_TOKEN",
    "task_mismatch": "APPROVAL_REJECT_INVALID_TOKEN",
    "already_used": "APPROVAL_ALREADY_USED",
    "expired": "LOCAL_AGENT_TASK_APPROVAL_EXPIRED",
    "forbidden": "APPROVAL_REJECT_FORBIDDEN",
    "rate_limited": "APPROVAL_RATE_LIMITED",
}


def _is_capture_screenshot(task) -> bool:
    return bool(task is not None and task.action == "capture_screenshot")


def _task_is_dry_run(task) -> bool:
    """params.options.dry_run 이 True 인 경우 dry-run 작업으로 본다.

    server 는 task.params 를 민감값 제거한 뒤 저장하므로 options.dry_run 은 보존된다.
    """
    try:
        options = task.params.get("options") if task is not None else None
        return bool(isinstance(options, dict) and options.get("dry_run"))
    except Exception:
        return False


def _capture_approval_note(task, agent_id: str, dry_run: bool) -> str:
    """CAPTURE_SCREENSHOT_APPROVAL_REQUESTED audit 용 note — reason/note 축약 포함.

    token 원문 / 파일명 / 전체 경로는 포함하지 않는다. reason/note 는 이미
    enqueue_task 단계에서 민감값 제거 후 저장되며, 본 함수는 추가 축약만 한다.
    """
    parts = [f"agent_id={agent_id}", f"dry_run={dry_run}"]
    try:
        params = task.params if task is not None else None
    except Exception:
        params = None
    if isinstance(params, dict):
        raw_reason = params.get("reason")
        if raw_reason:
            parts.append(f"reason={str(raw_reason)[:100]}")
        raw_note = params.get("note")
        if raw_note:
            parts.append(f"note={str(raw_note)[:100]}")
    return " ".join(parts)


# ── HTTP 라우트 ──────────────────────────────────────────────────────────

@local_agent_router.post("/register")
def register_local_agent(
    body: AgentRegisterRequest,
    user: dict = Depends(require_role("admin", "owner")),
):
    """새 로컬 에이전트 등록. agent_id + device_token 발급.

    device_token 은 응답에 1회만 노출되며 서버는 SHA-256 해시만 저장한다.
    """
    actor = user["actor"]
    role = user["role"]
    result = _reg.register_agent(
        host=body.host, os_name=body.os_name, version=body.version,
        requested_by=actor,
    )

    # 감사 로그: token 원문 / 해시 모두 기록 금지. token_hash prefix 만 식별자로.
    log_event(
        "LOCAL_AGENT_REGISTERED", result.agent.agent_id,
        actor=actor, role=role,
        note=f"host={result.agent.host} os={result.agent.os_name} "
             f"ver={result.agent.version}",
    )

    return {
        "agent_id": result.agent.agent_id,
        "device_token": result.device_token,  # 1회 노출, 클라이언트 책임 보관
        "host": result.agent.host,
        "os_name": result.agent.os_name,
        "version": result.agent.version,
        "registered_at": result.agent.registered_at,
    }


@local_agent_router.get("")
def list_local_agents(
    user: dict = Depends(require_role("admin", "owner", "viewer")),
):
    return {"agents": _reg.list_agents()}


@local_agent_router.post("/{agent_id}/tasks")
def submit_local_agent_task(
    agent_id: str,
    body: AgentTaskRequest,
    user: dict = Depends(require_role("admin", "owner")),
):
    """로컬 에이전트에게 작업 큐잉.

    - 미등록 agent_id → 404
    - 미등록 액션(delete_file/upload_file/modify_file/execute_shell …) → 400
    - high risk → 승인 토큰 발행 + status=waiting_approval
    """
    actor = user["actor"]
    role = user["role"]

    if _reg.get_agent(agent_id) is None:
        log_event(
            "LOCAL_AGENT_TASK_REJECTED", "local-agent",
            action_type=body.action, actor=actor, role=role,
            note=f"agent_id={agent_id} reason=AGENT_NOT_FOUND",
        )
        raise HTTPException(
            status_code=404,
            detail={"error": "AGENT_NOT_FOUND",
                    "message": f"미등록 에이전트: {agent_id}"},
        )

    try:
        task = _reg.enqueue_task(
            agent_id=agent_id,
            action=body.action,
            params=body.params,
            requested_by=actor,
        )
    except _reg.UnknownActionError as e:
        log_event(
            "LOCAL_AGENT_TASK_REJECTED", "local-agent",
            action_type=str(body.action), actor=actor, role=role,
            note=f"agent_id={agent_id} reason=UNKNOWN_ACTION",
        )
        raise HTTPException(
            status_code=400,
            detail={"error": "UNKNOWN_ACTION", "message": str(e)},
        )

    # high risk → 승인 토큰 발행 + waiting_approval 이벤트
    if task.risk_level == "high":
        token = issue_token_for_dev_reg(
            task_id=task.task_id,
            requested_by=actor,
            risk_level=task.risk_level,
            ttl_minutes=30,
        )
        _reg.attach_token(task.task_id, token.token_id)
        log_event(
            "LOCAL_AGENT_TASK_WAITING_APPROVAL", task.task_id,
            risk_level=task.risk_level,
            action_type=task.action,
            actor=actor, role=role,
            token_id=token.token_id,
            note=f"agent_id={agent_id}",
        )
        if _is_capture_screenshot(task):
            log_event(
                "CAPTURE_SCREENSHOT_APPROVAL_REQUESTED", task.task_id,
                risk_level=task.risk_level,
                action_type=task.action,
                actor=actor, role=role,
                token_id=token.token_id,
                note=_capture_approval_note(
                    task, agent_id, _task_is_dry_run(task),
                ),
            )
    else:
        log_event(
            "LOCAL_AGENT_TASK_QUEUED", task.task_id,
            risk_level=task.risk_level,
            action_type=task.action,
            actor=actor, role=role,
            note=f"agent_id={agent_id} status={task.status}",
        )
        if task.status == "completed":
            log_event(
                "LOCAL_AGENT_TASK_COMPLETED", task.task_id,
                risk_level=task.risk_level,
                action_type=task.action,
                actor="system",
                note=f"agent_id={agent_id}",
            )

    return _reg.get_task(agent_id, task.task_id).to_safe()


@local_agent_router.post("/{agent_id}/capture-screenshot")
def create_capture_screenshot_request(
    agent_id: str,
    body: CaptureScreenshotRequest | None = Body(default=None),
    user: dict = Depends(require_role("admin", "owner")),
):
    """운영자가 생성하는 capture_screenshot 요청 진입점.

    동작:
      - body 누락 / {} / reason 만 포함 → dry_run=True (기본값).
      - dry_run=False 는 body 에 명시적으로 false 를 담은 경우에만 적용되고,
        task 는 기존대로 waiting_approval 상태로 시작 + 승인 토큰 발행.
      - params.options.dry_run 에만 값을 저장하고, reason/note 는 별도 키로
        enqueue_task 의 민감값 제거 필터를 거친 뒤 보존된다.

    응답:
      task_id / agent_id / action / status / dry_run / approval_required 만 포함.
      승인 토큰 원문, device_token, 로컬 경로, 이미지 파일명 등은 절대 포함하지 않는다.
    """
    actor = user["actor"]
    role = user["role"]
    req = body if body is not None else CaptureScreenshotRequest()
    dry_run = bool(req.dry_run)

    if _reg.get_agent(agent_id) is None:
        log_event(
            "LOCAL_AGENT_TASK_REJECTED", "local-agent",
            action_type="capture_screenshot", actor=actor, role=role,
            note=f"agent_id={agent_id} reason=AGENT_NOT_FOUND",
        )
        raise HTTPException(
            status_code=404,
            detail={"error": "AGENT_NOT_FOUND",
                    "message": f"미등록 에이전트: {agent_id}"},
        )

    # reason/note 는 메모용 텍스트로만 보관. 길이를 제한해 로그 비대화를 방지.
    params: dict = {"options": {"dry_run": dry_run}}
    if req.reason:
        params["reason"] = req.reason[:200]
    if req.note:
        params["note"] = req.note[:500]

    task = _reg.enqueue_task(
        agent_id=agent_id,
        action="capture_screenshot",
        params=params,           # _strip_sensitive 는 enqueue_task 내부에서 적용
        requested_by=actor,
    )

    # 운영자 요청임을 명시하는 감사 이벤트 — approval token 원문/전체 경로/파일명
    # 어느 것도 기록하지 않는다.
    log_event(
        "CAPTURE_SCREENSHOT_REQUEST_CREATED", task.task_id,
        risk_level=task.risk_level,
        action_type=task.action,
        actor=actor, role=role,
        note=(f"agent_id={agent_id} dry_run={dry_run}"
              + (f" reason={req.reason[:100]}" if req.reason else "")),
    )

    # 기존 승인 흐름 재사용 — 토큰 발행 + 기존 감사 이벤트(두 종) 그대로.
    token = issue_token_for_dev_reg(
        task_id=task.task_id,
        requested_by=actor,
        risk_level=task.risk_level,
        ttl_minutes=30,
    )
    _reg.attach_token(task.task_id, token.token_id)
    log_event(
        "LOCAL_AGENT_TASK_WAITING_APPROVAL", task.task_id,
        risk_level=task.risk_level,
        action_type=task.action,
        actor=actor, role=role,
        token_id=token.token_id,
        note=f"agent_id={agent_id}",
    )
    log_event(
        "CAPTURE_SCREENSHOT_APPROVAL_REQUESTED", task.task_id,
        risk_level=task.risk_level,
        action_type=task.action,
        actor=actor, role=role,
        token_id=token.token_id,
        note=_capture_approval_note(task, agent_id, dry_run),
    )

    return {
        "task_id": task.task_id,
        "agent_id": agent_id,
        "action": "capture_screenshot",
        "status": "waiting_approval",
        "dry_run": dry_run,
        "approval_required": True,
    }


@local_agent_router.post("/{agent_id}/tasks/{task_id}/approve")
def approve_local_agent_task(
    agent_id: str,
    task_id: str,
    body: AgentTaskApprovalRequest,
    user: dict = Depends(require_role("admin", "owner")),
):
    """high risk 작업(capture_screenshot 등)을 승인하여 queued 로 전환.

    - ApprovalToken 검증 → approve_token()
    - waiting_approval → queued (registry.mark_approved)
    - 이미 결정된 작업은 현재 상태를 그대로 반환 (재승인 방지).
    """
    actor = user["actor"]
    role = user["role"]
    token_id = (body.token_id or "").strip()

    task = _reg.get_task(agent_id, task_id)
    if task is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "TASK_NOT_FOUND",
                    "message": f"미등록 작업: {agent_id}/{task_id}"},
        )

    if not token_id:
        raise HTTPException(
            status_code=400,
            detail={"error": "MISSING_TOKEN_ID",
                    "message": "token_id 가 필요합니다"},
        )

    if task.risk_level != "high":
        # 승인 자체가 의미 없는 작업 — 혼동 방지로 400
        raise HTTPException(
            status_code=400,
            detail={"error": "NOT_APPROVABLE",
                    "message": "high risk 가 아닌 작업은 승인 대상이 아닙니다"},
        )

    # 재실행 방지: 이미 결정된 작업은 새 승인을 받지 않는다.
    if task.status != "waiting_approval":
        log_event(
            "LOCAL_AGENT_TASK_APPROVAL_REPLAYED", task_id,
            actor=actor, role=role,
            note=f"agent_id={agent_id} current_status={task.status}",
        )
        return task.to_safe()

    token, status = approve_token(token_id, task_id, actor, role)
    log_event(
        _APPROVE_AUDIT_EVENT.get(status, "APPROVAL_DENIED"),
        task_id, token_id=token_id, actor=actor, role=role,
        decision=status, risk_level=token.risk_level,
        action_type=task.action,
        note=f"agent_id={agent_id}",
    )

    if status == "approved":
        updated = _reg.mark_approved(task_id, actor)
        if updated is None:
            # mark_approved 가 task 를 못 찾은 비정상 케이스
            raise HTTPException(status_code=404,
                                detail={"error": "TASK_NOT_FOUND"})
        if _is_capture_screenshot(updated):
            log_event(
                "CAPTURE_SCREENSHOT_APPROVED", task_id,
                risk_level=updated.risk_level,
                action_type=updated.action,
                actor=actor, role=role, token_id=token_id,
                note=f"agent_id={agent_id} dry_run={_task_is_dry_run(updated)}",
            )
        return updated.to_safe()

    if status == "expired":
        # 토큰 만료 → 작업도 rejected 로 종결
        _reg.mark_expired(task_id)
        if _is_capture_screenshot(task):
            log_event(
                "CAPTURE_SCREENSHOT_REJECTED", task_id,
                risk_level=task.risk_level,
                action_type=task.action,
                actor=actor, role=role, token_id=token_id,
                decision="expired",
                note=f"agent_id={agent_id}",
            )

    http_code = _APPROVE_STATUS_HTTP.get(status, 400)
    raise HTTPException(status_code=http_code,
                        detail={"error": status.upper(), "status": status})


@local_agent_router.post("/{agent_id}/tasks/{task_id}/reject")
def reject_local_agent_task(
    agent_id: str,
    task_id: str,
    body: AgentTaskApprovalRequest,
    user: dict = Depends(require_role("admin", "owner")),
):
    """high risk 작업을 거절. 작업은 rejected 상태로 종결되어 WS 로 전달되지 않는다."""
    actor = user["actor"]
    role = user["role"]
    token_id = (body.token_id or "").strip()
    reason = (body.reason or "").strip()

    task = _reg.get_task(agent_id, task_id)
    if task is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "TASK_NOT_FOUND",
                    "message": f"미등록 작업: {agent_id}/{task_id}"},
        )
    if not token_id:
        raise HTTPException(
            status_code=400,
            detail={"error": "MISSING_TOKEN_ID",
                    "message": "token_id 가 필요합니다"},
        )
    if task.risk_level != "high":
        raise HTTPException(
            status_code=400,
            detail={"error": "NOT_APPROVABLE",
                    "message": "high risk 가 아닌 작업은 거절 대상이 아닙니다"},
        )

    if task.status != "waiting_approval":
        log_event(
            "LOCAL_AGENT_TASK_APPROVAL_REPLAYED", task_id,
            actor=actor, role=role,
            note=f"agent_id={agent_id} current_status={task.status}",
        )
        return task.to_safe()

    token, status = reject_token(token_id, task_id, actor, role, reason=reason)
    log_event(
        _REJECT_AUDIT_EVENT.get(status, "APPROVAL_REJECTED"),
        task_id, token_id=token_id, actor=actor, role=role,
        decision=status, risk_level=token.risk_level,
        action_type=task.action,
        note=f"agent_id={agent_id}" + (f" reason={reason}" if reason else ""),
    )
    if status == "rejected":
        updated = _reg.mark_rejected(task_id, actor, reason=reason)
        if updated is None:
            raise HTTPException(status_code=404,
                                detail={"error": "TASK_NOT_FOUND"})
        if _is_capture_screenshot(updated):
            log_event(
                "CAPTURE_SCREENSHOT_REJECTED", task_id,
                risk_level=updated.risk_level,
                action_type=updated.action,
                actor=actor, role=role, token_id=token_id,
                decision="rejected",
                note=f"agent_id={agent_id}" + (f" reason={reason}" if reason else ""),
            )
        return updated.to_safe()

    if status == "expired":
        _reg.mark_expired(task_id)
        if _is_capture_screenshot(task):
            log_event(
                "CAPTURE_SCREENSHOT_REJECTED", task_id,
                risk_level=task.risk_level,
                action_type=task.action,
                actor=actor, role=role, token_id=token_id,
                decision="expired",
                note=f"agent_id={agent_id}",
            )

    http_code = _REJECT_STATUS_HTTP.get(status, 400)
    raise HTTPException(status_code=http_code,
                        detail={"error": status.upper(), "status": status})


@local_agent_router.get("/{agent_id}/tasks")
def list_local_agent_tasks(
    agent_id: str,
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(require_role("admin", "owner", "viewer")),
):
    if status is not None and status not in _reg.KNOWN_TASK_STATUSES:
        raise HTTPException(
            status_code=400,
            detail={"error": "UNKNOWN_STATUS",
                    "message": f"알 수 없는 status: {status}"},
        )
    tasks = _reg.list_tasks_for_agent(agent_id, status=status, limit=limit)
    return {
        "agent_id": agent_id,
        "total": len(tasks),
        "tasks": [t.to_list_safe() for t in tasks],
    }


@local_agent_router.get("/{agent_id}/tasks/{task_id}")
def get_local_agent_task(
    agent_id: str,
    task_id: str,
    user: dict = Depends(require_role("admin", "owner", "viewer")),
):
    task = _reg.get_task(agent_id, task_id)
    if task is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "TASK_NOT_FOUND",
                    "message": f"미등록 작업: {agent_id}/{task_id}"},
        )
    return task.to_safe()


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
    """해당 에이전트의 queued 작업을 모두 delivered 로 전환하며 push. 전송 개수 반환."""
    pending = _reg.list_pending_for_agent(agent_id)
    sent = 0
    for t in pending:
        updated = _reg.mark_delivered(agent_id, t.task_id)
        if updated is None or updated.status != "delivered":
            continue
        await ws.send_json({
            "type": "task",
            "task": updated.to_dispatch(),
        })
        log_event(
            "LOCAL_AGENT_TASK_DELIVERED", updated.task_id,
            risk_level=updated.risk_level,
            action_type=updated.action,
            actor="ws-dispatch",
            note=f"agent_id={agent_id}",
        )
        sent += 1
    return sent


async def _handle_result(ws: WebSocket, agent_id: str, msg: dict) -> None:
    task_id = _safe_str(msg.get("task_id"))
    if not task_id:
        await ws.send_json({
            "type": "error", "error": "MISSING_TASK_ID",
            "message": "result 메시지에 task_id 가 없습니다",
        })
        return

    existing = _reg.get_task(agent_id, task_id)
    if existing is None:
        # 다른 agent 의 task_id 를 주장하거나 존재하지 않는 작업 — 거절
        await ws.send_json({
            "type": "error", "error": "TASK_NOT_FOUND",
            "task_id": task_id,
        })
        log_event(
            "LOCAL_AGENT_TASK_REJECTED", task_id,
            actor="ws-dispatch",
            note=f"agent_id={agent_id} reason=UNKNOWN_TASK_IN_RESULT",
        )
        return

    success = bool(msg.get("success", False))
    summary = _safe_str(msg.get("summary"))[:500]
    error = _safe_str(msg.get("error"))[:500]
    error_code = _safe_str(msg.get("error_code"))[:80]

    updated = _reg.apply_result(
        agent_id=agent_id, task_id=task_id,
        success=success, summary=summary, error=error, error_code=error_code,
    )
    if updated is None:
        await ws.send_json({
            "type": "error", "error": "TASK_NOT_FOUND", "task_id": task_id,
        })
        return

    if updated.status == "completed":
        log_event(
            "LOCAL_AGENT_TASK_COMPLETED", task_id,
            risk_level=updated.risk_level,
            action_type=updated.action,
            actor="ws-agent",
            note=f"agent_id={agent_id}",
        )
        if _is_capture_screenshot(updated):
            dry = _task_is_dry_run(updated)
            # summary 도 fallback 으로 검사 — task.params 가 어떤 이유로 손실돼도
            # client 가 보낸 summary 접두("dry_run:true") 로 분기할 수 있다.
            if not dry and updated.result_summary.startswith("dry_run:true"):
                dry = True
            log_event(
                ("CAPTURE_SCREENSHOT_DRY_RUN_COMPLETED"
                 if dry else "CAPTURE_SCREENSHOT_COMPLETED"),
                task_id,
                risk_level=updated.risk_level,
                action_type=updated.action,
                actor="ws-agent",
                note=f"agent_id={agent_id}",
            )
    elif updated.status == "failed":
        log_event(
            "LOCAL_AGENT_TASK_FAILED", task_id,
            risk_level=updated.risk_level,
            action_type=updated.action,
            actor="ws-agent",
            decision=error_code or "failed",
            note=f"agent_id={agent_id}",
        )
        if _is_capture_screenshot(updated):
            log_event(
                "CAPTURE_SCREENSHOT_FAILED", task_id,
                risk_level=updated.risk_level,
                action_type=updated.action,
                actor="ws-agent",
                decision=error_code or "failed",
                note=f"agent_id={agent_id}",
            )

    await ws.send_json({
        "type": "result_ack",
        "task_id": task_id,
        "status": updated.status,
    })


async def _handle_running(ws: WebSocket, agent_id: str, msg: dict) -> None:
    task_id = _safe_str(msg.get("task_id"))
    if not task_id:
        await ws.send_json({
            "type": "error", "error": "MISSING_TASK_ID",
        })
        return
    updated = _reg.mark_running(agent_id, task_id)
    if updated is None:
        await ws.send_json({
            "type": "error", "error": "TASK_NOT_FOUND", "task_id": task_id,
        })
        return
    if updated.status == "running":
        log_event(
            "LOCAL_AGENT_TASK_RUNNING", task_id,
            risk_level=updated.risk_level,
            action_type=updated.action,
            actor="ws-agent",
            note=f"agent_id={agent_id}",
        )
    await ws.send_json({
        "type": "running_ack", "task_id": task_id, "status": updated.status,
    })


@local_agent_router.websocket("/ws")
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
                websocket.receive_json(), timeout=10.0,
            )
        except asyncio.TimeoutError:
            log_event(
                "LOCAL_AGENT_WS_AUTH_FAILED", "local-agent",
                actor="ws-dispatch", note="reason=AUTH_TIMEOUT",
            )
            await websocket.close(code=4401)
            return
        except WebSocketDisconnect:
            return

        if not isinstance(auth_msg, dict) or auth_msg.get("type") != "auth":
            log_event(
                "LOCAL_AGENT_WS_AUTH_FAILED", "local-agent",
                actor="ws-dispatch", note="reason=AUTH_MESSAGE_REQUIRED",
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
            "LOCAL_AGENT_WS_CONNECTED", agent_id,
            actor="ws-dispatch",
            note=f"host={authed.host} ver={authed.version}",
        )
        await websocket.send_json({
            "type": "auth_ok",
            "agent_id": agent_id,
        })

        # 2) 초기 큐 드레인
        await _push_queued(websocket, agent_id)

        # 3) 메시지 루프
        while True:
            try:
                msg = await asyncio.wait_for(
                    websocket.receive_json(), timeout=_WS_RECV_TIMEOUT_SEC,
                )
            except asyncio.TimeoutError:
                # 유휴 — 신규 큐 작업 push + keepalive
                _reg.set_agent_last_seen(agent_id)
                await _push_queued(websocket, agent_id)
                expired = _reg.expire_stale_tasks()
                for t in expired:
                    log_event(
                        "LOCAL_AGENT_TASK_TIMEOUT", t.task_id,
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
                except Exception:
                    raise WebSocketDisconnect()
                continue

            if not isinstance(msg, dict):
                await websocket.send_json({
                    "type": "error", "error": "INVALID_MESSAGE",
                })
                continue

            # auth 이후 메시지의 agent_id 는 반드시 일치해야 한다.
            msg_agent_id = _safe_str(msg.get("agent_id"))
            if msg_agent_id and msg_agent_id != agent_id:
                await websocket.send_json({
                    "type": "error", "error": "AGENT_ID_MISMATCH",
                })
                continue

            mtype = _safe_str(msg.get("type"))
            if mtype == "heartbeat":
                _reg.set_agent_last_seen(agent_id)
                await websocket.send_json({"type": "heartbeat_ack"})
                await _push_queued(websocket, agent_id)
            elif mtype == "pull":
                await _push_queued(websocket, agent_id)
            elif mtype == "running":
                _reg.set_agent_last_seen(agent_id)
                await _handle_running(websocket, agent_id, msg)
            elif mtype == "result":
                _reg.set_agent_last_seen(agent_id)
                await _handle_result(websocket, agent_id, msg)
                await _push_queued(websocket, agent_id)
            elif mtype == "auth":
                # 재인증 요청은 거절 (이미 인증된 세션)
                await websocket.send_json({
                    "type": "error", "error": "ALREADY_AUTHENTICATED",
                })
            else:
                await websocket.send_json({
                    "type": "error", "error": "UNKNOWN_MESSAGE_TYPE",
                    "received": mtype[:40],
                })
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.exception("agent websocket 예외: %s", e)
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        if agent_id:
            _reg.set_agent_disconnected(agent_id)
            failed_on_disconnect = _reg.fail_active_tasks_for_agent(agent_id)
            for t in failed_on_disconnect:
                log_event(
                    "LOCAL_AGENT_TASK_FAILED", t.task_id,
                    risk_level=t.risk_level,
                    action_type=t.action,
                    actor="ws-disconnect",
                    decision="failed",
                    note=(
                        f"agent_id={agent_id}"
                        f" failure_reason={t.failure_reason}"
                        f" status=failed"
                    ),
                )
            log_event(
                "LOCAL_AGENT_WS_DISCONNECTED", agent_id,
                actor="ws-dispatch",
            )


__all__ = ["local_agent_router"]

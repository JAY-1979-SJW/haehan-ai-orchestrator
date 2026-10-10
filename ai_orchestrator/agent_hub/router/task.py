"""local_agent 작업(task) 라우트군 — 조회(list/get) leaf 서브라우터.

컴포지션 루트(local_agent_router)가 include_router 로 관리.
(cancel/approve/reject 등 작업 처리 라우트는 후속 슬라이스에서 합류)
sibling leaf 는 직접 import 하지 않는다. [docs/module_separation_standard.md]
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import audit_builders as _audit
from ..policy import audit_event_policy as _policy
from ..registry import facade as _reg
from . import guards as _guards  # 공유 leaf
from ...audit.audit_logger import log_event
from tools.gates.approval import approve_token, issue_token_for_dev_reg, reject_token
from tools.gates.auth import require_role
from .schemas import (
    AgentTaskApprovalRequest,
    AgentTaskRequest,
    CancelTaskRequest,
)
from .validation import _capture_approval_note  # 공유 leaf

_CANCEL_REASON_MAX_LEN = 200

task_router = APIRouter()


@task_router.get("/{agent_id}/tasks")
def list_local_agent_tasks(
    agent_id: str,
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(require_role("admin", "owner", "viewer")),
):
    if status is not None and status not in _reg.KNOWN_TASK_STATUSES:
        raise HTTPException(
            status_code=400,
            detail={"error": "UNKNOWN_STATUS", "message": f"알 수 없는 status: {status}"},
        )
    tasks = _reg.list_tasks_for_agent(agent_id, status=status, limit=limit)
    return {
        "agent_id": agent_id,
        "total": len(tasks),
        "tasks": [t.to_list_safe() for t in tasks],
    }


@task_router.get("/{agent_id}/tasks/{task_id}")
def get_local_agent_task(
    agent_id: str,
    task_id: str,
    user: dict = Depends(require_role("admin", "owner", "viewer")),
):
    task = _reg.get_task(agent_id, task_id)
    if task is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "TASK_NOT_FOUND", "message": f"미등록 작업: {agent_id}/{task_id}"},
        )
    return task.to_safe()


@task_router.post("/{agent_id}/tasks/{task_id}/cancel")
def cancel_local_agent_task(
    agent_id: str,
    task_id: str,
    body: CancelTaskRequest,
    user: dict = Depends(require_role("admin", "owner")),
):
    """task 취소.

    - queued / waiting_approval → 즉시 cancelled
    - delivered / running → cancel_requested (agent에 취소 신호 필요)
    - completed / failed / rejected / cancelled / cancel_requested → 409
    - reason > 200자 → 400
    """
    actor = user["actor"]
    role = user["role"]
    reason = body.reason or ""

    if len(reason) > _CANCEL_REASON_MAX_LEN:
        raise HTTPException(
            status_code=400,
            detail={"error": "REASON_TOO_LONG", "message": f"reason 은 최대 {_CANCEL_REASON_MAX_LEN}자입니다"},
        )

    # 취소 전 현재 상태 보존 (audit용)
    existing = _reg.get_task(agent_id, task_id)
    if existing is None:
        log_event(
            "LOCAL_AGENT_TASK_CANCEL_REQUESTED",
            task_id,
            actor=actor,
            role=role,
            note=f"agent_id={agent_id} reason=TASK_NOT_FOUND",
        )
        raise HTTPException(
            status_code=404,
            detail={"error": "TASK_NOT_FOUND", "message": f"미등록 작업: {agent_id}/{task_id}"},
        )
    previous_status = existing.status

    try:
        task, cancel_action = _reg.cancel_task(
            agent_id,
            task_id,
            actor=actor,
            reason=reason,
        )
    except _reg.CancelNotAllowedError as e:
        raise HTTPException(
            status_code=409,
            detail={"error": "CANCEL_NOT_ALLOWED", "message": str(e)},
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail={"error": "TASK_NOT_FOUND", "message": str(e)},
        ) from e

    audit_event = "LOCAL_AGENT_TASK_CANCELLED" if cancel_action == "cancelled" else "LOCAL_AGENT_TASK_CANCEL_REQUESTED"
    log_event(
        audit_event,
        task_id,
        risk_level=task.risk_level,
        action_type=task.action,
        actor=actor,
        role=role,
        note=(
            f"agent_id={agent_id}"
            f" previous_status={previous_status}"
            f" next_status={task.status}"
            f" requested_by={actor}"
            f" reason_len={len(reason)}"
        ),
    )

    return {
        "task": task.to_safe(),
        "cancel_action": cancel_action,
    }


@task_router.post("/{agent_id}/tasks/{task_id}/approve")
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
            detail={"error": "TASK_NOT_FOUND", "message": f"미등록 작업: {agent_id}/{task_id}"},
        )

    if not token_id:
        raise HTTPException(
            status_code=400,
            detail={"error": "MISSING_TOKEN_ID", "message": "token_id 가 필요합니다"},
        )

    if task.risk_level != "high":
        # 승인 자체가 의미 없는 작업 — 혼동 방지로 400
        raise HTTPException(
            status_code=400,
            detail={"error": "NOT_APPROVABLE", "message": "high risk 가 아닌 작업은 승인 대상이 아닙니다"},
        )

    # 재실행 방지: 이미 결정된 작업은 새 승인을 받지 않는다.
    if task.status != "waiting_approval":
        log_event(
            "LOCAL_AGENT_TASK_APPROVAL_REPLAYED",
            task_id,
            actor=actor,
            role=role,
            note=f"agent_id={agent_id} current_status={task.status}",
        )
        return task.to_safe()

    token, status = approve_token(token_id, task_id, actor, role)
    log_event(
        _policy.APPROVE_AUDIT_EVENT.get(status, "APPROVAL_DENIED"),
        task_id,
        actor=actor,
        role=role,
        decision=status,
        risk_level=token.risk_level,
        action_type=task.action,
        note=_audit.build_approval_note(agent_id, token.public_id),
    )

    if status == "approved":
        updated = _reg.mark_approved(task_id, actor)
        if updated is None:
            # mark_approved 가 task 를 못 찾은 비정상 케이스
            raise HTTPException(status_code=404, detail={"error": "TASK_NOT_FOUND"})
        if _guards.is_capture_screenshot_task(updated):
            log_event(
                "CAPTURE_SCREENSHOT_APPROVED",
                task_id,
                risk_level=updated.risk_level,
                action_type=updated.action,
                actor=actor,
                role=role,
                note=_audit.build_screenshot_approval_note(
                    agent_id,
                    _guards.task_is_dry_run(updated),
                    approval_public_id=token.public_id,
                ),
            )
        return updated.to_safe()

    if status == "expired":
        # 토큰 만료 → 작업도 rejected 로 종결
        _reg.mark_expired(task_id)
        if _guards.is_capture_screenshot_task(task):
            log_event(
                "CAPTURE_SCREENSHOT_REJECTED",
                task_id,
                risk_level=task.risk_level,
                action_type=task.action,
                actor=actor,
                role=role,
                decision="expired",
                note=f"agent_id={agent_id} approval_public_id={token.public_id}"
                if token.public_id
                else f"agent_id={agent_id}",
            )

    http_code = _policy.APPROVE_STATUS_HTTP.get(status, 400)
    raise HTTPException(status_code=http_code, detail={"error": status.upper(), "status": status})


@task_router.post("/{agent_id}/tasks/{task_id}/reject")
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
            detail={"error": "TASK_NOT_FOUND", "message": f"미등록 작업: {agent_id}/{task_id}"},
        )
    if not token_id:
        raise HTTPException(
            status_code=400,
            detail={"error": "MISSING_TOKEN_ID", "message": "token_id 가 필요합니다"},
        )
    if task.risk_level != "high":
        raise HTTPException(
            status_code=400,
            detail={"error": "NOT_APPROVABLE", "message": "high risk 가 아닌 작업은 거절 대상이 아닙니다"},
        )

    if task.status != "waiting_approval":
        log_event(
            "LOCAL_AGENT_TASK_APPROVAL_REPLAYED",
            task_id,
            actor=actor,
            role=role,
            note=f"agent_id={agent_id} current_status={task.status}",
        )
        return task.to_safe()

    token, status = reject_token(token_id, task_id, actor, role, reason=reason)
    log_event(
        _policy.REJECT_AUDIT_EVENT.get(status, "APPROVAL_REJECTED"),
        task_id,
        actor=actor,
        role=role,
        decision=status,
        risk_level=token.risk_level,
        action_type=task.action,
        note=f"agent_id={agent_id}"
        + (f" reason={reason}" if reason else "")
        + (f" approval_public_id={token.public_id}" if token.public_id else ""),
    )
    if status == "rejected":
        updated = _reg.mark_rejected(task_id, actor, reason=reason)
        if updated is None:
            raise HTTPException(status_code=404, detail={"error": "TASK_NOT_FOUND"})
        if _guards.is_capture_screenshot_task(updated):
            log_event(
                "CAPTURE_SCREENSHOT_REJECTED",
                task_id,
                risk_level=updated.risk_level,
                action_type=updated.action,
                actor=actor,
                role=role,
                decision="rejected",
                note=f"agent_id={agent_id}"
                + (f" reason={reason}" if reason else "")
                + (f" approval_public_id={token.public_id}" if token.public_id else ""),
            )
        return updated.to_safe()

    if status == "expired":
        _reg.mark_expired(task_id)
        if _guards.is_capture_screenshot_task(task):
            log_event(
                "CAPTURE_SCREENSHOT_REJECTED",
                task_id,
                risk_level=task.risk_level,
                action_type=task.action,
                actor=actor,
                role=role,
                decision="expired",
                note=f"agent_id={agent_id} approval_public_id={token.public_id}"
                if token.public_id
                else f"agent_id={agent_id}",
            )

    http_code = _policy.REJECT_STATUS_HTTP.get(status, 400)
    raise HTTPException(status_code=http_code, detail={"error": status.upper(), "status": status})


@task_router.post("/{agent_id}/tasks")
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
            "LOCAL_AGENT_TASK_REJECTED",
            "local-agent",
            action_type=body.action,
            actor=actor,
            role=role,
            note=f"agent_id={agent_id} reason=AGENT_NOT_FOUND",
        )
        raise HTTPException(
            status_code=404,
            detail={"error": "AGENT_NOT_FOUND", "message": f"미등록 에이전트: {agent_id}"},
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
            "LOCAL_AGENT_TASK_REJECTED",
            "local-agent",
            action_type=str(body.action),
            actor=actor,
            role=role,
            note=f"agent_id={agent_id} reason=UNKNOWN_ACTION",
        )
        raise HTTPException(
            status_code=400,
            detail={"error": "UNKNOWN_ACTION", "message": str(e)},
        ) from e

    # high risk → 승인 토큰 발행 + waiting_approval 이벤트
    if task.risk_level == "high":
        token = issue_token_for_dev_reg(
            task_id=task.task_id,
            requested_by=actor,
            risk_level=task.risk_level,
            ttl_minutes=30,
        )
        _reg.attach_token(task.task_id, token.token_id, token.public_id)
        log_event(
            "LOCAL_AGENT_TASK_WAITING_APPROVAL",
            task.task_id,
            risk_level=task.risk_level,
            action_type=task.action,
            actor=actor,
            role=role,
            token_id=token.token_id,
            note=f"agent_id={agent_id}",
        )
        if _guards.is_capture_screenshot_task(task):
            log_event(
                "CAPTURE_SCREENSHOT_APPROVAL_REQUESTED",
                task.task_id,
                risk_level=task.risk_level,
                action_type=task.action,
                actor=actor,
                role=role,
                token_id=token.token_id,
                note=_capture_approval_note(
                    task,
                    agent_id,
                    _guards.task_is_dry_run(task),
                ),
            )
    else:
        log_event(
            "LOCAL_AGENT_TASK_QUEUED",
            task.task_id,
            risk_level=task.risk_level,
            action_type=task.action,
            actor=actor,
            role=role,
            note=f"agent_id={agent_id} status={task.status}",
        )
        if task.status == "completed":
            log_event(
                "LOCAL_AGENT_TASK_COMPLETED",
                task.task_id,
                risk_level=task.risk_level,
                action_type=task.action,
                actor="system",
                note=f"agent_id={agent_id}",
            )

    saved = _reg.get_task(agent_id, task.task_id)
    if saved is None:  # 방금 만든 작업이 사라진 경우(이전에는 AttributeError 로 500) — 명시적으로 500
        raise HTTPException(status_code=500, detail="저장된 작업을 찾을 수 없습니다")
    return saved.to_safe()

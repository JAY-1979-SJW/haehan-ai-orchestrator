"""Task lifecycle transitions: delivered, running, result application, timeouts."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .local_agent_models import LocalAgentTask
from .local_agent_redaction import _strip_result_data
from .local_agent_registry_common import (
    _lock, _tasks, _now_iso, _ensure_task_transition,
    ACTIVE_TASK_STATUSES, DELIVERED_TIMEOUT_SECONDS, RUNNING_TIMEOUT_SECONDS,
    InvalidTaskTransitionError,
)
from .local_agent_registry_sanitize import _build_observe_summary, _build_audit_summary


# ── 실패 처리 internal helper ───────────────────────────────────────────

def _mark_task_failed(
    task: LocalAgentTask,
    *,
    failure_reason: str,
    error_summary: str = "",
    now: str,
    timed_out: bool = False,
) -> None:
    """task 를 failed 로 전환하는 내부 helper.

    _ensure_task_transition 으로 허용 여부를 검증한 후 필드를 일괄 세팅한다.
    호출자는 이미 _lock 을 보유한 상태여야 한다.
    """
    _ensure_task_transition(task, "failed")
    task.status = "failed"
    task.failure_reason = failure_reason
    if error_summary:
        task.error_summary = error_summary[:500]
    task.completed_at = now
    task.updated_at = now
    if timed_out:
        task.timed_out_at = now


# ── Stage 2 전달/결과 ───────────────────────────────────────────────────

def mark_delivered(agent_id: str, task_id: str) -> Optional[LocalAgentTask]:
    """queued → delivered. 다른 상태에서는 변경 없음."""
    with _lock:
        t = _tasks.get(task_id)
        if t is None or t.agent_id != agent_id:
            return None
        if t.status != "queued":
            return t
        _ensure_task_transition(t, "delivered")
        now = _now_iso()
        t.status = "delivered"
        t.delivered_at = now
        t.updated_at = now
        return t


def mark_running(agent_id: str, task_id: str) -> Optional[LocalAgentTask]:
    """delivered → running."""
    with _lock:
        t = _tasks.get(task_id)
        if t is None or t.agent_id != agent_id:
            return None
        if t.status != "delivered":
            return t
        _ensure_task_transition(t, "running")
        now = _now_iso()
        t.status = "running"
        if not t.started_at:
            t.started_at = now
        t.updated_at = now
        return t


def apply_result(
    *,
    agent_id: str,
    task_id: str,
    success: bool,
    summary: str = "",
    error: str = "",
    error_code: str = "",
    observe_summary: Optional[dict] = None,
    audit_summary: Optional[dict] = None,
    data: Optional[dict] = None,
) -> Optional[LocalAgentTask]:
    """에이전트가 보고한 결과 반영. running/delivered/cancel_requested 에서 동작.

    - success=True  → running/cancel_requested → completed
      (delivered → completed 는 허용되지 않으므로 실패 보고만 허용)
    - success=False → failed
    - cancel_requested 상태에서 result 수신 시 cancel 필드는 보존한다 (agent result 우선).
    """
    with _lock:
        t = _tasks.get(task_id)
        if t is None or t.agent_id != agent_id:
            return None
        if t.status not in ("running", "delivered", "cancel_requested"):
            return t
        next_status = "completed" if success else "failed"
        _ensure_task_transition(t, next_status)
        now = _now_iso()
        if success:
            t.status = "completed"
            t.result_summary = (summary or "")[:500]
            t.error_summary = ""
            if data is not None:
                t.result_data = _strip_result_data(data)
            if observe_summary is not None:
                t.observe_summary = _build_observe_summary(observe_summary)
            if audit_summary is not None:
                t.audit_summary = _build_audit_summary(audit_summary)
        else:
            t.status = "failed"
            msg = (error_code + ": " + (error or summary or "")).strip(": ")
            t.error_summary = msg[:500]
            t.result_summary = (summary or "")[:500]
            if not t.failure_reason:
                t.failure_reason = "agent_error"
            if audit_summary is not None:
                t.audit_summary = _build_audit_summary(audit_summary)
        t.completed_at = now
        t.updated_at = now
        return t


# ── timeout 만료 ─────────────────────────────────────────────────────────

def expire_stale_tasks(
    now: Optional[datetime] = None,
) -> list[LocalAgentTask]:
    """delivered/running/cancel_requested 상태 중 timeout 초과 task 를 failed 로 전환.

    - delivered 상태: delivered_at 기준 DELIVERED_TIMEOUT_SECONDS 초과
    - running 상태: started_at 기준 RUNNING_TIMEOUT_SECONDS 초과
    - cancel_requested 상태: cancel_requested_at 기준 RUNNING_TIMEOUT_SECONDS 초과
    - 만료 처리된 task 목록을 반환한다.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    expired: list[LocalAgentTask] = []
    with _lock:
        for task in list(_tasks.values()):
            try:
                if task.status == "delivered" and task.delivered_at:
                    delivered_at = datetime.fromisoformat(task.delivered_at)
                    if (now - delivered_at).total_seconds() > DELIVERED_TIMEOUT_SECONDS:
                        _mark_task_failed(
                            task,
                            failure_reason="delivered_timeout",
                            error_summary="delivered_timeout: agent did not start within time limit",
                            now=now_iso,
                            timed_out=True,
                        )
                        expired.append(task)
                elif task.status == "running" and task.started_at:
                    started_at = datetime.fromisoformat(task.started_at)
                    if (now - started_at).total_seconds() > RUNNING_TIMEOUT_SECONDS:
                        _mark_task_failed(
                            task,
                            failure_reason="running_timeout",
                            error_summary="running_timeout: agent did not report result within time limit",
                            now=now_iso,
                            timed_out=True,
                        )
                        expired.append(task)
                elif task.status == "cancel_requested" and task.cancel_requested_at:
                    requested_at = datetime.fromisoformat(task.cancel_requested_at)
                    if (now - requested_at).total_seconds() > RUNNING_TIMEOUT_SECONDS:
                        _mark_task_failed(
                            task,
                            failure_reason="cancel_timeout",
                            error_summary="cancel_timeout: agent did not acknowledge cancel within time limit",
                            now=now_iso,
                            timed_out=True,
                        )
                        expired.append(task)
            except (ValueError, TypeError):
                continue
    return expired


def fail_active_tasks_for_agent(
    agent_id: str,
    reason: str = "websocket_disconnected",
    now: Optional[datetime] = None,
) -> list[LocalAgentTask]:
    """agent WebSocket 연결 종료 시 ACTIVE_TASK_STATUSES 작업을 failed 처리.

    - ACTIVE_TASK_STATUSES = delivered / running / cancel_requested
    - queued / completed / failed / waiting_approval 등은 변경하지 않는다.
    - 처리된 task 목록을 반환한다.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    affected: list[LocalAgentTask] = []
    with _lock:
        for task in list(_tasks.values()):
            if task.agent_id != agent_id:
                continue
            if task.status not in ACTIVE_TASK_STATUSES:
                continue
            try:
                _mark_task_failed(
                    task,
                    failure_reason=reason,
                    now=now_iso,
                    timed_out=False,
                )
                affected.append(task)
            except InvalidTaskTransitionError:
                continue
    return affected


__all__ = [
    "_mark_task_failed",
    "mark_delivered", "mark_running", "apply_result",
    "expire_stale_tasks", "fail_active_tasks_for_agent",
]

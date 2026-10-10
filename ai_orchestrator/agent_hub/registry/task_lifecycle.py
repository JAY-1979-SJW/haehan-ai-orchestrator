"""Task lifecycle transitions: delivered, running, result application, timeouts."""

from __future__ import annotations

from datetime import UTC, datetime

from ..models import LocalAgentTask
from ..redaction import _strip_result_data
from .common import (
    ACTIVE_TASK_STATUSES,
    DELIVERED_TIMEOUT_SECONDS,
    MAX_WS_DISCONNECT_RETRIES,
    RUNNING_TIMEOUT_SECONDS,
    InvalidTaskTransitionError,
    _ensure_task_transition,
    _lock,
    _now_iso,
    _tasks,
)
from .sanitize import _build_audit_summary, _build_observe_summary

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


def mark_delivered(agent_id: str, task_id: str) -> LocalAgentTask | None:
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


def mark_running(agent_id: str, task_id: str) -> LocalAgentTask | None:
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


def apply_result(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    *,
    agent_id: str,
    task_id: str,
    success: bool,
    summary: str = "",
    error: str = "",
    error_code: str = "",
    observe_summary: dict | None = None,
    audit_summary: dict | None = None,
    data: dict | None = None,
) -> LocalAgentTask | None:
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
    now: datetime | None = None,
) -> list[LocalAgentTask]:
    """delivered/running/cancel_requested 상태 중 timeout 초과 task 를 failed 로 전환.

    - delivered 상태: delivered_at 기준 DELIVERED_TIMEOUT_SECONDS 초과
    - running 상태: started_at 기준 RUNNING_TIMEOUT_SECONDS 초과
    - cancel_requested 상태: cancel_requested_at 기준 RUNNING_TIMEOUT_SECONDS 초과
    - 만료 처리된 task 목록을 반환한다.
    """
    if now is None:
        now = datetime.now(UTC)
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
    now: datetime | None = None,
) -> tuple[list[LocalAgentTask], list[LocalAgentTask]]:
    """agent WebSocket 연결 종료 시 ACTIVE_TASK_STATUSES 작업을 처리.

    - ACTIVE_TASK_STATUSES = delivered / running / cancel_requested
    - queued / completed / failed / waiting_approval 등은 변경하지 않는다.
    - delivered 는 MAX_WS_DISCONNECT_RETRIES 미만이면 **재큐잉**(queued로 되돌려
      retry_count 증가)한다 — 에이전트가 재연결하면 기존 "queued → delivered on connect"
      로직(_push_queued)이 그대로 다시 전달한다. 사람이 겪은 실제 증상(2026-09-30: 짧은
      재연결 몇 초 사이 들어온 요청이 그 자리에서 즉시 실패로 끝나던 것)을 고치기 위함.
    - running 은 이미 실행이 시작됐을 수 있어(비멱등 작업 중복 실행 위험) 재큐잉하지 않고
      기존처럼 failed 처리한다.
    - cancel_requested 는 재큐잉하지 않고 기존처럼 즉시 failed — 사용자가 명시적으로
      취소를 요청한 작업을 연결 문제를 핑계로 되살리면 사용자 의도를 거스르게 된다.
    - retry_count 가 MAX_WS_DISCONNECT_RETRIES 이상이면(같은 작업이 매번 agent를 죽이는
      등) 더 재큐잉하지 않고 failed 로 종결 — 무한 재시도 방지.
    - (failed 목록, requeued 목록) 튜플을 반환한다.
    """
    if now is None:
        now = datetime.now(UTC)
    now_iso = now.isoformat()

    failed: list[LocalAgentTask] = []
    requeued: list[LocalAgentTask] = []
    with _lock:
        for task in list(_tasks.values()):
            if task.agent_id != agent_id:
                continue
            if task.status not in ACTIVE_TASK_STATUSES:
                continue

            # running 은 에이전트가 이미 실행을 시작했을 수 있어 재큐잉하면 중복 실행 위험 — 제외.
            can_retry = task.status == "delivered" and task.retry_count < MAX_WS_DISCONNECT_RETRIES
            try:
                if can_retry:
                    _ensure_task_transition(task, "queued")
                    task.status = "queued"
                    task.retry_count += 1
                    task.delivered_at = ""
                    task.started_at = ""
                    task.updated_at = now_iso
                    requeued.append(task)
                else:
                    _mark_task_failed(
                        task,
                        failure_reason=reason,
                        now=now_iso,
                        timed_out=False,
                    )
                    failed.append(task)
            except InvalidTaskTransitionError:
                continue
    return failed, requeued


__all__ = [
    "_mark_task_failed",
    "apply_result",
    "expire_stale_tasks",
    "fail_active_tasks_for_agent",
    "mark_delivered",
    "mark_running",
]

"""Task queue: enqueue, lookup, approval flow, and list helpers."""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Callable

from ..models import LocalAgentTask
from ..redaction import _strip_sensitive
from .common import (
    _SERVER_AUTO_COMPLETE,
    ACTION_RISK,
    ALLOWED_APPS,
    UnknownActionError,
    _lock,
    _now_iso,
    _tasks,
)

# 큐에 작업(queued)이 들어간 직후 호출되는 리스너(agent_id 전달). WS 계층이 연결된 에이전트를
# 즉시 깨우는 데 쓴다 — 레지스트리는 WS 계층을 import 하지 않는다(의존 방향 유지).
_enqueue_listeners: list[Callable[[str], None]] = []


def add_enqueue_listener(listener: Callable[[str], None]) -> None:
    if listener not in _enqueue_listeners:
        _enqueue_listeners.append(listener)


def _notify_enqueued(agent_id: str) -> None:
    for listener in list(_enqueue_listeners):
        # 리스너 실패가 작업 등록을 막으면 안 된다 — 늦어도 heartbeat 가 전달한다(폴백)
        with contextlib.suppress(Exception):
            listener(agent_id)


def enqueue_task(
    *,
    agent_id: str,
    action: str,
    params: dict | None,
    requested_by: str,
) -> LocalAgentTask:
    """작업을 큐에 등록.

    - 미등록 action → UnknownActionError (라우터에서 400 + UNKNOWN_ACTION)
    - low risk + 서버 즉시 완료 가능 액션 → status=completed
    - low risk + PC 의존 액션 (open_url) → status=queued
    - medium → status=queued
    - high → status=waiting_approval + 토큰 발행 (호출자 책임)
    """
    action = (action or "").strip().lower()
    if action not in ACTION_RISK:
        raise UnknownActionError(f"미등록 액션: {action or '-'}")

    risk_level = ACTION_RISK[action]
    safe_params = _strip_sensitive(params or {})

    if risk_level == "high":
        status = "waiting_approval"
    elif action in _SERVER_AUTO_COMPLETE:
        status = "completed"
    else:
        status = "queued"

    now = _now_iso()
    task = LocalAgentTask(
        task_id=f"lat-{uuid.uuid4().hex[:12]}",
        agent_id=agent_id,
        action=action,
        params=safe_params,
        risk_level=risk_level,
        status=status,
        requested_by=requested_by,
        created_at=now,
        updated_at=now,
        result_summary=_initial_result_summary(action, safe_params),
        completed_at=now if status == "completed" else "",
    )
    with _lock:
        _tasks[task.task_id] = task
    if status == "queued":
        _notify_enqueued(agent_id)
    return task


def attach_token(task_id: str, token_id: str, public_id: str = "") -> None:
    """high risk 작업에 승인 토큰 ID + public id 연결 (라우터에서 호출).

    token_id 는 서버 승인 검증용 secret-like 값으로만 보관하며, public_id 는
    UI/result_data/audit 표시용 외부 식별자로 분리 저장한다.
    """
    with _lock:
        t = _tasks.get(task_id)
        if t is None:
            return
        t.token_id = token_id
        if public_id:
            t.approval_public_id = public_id
        t.updated_at = _now_iso()


def get_task(agent_id: str, task_id: str) -> LocalAgentTask | None:
    t = _tasks.get(task_id)
    if t is None or t.agent_id != agent_id:
        return None
    return t


def find_task_by_id(task_id: str) -> LocalAgentTask | None:
    """agent_id 불필요한 내부 조회 (승인 훅 등). agent 범위 권한 검사는 호출자가 수행."""
    return _tasks.get(task_id)


def find_task_by_token_id(token_id: str) -> LocalAgentTask | None:
    """승인 토큰 → 대응 local agent task 역인덱스 (선형 탐색 — 요청 주기 낮음)."""
    if not token_id:
        return None
    with _lock:
        for t in _tasks.values():
            if t.token_id and t.token_id == token_id:
                return t
    return None


def mark_approved(task_id: str, actor: str) -> LocalAgentTask | None:
    """waiting_approval → queued 로 전환. 이미 결정된 작업은 그대로 반환 (idempotent).

    - high risk 아닌 작업이 실수로 전달되면 no-op (상태 변경 없음).
    - approved_at 은 최초 승인 시각 1회만 기록 (재실행 방지 근거).
    """
    with _lock:
        t = _tasks.get(task_id)
        if t is None:
            return None
        if t.status != "waiting_approval":
            return t
        if t.risk_level != "high":
            return t
        now = _now_iso()
        t.status = "queued"
        t.approved_at = now
        t.approved_by = (actor or "")[:80]
        t.updated_at = now
        return t


def mark_rejected(
    task_id: str,
    actor: str,
    reason: str = "",
) -> LocalAgentTask | None:
    """waiting_approval → rejected 로 전환. idempotent."""
    with _lock:
        t = _tasks.get(task_id)
        if t is None:
            return None
        if t.status != "waiting_approval":
            return t
        now = _now_iso()
        t.status = "rejected"
        t.rejected_at = now
        t.approved_by = (actor or "")[:80]
        t.reject_reason = (reason or "")[:200]
        t.completed_at = now
        t.updated_at = now
        return t


def mark_expired(task_id: str) -> LocalAgentTask | None:
    """승인 토큰 만료 등으로 작업을 rejected 상태로 종결."""
    with _lock:
        t = _tasks.get(task_id)
        if t is None:
            return None
        if t.status != "waiting_approval":
            return t
        now = _now_iso()
        t.status = "rejected"
        t.rejected_at = now
        t.reject_reason = "token_expired"
        t.completed_at = now
        t.updated_at = now
        return t


def list_tasks_for_agent(
    agent_id: str,
    status: str | None = None,
    limit: int = 50,
) -> list[LocalAgentTask]:
    """agent_id 기준 task 목록 반환.

    - 없는 agent_id → 빈 list
    - status 지정 시 KNOWN_TASK_STATUSES 검증; 미지정 시 전체
    - created_at 내림차순 (최신 우선)
    - limit 개수만 반환
    """
    with _lock:
        tasks = [t for t in _tasks.values() if t.agent_id == agent_id]
    if status is not None:
        tasks = [t for t in tasks if t.status == status]
    tasks.sort(key=lambda t: t.created_at, reverse=True)
    return tasks[:limit]


def list_pending_for_agent(agent_id: str) -> list[LocalAgentTask]:
    """해당 에이전트의 status=queued 작업 (오래된 것부터)."""
    with _lock:
        out = [t for t in _tasks.values() if t.agent_id == agent_id and t.status == "queued"]
    out.sort(key=lambda t: t.created_at)
    return out


def _initial_result_summary(action: str, safe_params: dict) -> str:
    """서버 즉시 완료 액션의 안전 요약 텍스트 (민감 원문 금지)."""
    if action == "ping":
        return "pong"
    if action == "system_info":
        return "system_info accepted"
    if action == "list_allowed_apps":
        return "allowed_apps=" + ",".join(ALLOWED_APPS)
    if action == "open_url":
        url = str(safe_params.get("url", ""))[:120]
        return f"queued: open_url {url}"
    if action == "list_files_readonly":
        return "queued: list_files_readonly"
    if action == "capture_screenshot":
        return "waiting approval: capture_screenshot"
    if action == "open_url_execute":
        return "waiting approval: open_url_execute"
    return ""


__all__ = [
    "_initial_result_summary",
    "attach_token",
    "enqueue_task",
    "find_task_by_id",
    "find_task_by_token_id",
    "get_task",
    "list_pending_for_agent",
    "list_tasks_for_agent",
    "mark_approved",
    "mark_expired",
    "mark_rejected",
]

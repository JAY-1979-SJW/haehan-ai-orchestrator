"""Shared in-memory store, constants, and transition validator for local_agent_registry."""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Optional

from .local_agent_actions import AUTO_EXECUTE_VIA_AGENT
from .local_agent_risk_policy import (
    ACTION_RISK, _SERVER_AUTO_COMPLETE, ALLOWED_APPS
)
from .local_agent_models import LocalAgent, LocalAgentTask, RegisterResult


# ── timeout 상수 ────────────────────────────────────────────────────────

# delivered 상태에서 running 미전환 허용 시간 (초)
DELIVERED_TIMEOUT_SECONDS: int = 120
# running 상태에서 result 미수신 허용 시간 (초)
RUNNING_TIMEOUT_SECONDS: int = 300

# ── heartbeat / 상태 계산 상수 ──────────────────────────────────────────

# last_seen_at 이 이 초 이상 오래되면 stale 로 분류
HEARTBEAT_STALE_SECONDS: int = 90
# active task 로 간주하는 상태 집합
ACTIVE_TASK_STATUSES: frozenset[str] = frozenset({"delivered", "running", "cancel_requested"})


# ── 상태 전이 매트릭스 ───────────────────────────────────────────────────

VALID_TASK_TRANSITIONS: dict[str, set[str]] = {
    "queued":           {"delivered", "failed", "cancelled"},
    "delivered":        {"running", "failed", "cancel_requested"},
    "running":          {"completed", "failed", "cancel_requested"},
    "cancel_requested": {"cancelled", "failed", "completed"},
    "completed":        set(),
    "failed":           set(),
    "cancelled":        set(),
}

KNOWN_TASK_STATUSES: frozenset[str] = frozenset({
    "queued", "delivered", "running",
    "waiting_approval", "completed", "failed", "rejected",
    "cancel_requested", "cancelled",
})


class InvalidTaskTransitionError(ValueError):
    """허용되지 않은 상태 전이 시도."""


class UnknownActionError(ValueError):
    """미등록/금지 액션 요청. 라우터에서 400 으로 변환."""


# ── 인메모리 저장소 ──────────────────────────────────────────────────────

_lock = threading.Lock()
_agents: dict[str, LocalAgent] = {}
_tasks: dict[str, LocalAgentTask] = {}


# ── 시간 helper ───────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── 전이 검증 ─────────────────────────────────────────────────────────────

def _ensure_task_transition(task: LocalAgentTask, next_status: str) -> None:
    """task 의 현재 status → next_status 전이가 허용되는지 검증.

    허용되지 않으면 InvalidTaskTransitionError 를 발생시킨다.
    task 상태를 바꾸지 않는다 — 호출자가 변경 직전에 호출해야 한다.
    """
    allowed = VALID_TASK_TRANSITIONS.get(task.status, set())
    if next_status not in allowed:
        raise InvalidTaskTransitionError(
            f"invalid transition: {task.status!r} -> {next_status!r} "
            f"(task_id={task.task_id})"
        )


# ── 저장소 초기화 (테스트 전용) ──────────────────────────────────────────

def clear() -> None:
    """테스트 전용: 메모리 저장소 초기화."""
    with _lock:
        _agents.clear()
        _tasks.clear()


__all__ = [
    "AUTO_EXECUTE_VIA_AGENT",
    "ACTION_RISK", "_SERVER_AUTO_COMPLETE", "ALLOWED_APPS",
    "LocalAgent", "LocalAgentTask", "RegisterResult",
    "DELIVERED_TIMEOUT_SECONDS", "RUNNING_TIMEOUT_SECONDS",
    "HEARTBEAT_STALE_SECONDS", "ACTIVE_TASK_STATUSES",
    "VALID_TASK_TRANSITIONS", "KNOWN_TASK_STATUSES",
    "InvalidTaskTransitionError", "UnknownActionError",
    "_lock", "_agents", "_tasks",
    "_now_iso", "_ensure_task_transition", "clear",
]

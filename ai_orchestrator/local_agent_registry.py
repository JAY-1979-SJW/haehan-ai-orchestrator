"""로컬 에이전트 + 작업 큐 — 책임별 leaf 모듈 aggregator.

common/agent/task_queue/task_lifecycle/task_cancel/cleanup/sanitize
기능이 각 leaf 에 구현돼 있다. [docs/module_separation_standard.md]
"""
from __future__ import annotations

# ── 공유 모델·상수·에러 ──────────────────────────────────────────────────────
from .local_agent_registry_common import (  # noqa: F401
    InvalidTaskTransitionError, UnknownActionError,
    _now_iso, _ensure_task_transition, clear,
    _agents, _tasks, _lock,
    VALID_TASK_TRANSITIONS, KNOWN_TASK_STATUSES,
    DELIVERED_TIMEOUT_SECONDS, RUNNING_TIMEOUT_SECONDS,
    HEARTBEAT_STALE_SECONDS, ACTIVE_TASK_STATUSES,
)
# ── 모델 (기존 sub-모듈에서 re-export) ──────────────────────────────────────
from .local_agent_models import LocalAgent, LocalAgentTask, RegisterResult  # noqa: F401
from .local_agent_actions import AUTO_EXECUTE_VIA_AGENT  # noqa: F401
from .local_agent_risk_policy import ACTION_RISK, ALLOWED_APPS  # noqa: F401
# ── 에이전트 생명주기 ──────────────────────────────────────────────────────
from .local_agent_registry_agent import (  # noqa: F401
    register_agent, get_agent, list_agents, authenticate_agent,
    set_agent_connected, set_agent_last_seen, set_agent_disconnected,
    get_active_task_count, get_current_task_id, get_agent_status,
)
# ── 작업 큐 ────────────────────────────────────────────────────────────────
from .local_agent_registry_task_queue import (  # noqa: F401
    enqueue_task, get_task, attach_token, find_task_by_id, find_task_by_token_id,
    mark_approved, mark_rejected, mark_expired,
    list_tasks_for_agent, list_pending_for_agent,
)
# ── 작업 생명주기 ────────────────────────────────────────────────────────────
from .local_agent_registry_task_lifecycle import (  # noqa: F401
    _mark_task_failed, mark_delivered, mark_running, apply_result,
    expire_stale_tasks, fail_active_tasks_for_agent,
)
# ── 취소 ────────────────────────────────────────────────────────────────────
from .local_agent_registry_task_cancel import CancelNotAllowedError, cancel_task  # noqa: F401
# ── 정리 ────────────────────────────────────────────────────────────────────
from .local_agent_registry_cleanup import (  # noqa: F401
    get_agent_cleanup_preview, cleanup_agent_and_tasks,
)
# ── sanitize (내부, 일부 테스트에서 직접 import) ────────────────────────────
from .local_agent_registry_sanitize import (  # noqa: F401
    _sanitize_final_url_value, _build_audit_summary, _build_observe_summary,
)

__all__ = [
    "ACTION_RISK", "ALLOWED_APPS", "AUTO_EXECUTE_VIA_AGENT",
    "VALID_TASK_TRANSITIONS", "InvalidTaskTransitionError",
    "DELIVERED_TIMEOUT_SECONDS", "RUNNING_TIMEOUT_SECONDS",
    "HEARTBEAT_STALE_SECONDS", "ACTIVE_TASK_STATUSES",
    "LocalAgent", "LocalAgentTask", "RegisterResult",
    "UnknownActionError",
    "register_agent", "get_agent", "list_agents", "authenticate_agent",
    "enqueue_task", "get_task", "attach_token", "clear",
    "list_pending_for_agent", "mark_delivered", "mark_running", "apply_result",
    "find_task_by_id", "find_task_by_token_id",
    "mark_approved", "mark_rejected", "mark_expired",
    "expire_stale_tasks", "fail_active_tasks_for_agent",
    "KNOWN_TASK_STATUSES", "list_tasks_for_agent",
    "set_agent_connected", "set_agent_last_seen", "set_agent_disconnected",
    "get_active_task_count", "get_current_task_id", "get_agent_status",
    "cancel_task", "CancelNotAllowedError",
    "get_agent_cleanup_preview", "cleanup_agent_and_tasks",
]

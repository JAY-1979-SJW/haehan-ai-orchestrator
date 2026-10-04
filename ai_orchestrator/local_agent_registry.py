"""로컬 에이전트 + 작업 큐 — 책임별 leaf 모듈 aggregator.

common/agent/task_queue/task_lifecycle/task_cancel/cleanup/sanitize
기능이 각 leaf 에 구현돼 있다. [docs/module_separation_standard.md]
"""

from __future__ import annotations

from .local_agent_actions import AUTO_EXECUTE_VIA_AGENT

# ── 모델 (기존 sub-모듈에서 re-export) ──────────────────────────────────────
from .local_agent_models import LocalAgent, LocalAgentTask, RegisterResult

# ── 마스킹/정책 내부 이름 (레지스트리를 쪼갤 때 옛 창구에서 빠져, 이 이름을 창구로 참조하는
#    테스트 약 50건이 AttributeError/ImportError 였음 — 2026-09-30 복원) ─────────────
from .local_agent_redaction import (  # noqa: F401
    _RESULT_DATA_ALLOWED_KEYS,
    _SENSITIVE_KEYS,
    _strip_result_data,
)

# ── 에이전트 생명주기 ──────────────────────────────────────────────────────
from .local_agent_registry_agent import (
    authenticate_agent,
    clear_agent_capacity,
    get_agent_capacity,
    select_agent,
    set_agent_capacity,
    get_active_task_count,
    get_agent,
    get_agent_status,
    get_completed_task_count,
    get_current_task_id,
    get_failed_task_count,
    # 2026-09-29 수정(회귀 버그): 이 3개가 leaf 모듈엔 있는데 facade 재노출에서
    # 누락돼 있었다 — LocalAgent.to_safe()(local_agent_models.py)가
    # registry.get_task_count() 등을 호출하는데 AttributeError로 GET /local-agents
    # 자체가 500으로 깨졌다(실측 확인: 로컬 에이전트 재등록 검증 중 발견).
    get_task_count,
    list_agents,
    register_agent,
    set_agent_connected,
    set_agent_disconnected,
    set_agent_last_seen,
)

# ── 정리 ────────────────────────────────────────────────────────────────────
from .local_agent_registry_cleanup import (
    cleanup_agent_and_tasks,
    get_agent_cleanup_preview,
)

# ── 공유 모델·상수·에러 ──────────────────────────────────────────────────────
from .local_agent_registry_common import (  # noqa: F401
    ACTIVE_TASK_STATUSES,
    DELIVERED_TIMEOUT_SECONDS,
    HEARTBEAT_STALE_SECONDS,
    KNOWN_TASK_STATUSES,
    RUNNING_TIMEOUT_SECONDS,
    VALID_TASK_TRANSITIONS,
    InvalidTaskTransitionError,
    UnknownActionError,
    _agents,
    _ensure_task_transition,
    _lock,
    _now_iso,
    _tasks,
    clear,
)

# ── sanitize (내부, 일부 테스트에서 직접 import) ────────────────────────────
from .local_agent_registry_sanitize import (  # noqa: F401
    _build_audit_summary,
    _build_observe_summary,
    _sanitize_final_url_value,
)

# ── 취소 ────────────────────────────────────────────────────────────────────
from .local_agent_registry_task_cancel import CancelNotAllowedError, cancel_task

# ── 작업 생명주기 ────────────────────────────────────────────────────────────
from .local_agent_registry_task_lifecycle import (  # noqa: F401
    _mark_task_failed,
    apply_result,
    expire_stale_tasks,
    fail_active_tasks_for_agent,
    mark_delivered,
    mark_running,
)

# ── 작업 큐 ────────────────────────────────────────────────────────────────
from .local_agent_registry_task_queue import (
    attach_token,
    enqueue_task,
    find_task_by_id,
    find_task_by_token_id,
    get_task,
    list_pending_for_agent,
    list_tasks_for_agent,
    mark_approved,
    mark_expired,
    mark_rejected,
)
from .local_agent_risk_policy import (
    _SERVER_AUTO_COMPLETE,  # noqa: F401
    ACTION_RISK,
    ALLOWED_APPS,
)

__all__ = [
    "ACTION_RISK",
    "ACTIVE_TASK_STATUSES",
    "ALLOWED_APPS",
    "AUTO_EXECUTE_VIA_AGENT",
    "DELIVERED_TIMEOUT_SECONDS",
    "HEARTBEAT_STALE_SECONDS",
    "KNOWN_TASK_STATUSES",
    "RUNNING_TIMEOUT_SECONDS",
    "VALID_TASK_TRANSITIONS",
    "CancelNotAllowedError",
    "InvalidTaskTransitionError",
    "LocalAgent",
    "LocalAgentTask",
    "RegisterResult",
    "UnknownActionError",
    "apply_result",
    "attach_token",
    "authenticate_agent",
    "cancel_task",
    "cleanup_agent_and_tasks",
    "clear",
    "enqueue_task",
    "expire_stale_tasks",
    "clear_agent_capacity",
    "fail_active_tasks_for_agent",
    "find_task_by_id",
    "find_task_by_token_id",
    "get_active_task_count",
    "get_agent",
    "get_agent_capacity",
    "get_agent_cleanup_preview",
    "get_agent_status",
    "get_completed_task_count",
    "get_current_task_id",
    "get_failed_task_count",
    "get_task",
    "get_task_count",
    "list_agents",
    "list_pending_for_agent",
    "list_tasks_for_agent",
    "mark_approved",
    "mark_delivered",
    "mark_expired",
    "mark_rejected",
    "mark_running",
    "register_agent",
    "select_agent",
    "set_agent_capacity",
    "set_agent_connected",
    "set_agent_disconnected",
    "set_agent_last_seen",
]

"""로컬 에이전트 레지스트리 재노출 leaf — 공유 leaf(common/sanitize/agent)와 모델·정책 이름.

root(local_agent_registry.py)는 이 leaf 와 나머지 leaf 를 재노출하는 얇은 파사드다.
공개 API·내부(언더스코어) 이름은 root 에서 그대로 import/속성 접근 가능해야 한다.
[docs/module_separation_standard.md]
"""

# ruff: noqa: F401
from __future__ import annotations

from ...contracts.local_agent_actions import AUTO_EXECUTE_VIA_AGENT
from ..models import LocalAgent, LocalAgentTask, RegisterResult

# 마스킹/정책 내부 이름 — 이 이름을 창구로 참조하는 테스트 다수 (2026-09-30 복원)
from ..redaction import (
    _RESULT_DATA_ALLOWED_KEYS,
    _SENSITIVE_KEYS,
    _strip_result_data,
)
from .agent import (
    authenticate_agent,
    clear_agent_capacity,
    get_active_task_count,
    get_agent,
    get_agent_capacity,
    get_agent_status,
    get_completed_task_count,
    get_current_task_id,
    get_failed_task_count,
    # 2026-09-29 회귀 수정: LocalAgent.to_safe() 가 registry.get_task_count() 등을 호출 —
    # 재노출 누락 시 GET /local-agents 가 500.
    get_task_count,
    list_agents,
    register_agent,
    select_agent,
    set_agent_capacity,
    set_agent_connected,
    set_agent_disconnected,
    set_agent_last_seen,
)
from .common import (
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
from .sanitize import (
    _build_audit_summary,
    _build_observe_summary,
    _sanitize_final_url_value,
)
from ..policy.risk_policy import (
    _SERVER_AUTO_COMPLETE,
    ACTION_RISK,
    ALLOWED_APPS,
)

# root __all__ 중 이 leaf 가 정의/재노출하는 공개 이름
EXPORTED_NAMES = [
    "ACTION_RISK", "ACTIVE_TASK_STATUSES", "ALLOWED_APPS", "AUTO_EXECUTE_VIA_AGENT",
    "DELIVERED_TIMEOUT_SECONDS", "HEARTBEAT_STALE_SECONDS", "KNOWN_TASK_STATUSES",
    "RUNNING_TIMEOUT_SECONDS", "VALID_TASK_TRANSITIONS", "InvalidTaskTransitionError",
    "LocalAgent", "LocalAgentTask", "RegisterResult", "UnknownActionError",
    "authenticate_agent", "clear", "clear_agent_capacity", "get_active_task_count",
    "get_agent", "get_agent_capacity", "get_agent_status", "get_completed_task_count",
    "get_current_task_id", "get_failed_task_count", "get_task_count", "list_agents",
    "register_agent", "select_agent", "set_agent_capacity", "set_agent_connected",
    "set_agent_disconnected", "set_agent_last_seen",
]  # fmt: skip

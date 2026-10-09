"""Shared in-memory store, constants, and transition validator for local_agent_registry."""

from __future__ import annotations

import contextlib
import json
import threading
from datetime import UTC, datetime

from ai_orchestrator.paths.runtime import data_dir

from ...contracts.local_agent_actions import AUTO_EXECUTE_VIA_AGENT
from ..models import LocalAgent, LocalAgentTask, RegisterResult
from ..policy.risk_policy import _SERVER_AUTO_COMPLETE, ACTION_RISK, ALLOWED_APPS

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

# WS 연결 끊김(websocket_disconnected)으로 실패할 뻔한 작업을 재큐잉 허용할 최대 횟수.
# 이 횟수를 넘으면 더 재시도하지 않고 failed 로 종결(작업 자체가 매번 agent를 죽이는
# 경우 등 무한 재시도 방지). 2026-09-30: 사용자가 실제로 AI 채팅에서 겪은
# "작업 실패: websocket_disconnected"(에이전트 재기동 도중 들어온 요청이 그 자리에서
# 바로 실패 처리되던 문제)를 고치며 추가.
MAX_WS_DISCONNECT_RETRIES: int = 2


# ── 상태 전이 매트릭스 ───────────────────────────────────────────────────

VALID_TASK_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"delivered", "failed", "cancelled"},
    # "queued" 로의 역행은 WS 연결 끊김 재큐잉 전용(fail_active_tasks_for_agent) — 사람이나
    # 일반 흐름이 delivered/running에서 queued 로 되돌리는 다른 경로는 없다.
    "delivered": {"running", "failed", "cancel_requested", "queued"},
    "running": {"completed", "failed", "cancel_requested", "queued"},
    "cancel_requested": {"cancelled", "failed", "completed"},
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
}

KNOWN_TASK_STATUSES: frozenset[str] = frozenset(
    {
        "queued",
        "delivered",
        "running",
        "waiting_approval",
        "completed",
        "failed",
        "rejected",
        "cancel_requested",
        "cancelled",
    }
)


class InvalidTaskTransitionError(ValueError):
    """허용되지 않은 상태 전이 시도."""


class UnknownActionError(ValueError):
    """미등록/금지 액션 요청. 라우터에서 400 으로 변환."""


# ── 인메모리 저장소 ──────────────────────────────────────────────────────

_lock = threading.Lock()
_agents: dict[str, LocalAgent] = {}
_tasks: dict[str, LocalAgentTask] = {}


# ── 에이전트 정체성 영속화 (2026-09-29 추가) ──────────────────────────────
# FastAPI 프로세스가 재시작되면 인메모리 _agents가 비어 authenticate_agent()가 기존
# device_token을 전부 거부해 WS가 4401로 끊기는 문제(실측 확인: core/agent_runtime/agent.py는
# 클라이언트 쪽 토큰을 keyring에 영속 보관하지만 서버는 재시작마다 전부 잊었다) — 등록
# 정체성(agent_id/token_hash 등, 연결상태 제외)만 디스크에 저장해 재시작 후에도 기존
# 에이전트가 그대로 재인증되게 한다. 연결상태(connected_at 등)는 저장하지 않는다 —
# 재시작 직후는 실제로 미연결 상태가 맞고, 클라이언트가 재연결하면 set_agent_connected가
# 정확히 다시 채운다. token_hash만 저장(device_token 원문 저장 금지 — 기존 보안 정책과 동일).
_REGISTRY_STATE_PATH = data_dir() / "local_agent_registry_state.json"


def _save_agents_to_disk() -> None:
    """등록된 에이전트 정체성을 디스크에 저장.

    2026-09-29 pre-push AI 리뷰 지적 반영: 처음엔 _lock 없이 _agents.items()를 순회해
    동시 수정(register_agent/cleanup_agent_and_tasks) 중 경쟁 가능성이 있었다. _lock은
    재진입 불가(threading.Lock)라 "락을 쥔 채로 이 함수를 부르는" 설계는 데드락 위험이 —
    그래서 이 함수 자체가 짧게 락을 잡아 스냅샷만 뜨고, 실제 파일 I/O(느릴 수 있음)는
    락 밖에서 수행한다. 호출부(register_agent/cleanup_agent_and_tasks)는 반드시 자신의
    with _lock 블록을 벗어난 뒤에 이 함수를 불러야 한다(안 그러면 아래 with _lock에서 교착).
    """
    with _lock:
        payload = {
            aid: {
                "agent_id": a.agent_id,
                "host": a.host,
                "os_name": a.os_name,
                "version": a.version,
                "registered_at": a.registered_at,
                "requested_by": a.requested_by,
                "token_hash": a.token_hash,
                "smoke_test": a.smoke_test,
            }
            for aid, a in _agents.items()
        }
    try:
        _REGISTRY_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _REGISTRY_STATE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_REGISTRY_STATE_PATH)
    except OSError:
        # 영속화 실패는 비치명적 — 다음 등록/정리 시점에 재시도, 서버 기동 자체는 막지 않음
        pass


def _load_agents_from_disk() -> None:
    if not _REGISTRY_STATE_PATH.exists():
        return
    try:
        raw = json.loads(_REGISTRY_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    for aid, fields in raw.items():
        try:
            _agents[aid] = LocalAgent(
                agent_id=fields["agent_id"],
                host=fields.get("host", ""),
                os_name=fields.get("os_name", ""),
                version=fields.get("version", ""),
                registered_at=fields.get("registered_at", ""),
                requested_by=fields.get("requested_by", ""),
                token_hash=fields["token_hash"],
                smoke_test=fields.get("smoke_test", False),
            )
        except (KeyError, TypeError):
            continue


_load_agents_from_disk()  # 모듈 임포트(서버 기동) 시 1회 복원


# ── 시간 helper ───────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ── 전이 검증 ─────────────────────────────────────────────────────────────


def _ensure_task_transition(task: LocalAgentTask, next_status: str) -> None:
    """task 의 현재 status → next_status 전이가 허용되는지 검증.

    허용되지 않으면 InvalidTaskTransitionError 를 발생시킨다.
    task 상태를 바꾸지 않는다 — 호출자가 변경 직전에 호출해야 한다.
    """
    allowed = VALID_TASK_TRANSITIONS.get(task.status, set())
    if next_status not in allowed:
        raise InvalidTaskTransitionError(
            f"invalid transition: {task.status!r} -> {next_status!r} (task_id={task.task_id})"
        )


# ── 저장소 초기화 (테스트 전용) ──────────────────────────────────────────


def clear() -> None:
    """테스트 전용: 메모리 저장소 + 영속화 파일 초기화.

    2026-09-29 영속화 추가 후: 디스크 파일을 같이 안 지우면 이전 테스트/개발 세션이 남긴
    agent 상태가 다음 테스트의 모듈 임포트 시 자동 로드되어 테스트 간 오염이 생긴다.
    """
    with _lock:
        _agents.clear()
        _tasks.clear()
    with contextlib.suppress(OSError):
        _REGISTRY_STATE_PATH.unlink(missing_ok=True)


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
    "_REGISTRY_STATE_PATH",
    "_SERVER_AUTO_COMPLETE",
    "InvalidTaskTransitionError",
    "LocalAgent",
    "LocalAgentTask",
    "RegisterResult",
    "UnknownActionError",
    "_agents",
    "_ensure_task_transition",
    "_load_agents_from_disk",
    "_lock",
    "_now_iso",
    "_save_agents_to_disk",
    "_tasks",
    "clear",
]

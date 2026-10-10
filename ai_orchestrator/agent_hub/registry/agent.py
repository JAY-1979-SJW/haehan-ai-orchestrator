"""Agent registration, authentication, and connection-state helpers."""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import datetime

from ..models import LocalAgent, RegisterResult
from .common import (
    ACTIVE_TASK_STATUSES,
    HEARTBEAT_STALE_SECONDS,
    _agents,
    _lock,
    _now_iso,
    _save_agents_to_disk,
    _tasks,
)

logger = logging.getLogger(__name__)

MAX_AGENT_PARALLEL = 3  # 에이전트 1대가 동시에 처리할 수 있는 작업 수 상한(기준서 P1)
_agent_capacity: dict[str, int] = {}

# ── 등록 / 조회 ──────────────────────────────────────────────────────────


def register_agent(
    *,
    host: str,
    os_name: str,
    version: str,
    requested_by: str,
    smoke_test: bool = False,
) -> RegisterResult:
    """새 에이전트 등록. agent_id + device_token 발급, 서버는 토큰 해시만 저장.

    device_token 원문은 호출자(라우터) 가 응답에 1회만 노출하고 폐기한다.
    smoke_test: smoke test marker for cleanup eligibility.
    """
    host = (host or "").strip() or "unknown-host"
    os_name = (os_name or "").strip() or "unknown-os"
    version = (version or "").strip() or "0.0.0"

    agent_id = f"la-{uuid.uuid4().hex[:12]}"
    device_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(device_token.encode("utf-8")).hexdigest()

    agent = LocalAgent(
        agent_id=agent_id,
        host=host,
        os_name=os_name,
        version=version,
        registered_at=_now_iso(),
        requested_by=requested_by,
        token_hash=token_hash,
        smoke_test=smoke_test,
    )
    with _lock:
        _agents[agent_id] = agent
    _save_agents_to_disk()  # 2026-09-29: 재시작 후에도 재인증되도록 정체성 영속화
    return RegisterResult(agent=agent, device_token=device_token)


def get_agent(agent_id: str) -> LocalAgent | None:
    return _agents.get(agent_id)


def agent_stats(agent_id: str) -> dict:
    """LocalAgent.to_safe() 에 넘기는 연결 상태·작업 통계(레지스트리가 계산)."""
    return {
        "agent_status": get_agent_status(agent_id),
        "active_task_count": get_active_task_count(agent_id),
        "current_task_id": get_current_task_id(agent_id),
        "task_count": get_task_count(agent_id),
        "completed_task_count": get_completed_task_count(agent_id),
        "failed_task_count": get_failed_task_count(agent_id),
    }


def list_agents() -> list[dict]:
    return [a.to_safe(agent_stats(a.agent_id)) for a in _agents.values()]


def authenticate_agent(agent_id: str, device_token: str) -> LocalAgent | None:
    """agent_id + device_token 원문을 검증. 성공 시 LocalAgent, 실패 시 None.

    - 타이밍 공격 방지: secrets.compare_digest 로 상수 시간 비교.
    - device_token 원문은 본 함수의 인자로만 존재하며 어떤 속성에도 저장하지 않는다.
    - 호출자는 실패 로그에 token 원문을 절대 기록하면 안 된다.
    """
    if not agent_id or not device_token:
        return None
    agent = _agents.get(agent_id)
    if agent is None:
        return None
    try:
        candidate_hash = hashlib.sha256(device_token.encode("utf-8")).hexdigest()
    except Exception as exc:  # noqa: BLE001 - device_token 해시 계산 실패 시 인증 실패(None)로 폴백 - 이미 fail-closed(허용 아님), secrets.compare_digest 상수시간 비교 로직 앞단 가드
        logger.warning("디바이스 토큰 해시 계산 실패: %s", type(exc).__name__)
        return None
    if not secrets.compare_digest(candidate_hash, agent.token_hash):
        return None
    return agent


# ── 연결 상태 helper ─────────────────────────────────────────────────────


def set_agent_connected(agent_id: str, now: str | None = None) -> None:
    with _lock:
        a = _agents.get(agent_id)
        if a is None:
            return
        ts = now if now is not None else _now_iso()
        a.connected_at = ts
        a.last_seen_at = ts
        a.disconnected_at = ""


def set_agent_last_seen(agent_id: str, now: str | None = None) -> None:
    with _lock:
        a = _agents.get(agent_id)
        if a is None:
            return
        a.last_seen_at = now if now is not None else _now_iso()


def set_agent_disconnected(agent_id: str, now: str | None = None) -> None:
    # last_seen_at은 기존 값 유지 (disconnect 시각은 별도 필드로만 기록)
    with _lock:
        a = _agents.get(agent_id)
        if a is None:
            return
        a.disconnected_at = now if now is not None else _now_iso()


def set_agent_capacity(agent_id: str, max_parallel: object) -> int:
    """에이전트가 auth 때 알린 동시 처리 수를 저장(1~3으로 제한, 잘못된 값은 1)."""
    try:
        value = int(max_parallel)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        value = 1
    value = max(1, min(MAX_AGENT_PARALLEL, value))
    with _lock:
        _agent_capacity[agent_id] = value
    return value


def get_agent_capacity(agent_id: str) -> int:
    with _lock:
        return _agent_capacity.get(agent_id, 1)


def clear_agent_capacity(agent_id: str) -> None:
    with _lock:
        _agent_capacity.pop(agent_id, None)


def get_active_task_count(agent_id: str) -> int:
    with _lock:
        return sum(1 for t in _tasks.values() if t.agent_id == agent_id and t.status in ACTIVE_TASK_STATUSES)


def select_agent(agents: list[dict]) -> dict | None:
    """작업을 보낼 에이전트 선택: idle → 동시 처리 용량이 남은 busy → 첫 번째(큐에 쌓임). 없으면 None."""
    if not agents:
        return None
    idle = next((a for a in agents if a.get("agent_status") == "idle"), None)
    if idle is not None:
        return idle
    for a in agents:
        if a.get("agent_status") == "busy" and get_active_task_count(a["agent_id"]) < get_agent_capacity(a["agent_id"]):
            return a
    return agents[0]


def get_current_task_id(agent_id: str) -> str:
    """running task 중 started_at 또는 updated_at 기준 최신 1개의 task_id."""
    with _lock:
        running = [t for t in _tasks.values() if t.agent_id == agent_id and t.status == "running"]
    if not running:
        return ""
    best = max(running, key=lambda t: t.started_at or t.updated_at)
    return best.task_id


def get_task_count(agent_id: str) -> int:
    """agent의 전체 task 수."""
    with _lock:
        return sum(1 for t in _tasks.values() if t.agent_id == agent_id)


def get_completed_task_count(agent_id: str) -> int:
    """agent의 completed task 수."""
    with _lock:
        return sum(1 for t in _tasks.values() if t.agent_id == agent_id and t.status == "completed")


def get_failed_task_count(agent_id: str) -> int:
    """agent의 failed/error/cancelled task 수."""
    with _lock:
        return sum(
            1 for t in _tasks.values() if t.agent_id == agent_id and t.status in ("failed", "error", "cancelled")
        )


def get_agent_status(agent_id: str, now: str | None = None) -> str:
    """agent_id 기준 상태 계산 (저장 필드 아님)."""
    a = _agents.get(agent_id)
    if a is None:
        return "offline"
    if not a.connected_at:
        return "offline"
    if a.disconnected_at:
        return "offline"
    if a.last_seen_at:
        ts_now = now if now is not None else _now_iso()
        try:
            last = datetime.fromisoformat(a.last_seen_at)
            cur = datetime.fromisoformat(ts_now)
            if (cur - last).total_seconds() > HEARTBEAT_STALE_SECONDS:
                return "stale"
        except (ValueError, TypeError):
            pass
    if get_active_task_count(agent_id) > 0:
        return "busy"
    return "idle"


__all__ = [
    "MAX_AGENT_PARALLEL",
    "clear_agent_capacity",
    "get_agent_capacity",
    "select_agent",
    "set_agent_capacity",
    "authenticate_agent",
    "get_active_task_count",
    "get_agent",
    "get_agent_status",
    "get_completed_task_count",
    "get_current_task_id",
    "get_failed_task_count",
    "get_task_count",
    "list_agents",
    "register_agent",
    "set_agent_connected",
    "set_agent_disconnected",
    "set_agent_last_seen",
]

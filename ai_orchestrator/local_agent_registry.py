"""로컬 에이전트 + 작업 큐 (Stage 1/2 공용).

서버 측에서만 사용. 실제 작업 실행은 Windows 로컬 에이전트(local_agent/)
프로세스가 담당하며, 서버는 등록·조회·큐 관리·승인 게이트만 제공한다.

보안:
  - device_token 원문은 register 응답에 1회만 노출, 서버 저장은 SHA-256 해시만.
  - params 의 민감 키(password/token/cookie/secret …) 는 _strip_sensitive() 로 제거 후 저장.
  - 미등록 액션(delete_file/upload_file/modify_file/execute_shell …) 은 UNKNOWN_ACTION 로 거절.

Stage 2 추가:
  - LocalAgentTask 에 delivered_at / started_at / completed_at / error_summary 필드.
  - status 에 delivered / running / failed 추가.
  - authenticate_agent(), list_pending_for_agent(), mark_delivered(),
    mark_running(), apply_result() 추가 — WebSocket 핸들러에서 사용.
"""
from __future__ import annotations

import hashlib
import secrets
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from .local_agent_actions import AUTO_EXECUTE_VIA_AGENT
from .local_agent_risk_policy import (
    ACTION_RISK, _SERVER_AUTO_COMPLETE, ALLOWED_APPS
)
from .local_agent_models import LocalAgent, LocalAgentTask, RegisterResult
from .local_agent_redaction import (
    _SENSITIVE_KEYS, _strip_sensitive, _RESULT_DATA_ALLOWED_KEYS,
    _sanitize_url_for_storage, _strip_result_data
)


# ── 민감 정보 정책 ────────────────────────────────────────────────────────────
# _SENSITIVE_KEYS, _strip_sensitive, _RESULT_DATA_ALLOWED_KEYS,
# _sanitize_url_for_storage, _strip_result_data 는 local_agent_redaction.py에서 import


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── 데이터 모델 ──────────────────────────────────────────────────────────
# LocalAgent, LocalAgentTask, RegisterResult 는 local_agent_models.py에서 import


# ── timeout 상수 ────────────────────────────────────────────────────────

# delivered 상태에서 running 미전환 허용 시간 (초)
DELIVERED_TIMEOUT_SECONDS: int = 120
# running 상태에서 result 미수신 허용 시간 (초)
RUNNING_TIMEOUT_SECONDS: int = 300

# ── heartbeat / 상태 계산 상수 ──────────────────────────────────────────

# last_seen_at 이 이 초 이상 오래되면 stale 로 분류
HEARTBEAT_STALE_SECONDS: int = 90
# active task 로 간주하는 상태 집합 (cancel_requested 포함 — 아직 agent가 처리 중)
ACTIVE_TASK_STATUSES: frozenset[str] = frozenset({"delivered", "running", "cancel_requested"})


# ── 상태 전이 매트릭스 ───────────────────────────────────────────────────

# 허용된 상태 전이만 등록. 미등록 전이는 _ensure_task_transition 이 차단한다.
# waiting_approval/rejected 는 별도 함수(mark_approved/mark_rejected/mark_expired)
# 에서만 처리하므로 여기서는 정규 실행 흐름만 포함한다.
# waiting_approval → cancelled 는 cancel_task() 전용 함수에서만 처리한다.
VALID_TASK_TRANSITIONS: dict[str, set[str]] = {
    "queued":           {"delivered", "failed", "cancelled"},
    "delivered":        {"running", "failed", "cancel_requested"},
    "running":          {"completed", "failed", "cancel_requested"},
    "cancel_requested": {"cancelled", "failed", "completed"},
    "completed":        set(),
    "failed":           set(),
    "cancelled":        set(),
}


class InvalidTaskTransitionError(ValueError):
    """허용되지 않은 상태 전이 시도."""


def _ensure_task_transition(task: "LocalAgentTask", next_status: str) -> None:
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


# ── 인메모리 저장소 ──────────────────────────────────────────────────────

_lock = threading.Lock()
_agents: dict[str, LocalAgent] = {}
_tasks: dict[str, LocalAgentTask] = {}


def clear() -> None:
    """테스트 전용: 메모리 저장소 초기화."""
    with _lock:
        _agents.clear()
        _tasks.clear()


# ── 연결 상태 helper ─────────────────────────────────────────────────────

def set_agent_connected(agent_id: str, now: Optional[str] = None) -> None:
    with _lock:
        a = _agents.get(agent_id)
        if a is None:
            return
        ts = now if now is not None else _now_iso()
        a.connected_at = ts
        a.last_seen_at = ts
        a.disconnected_at = ""


def set_agent_last_seen(agent_id: str, now: Optional[str] = None) -> None:
    with _lock:
        a = _agents.get(agent_id)
        if a is None:
            return
        a.last_seen_at = now if now is not None else _now_iso()


def set_agent_disconnected(agent_id: str, now: Optional[str] = None) -> None:
    # last_seen_at은 기존 값 유지 (disconnect 시각은 별도 필드로만 기록)
    with _lock:
        a = _agents.get(agent_id)
        if a is None:
            return
        a.disconnected_at = now if now is not None else _now_iso()


def get_active_task_count(agent_id: str) -> int:
    with _lock:
        return sum(
            1 for t in _tasks.values()
            if t.agent_id == agent_id and t.status in ACTIVE_TASK_STATUSES
        )


def get_current_task_id(agent_id: str) -> str:
    """running task 중 started_at 또는 updated_at 기준 최신 1개의 task_id."""
    with _lock:
        running = [
            t for t in _tasks.values()
            if t.agent_id == agent_id and t.status == "running"
        ]
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
        return sum(1 for t in _tasks.values()
                   if t.agent_id == agent_id and t.status == "completed")


def get_failed_task_count(agent_id: str) -> int:
    """agent의 failed/error/cancelled task 수."""
    with _lock:
        return sum(1 for t in _tasks.values()
                   if t.agent_id == agent_id and t.status in ("failed", "error", "cancelled"))


def get_agent_status(agent_id: str, now: Optional[str] = None) -> str:
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


# ── 등록 / 조회 ──────────────────────────────────────────────────────────

def register_agent(
    *, host: str, os_name: str, version: str, requested_by: str,
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
    return RegisterResult(agent=agent, device_token=device_token)


def get_agent(agent_id: str) -> Optional[LocalAgent]:
    return _agents.get(agent_id)


def list_agents() -> list[dict]:
    return [a.to_safe() for a in _agents.values()]


def authenticate_agent(agent_id: str, device_token: str) -> Optional[LocalAgent]:
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
    except Exception:
        return None
    if not secrets.compare_digest(candidate_hash, agent.token_hash):
        return None
    return agent


# ── 작업 큐 ──────────────────────────────────────────────────────────────

class UnknownActionError(ValueError):
    """미등록/금지 액션 요청. 라우터에서 400 으로 변환."""


def enqueue_task(
    *,
    agent_id: str,
    action: str,
    params: Optional[dict],
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


def get_task(agent_id: str, task_id: str) -> Optional[LocalAgentTask]:
    t = _tasks.get(task_id)
    if t is None or t.agent_id != agent_id:
        return None
    return t


def find_task_by_id(task_id: str) -> Optional[LocalAgentTask]:
    """agent_id 불필요한 내부 조회 (승인 훅 등). agent 범위 권한 검사는 호출자가 수행."""
    return _tasks.get(task_id)


def find_task_by_token_id(token_id: str) -> Optional[LocalAgentTask]:
    """승인 토큰 → 대응 local agent task 역인덱스 (선형 탐색 — 요청 주기 낮음)."""
    if not token_id:
        return None
    with _lock:
        for t in _tasks.values():
            if t.token_id and t.token_id == token_id:
                return t
    return None


def mark_approved(task_id: str, actor: str) -> Optional[LocalAgentTask]:
    """waiting_approval → queued 로 전환. 이미 결정된 작업은 그대로 반환 (idempotent).

    - high risk 아닌 작업이 실수로 전달되면 no-op (상태 변경 없음).
    - approved_at 은 최초 승인 시각 1회만 기록 (재실행 방지 근거).
    """
    with _lock:
        t = _tasks.get(task_id)
        if t is None:
            return None
        if t.status != "waiting_approval":
            # 이미 queued/delivered/running/completed/failed/rejected → 상태 변경 없음
            return t
        if t.risk_level != "high":
            # 승인이 필요 없는 작업을 승인으로 이동시키지 않는다.
            return t
        now = _now_iso()
        t.status = "queued"
        t.approved_at = now
        t.approved_by = (actor or "")[:80]
        t.updated_at = now
        return t


def mark_rejected(
    task_id: str, actor: str, reason: str = "",
) -> Optional[LocalAgentTask]:
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
        t.approved_by = (actor or "")[:80]  # 의사결정자 기록 (거절 포함)
        t.reject_reason = (reason or "")[:200]
        t.completed_at = now
        t.updated_at = now
        return t


def mark_expired(task_id: str) -> Optional[LocalAgentTask]:
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


# ── 실패 처리 helper / timeout 만료 ────────────────────────────────────

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


def expire_stale_tasks(
    now: Optional[datetime] = None,
) -> list[LocalAgentTask]:
    """delivered/running/cancel_requested 상태 중 timeout 초과 task 를 failed 로 전환.

    - delivered 상태: delivered_at 기준 DELIVERED_TIMEOUT_SECONDS 초과
    - running 상태: started_at 기준 RUNNING_TIMEOUT_SECONDS 초과
    - cancel_requested 상태: cancel_requested_at 기준 RUNNING_TIMEOUT_SECONDS 초과
      (failure_reason="cancel_timeout")
    - queued / completed / failed 등 다른 상태는 건드리지 않는다.
    - 만료 처리된 task 목록을 반환한다 (감사 로그는 호출자가 기록).
    - now 를 주입하면 테스트에서 시간 조작이 가능하다.
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
                # 타임스탬프 파싱 실패 — 해당 task 는 건너뜀
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
    - timed_out_at은 설정하지 않는다 (timeout 아님).
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


# ── task 목록 조회 ──────────────────────────────────────────────────────

KNOWN_TASK_STATUSES: frozenset[str] = frozenset({
    "queued", "delivered", "running",
    "waiting_approval", "completed", "failed", "rejected",
    "cancel_requested", "cancelled",
})


def list_tasks_for_agent(
    agent_id: str,
    status: Optional[str] = None,
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


# ── Stage 2 전달/결과 ───────────────────────────────────────────────────

def list_pending_for_agent(agent_id: str) -> list[LocalAgentTask]:
    """해당 에이전트의 status=queued 작업 (오래된 것부터)."""
    with _lock:
        out = [t for t in _tasks.values()
               if t.agent_id == agent_id and t.status == "queued"]
    out.sort(key=lambda t: t.created_at)
    return out


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
        # running/delivered/cancel_requested 에서만 결과 적용 가능.
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
            # error_summary 는 민감값이 섞일 수 있어 짧게만 보존
            msg = (error_code + ": " + (error or summary or "")).strip(": ")
            t.error_summary = msg[:500]
            t.result_summary = (summary or "")[:500]
            if not t.failure_reason:
                t.failure_reason = "agent_error"
            # 실패한 task에서도 audit_summary 저장 가능 (필드 안전성 검증)
            if audit_summary is not None:
                t.audit_summary = _build_audit_summary(audit_summary)
        t.completed_at = now
        t.updated_at = now
        return t


def _initial_result_summary(action: str, safe_params: dict) -> str:
    """서버 즉시 완료 액션의 안전 요약 텍스트 (민감 원문 금지)."""
    if action == "ping":
        return "pong"
    if action == "system_info":
        # 실제 PC 정보는 에이전트가 보고한다. 서버는 요약만.
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


# ── 취소 엔진 ────────────────────────────────────────────────────────────

class CancelNotAllowedError(ValueError):
    """이미 종결된 또는 재취소 불가 상태에서 취소를 시도할 때."""


_CANCEL_TERMINAL_STATUSES: frozenset[str] = frozenset({
    "completed", "failed", "rejected", "cancelled",
})

_CANCEL_REASON_MAX_LEN = 200


def cancel_task(
    agent_id: str,
    task_id: str,
    *,
    actor: str = "",
    reason: str = "",
    now: Optional[datetime] = None,
) -> tuple["LocalAgentTask", str]:
    """task 취소 엔진. 상태에 따라 즉시 cancelled 또는 cancel_requested 로 전환.

    반환: (task, action_str)
      - action_str = "cancelled"        (queued / waiting_approval)
      - action_str = "cancel_requested" (delivered / running)

    예외:
      - ValueError: task 없음, agent_id 불일치, reason 초과
      - CancelNotAllowedError: terminal 상태 또는 cancel_requested 재취소
    """
    if reason and len(reason) > _CANCEL_REASON_MAX_LEN:
        raise ValueError(
            f"reason 이 최대 길이({_CANCEL_REASON_MAX_LEN}자)를 초과합니다"
        )

    now_dt = now if now is not None else datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()
    safe_reason = (reason or "")[:_CANCEL_REASON_MAX_LEN]
    safe_actor = (actor or "")[:80]

    with _lock:
        t = _tasks.get(task_id)
        if t is None or t.agent_id != agent_id:
            raise ValueError(f"task 없음 또는 agent_id 불일치: {agent_id}/{task_id}")

        if t.status in _CANCEL_TERMINAL_STATUSES:
            raise CancelNotAllowedError(
                f"취소 불가 — 이미 종결된 상태: {t.status!r} (task_id={task_id})"
            )

        if t.status == "cancel_requested":
            raise CancelNotAllowedError(
                f"취소 불가 — 이미 cancel_requested 상태 (task_id={task_id})"
            )

        if t.status in ("queued", "waiting_approval"):
            # agent에 아직 전달되지 않음 → 즉시 cancelled
            _ensure_task_transition(t, "cancelled") if t.status == "queued" else None
            # waiting_approval → cancelled 는 VALID_TASK_TRANSITIONS 미등록 (전용 처리)
            t.status = "cancelled"
            t.cancel_reason = safe_reason
            t.cancel_requested_by = safe_actor
            t.cancelled_at = now_iso
            t.completed_at = now_iso
            t.updated_at = now_iso
            return t, "cancelled"

        if t.status in ("delivered", "running"):
            # agent에 전달됐거나 실행 중 → cancel_requested
            _ensure_task_transition(t, "cancel_requested")
            t.status = "cancel_requested"
            t.cancel_reason = safe_reason
            t.cancel_requested_by = safe_actor
            t.cancel_requested_at = now_iso
            t.updated_at = now_iso
            return t, "cancel_requested"

        # 예상치 못한 상태 방어
        raise CancelNotAllowedError(
            f"취소 불가 — 처리되지 않은 상태: {t.status!r} (task_id={task_id})"
        )


# ── observe_summary sanitize ─────────────────────────────────────────────

_OBSERVE_SUMMARY_ALLOWED_KEYS: frozenset = frozenset({
    "target_kind", "url_category", "final_url_sanitized",
    "title", "title_len", "status_category", "pages_observed_count",
    "error_category", "blocked_reason", "login_required_hint",
    "modal_candidates_count", "html_truncated", "page_structure_counts",
    "observed_at",
})

_OBSERVE_FORBIDDEN_KEYS: frozenset = frozenset({
    "cookie", "session", "token", "authorization", "password",
    "localstorage", "sessionstorage", "html", "content", "body",
    "query", "fragment", "headers", "login_reason", "modal_candidates",
    "page_structure", "current_url",
})

# Stage 13C-2: audit_summary 허용 필드 (allowlist approach)
_AUDIT_SUMMARY_ALLOWED_KEYS: frozenset = frozenset({
    # STORE_AND_DISPLAY
    "audit_event_count", "audit_window_started_at", "audit_window_ended_at",
    "audit_event_categories", "blocked_event_count", "allowed_event_count",
    "denied_event_count", "error_event_count", "last_event_category",
    "last_event_status", "policy_decision_counts", "target_kind_counts",
    "action_kind_counts",
    # STORE_ONLY
    "audit_schema_version", "local_audit_source", "agent_reported_event_count",
    "audit_summary_generated_at", "audit_summary_hash", "dropped_event_count",
    "redacted_field_count",
})

_AUDIT_SUMMARY_FORBIDDEN_KEYS: frozenset = frozenset({
    "raw_events", "events", "event_list", "event_payload", "raw_audit",
    "audit_jsonl", "current_url", "url", "query", "fragment",
    "html", "text", "page_text", "modal_text", "selector", "screenshot_path",
    "local_file_path", "path", "absolute_path", "cookie", "session", "token",
    "password", "authorization", "headers", "request_headers", "response_headers",
    "request_body", "response_body", "body", "localstorage", "sessionstorage",
    "clipboard", "typed_text", "form_input_value", "username", "pc_username",
    "ip", "host",
})

_PAGE_STRUCTURE_COUNT_KEYS: tuple = (
    "headings", "links", "buttons", "inputs", "forms", "tables",
)


def _sanitize_final_url_value(raw: object) -> Optional[str]:
    """final_url_sanitized 검증: query/fragment 제거, 허용 대상만 반환."""
    if not isinstance(raw, str):
        return None
    raw = raw.strip()
    if raw.lower() == "about:blank":
        return "about:blank"
    try:
        parsed = urlparse(raw)
        host = (parsed.hostname or "").lower()
        if host in ("127.0.0.1", "localhost"):
            port_str = f":{parsed.port}" if parsed.port else ""
            return f"{parsed.scheme}://{host}{port_str}{parsed.path}"
    except Exception:
        pass
    return None


def _build_audit_summary(raw: Optional[dict]) -> Optional[dict]:
    """WS result에서 받은 raw audit_summary를 allowlist로 sanitize.

    PC local audit.jsonl 원문 절대 포함 금지.
    - Count 필드만 저장 (raw 이벤트 저장 금지)
    - URL/path/HTML/text/selector/header/body/cookie/token/password 금지
    - Enum 문자열만 허용 (길이 제한, 자유 문자열 금지)
    - Dict는 count dict만 허용 (nested dict 금지)
    """
    if not isinstance(raw, dict):
        return None

    out: dict = {}

    # 금지 키는 먼저 검증해 제거
    for bad_key in _AUDIT_SUMMARY_FORBIDDEN_KEYS:
        if bad_key in raw:
            # 금지 키가 있으면 전체 sanitize를 보수적으로 처리
            # (raw audit가 신뢰할 수 없을 가능성)
            pass

    # Integer count 필드 (non-negative)
    for key in ("audit_event_count", "blocked_event_count", "allowed_event_count",
                "denied_event_count", "error_event_count", "agent_reported_event_count",
                "dropped_event_count", "redacted_field_count", "audit_schema_version"):
        val = raw.get(key)
        if val is not None:
            try:
                count = max(0, int(val))
                out[key] = count
            except (TypeError, ValueError):
                pass

    # String enum 필드 (길이 제한, 자유 문자열 금지)
    for key in ("last_event_category", "last_event_status", "local_audit_source"):
        val = raw.get(key)
        if val is not None and isinstance(val, str):
            # 최대 80자 제한
            out[key] = str(val)[:80]

    # audit_event_categories — list[str] enum만 허용
    categories = raw.get("audit_event_categories")
    if isinstance(categories, list):
        safe_cats = []
        for cat in categories:
            if isinstance(cat, str):
                # 각 카테고리 최대 50자, 중복 제거
                cat_str = str(cat)[:50]
                if cat_str not in safe_cats:
                    safe_cats.append(cat_str)
        if safe_cats:
            out["audit_event_categories"] = safe_cats

    # Timestamp 문자열 필드 (ISO 형식, 길이 제한)
    for key in ("audit_window_started_at", "audit_window_ended_at", "audit_summary_generated_at"):
        val = raw.get(key)
        if val is not None and isinstance(val, str):
            # 최대 50자 (ISO 8601은 보통 ~25자)
            out[key] = str(val)[:50]

    # audit_summary_hash — digest만 허용, 원문 복구 불가능
    hash_val = raw.get("audit_summary_hash")
    if hash_val is not None and isinstance(hash_val, str):
        # 최대 128자 (SHA-256 hex는 64자)
        out["audit_summary_hash"] = str(hash_val)[:128]

    # Count dicts — key는 enum, value는 non-negative int
    for dict_key in ("policy_decision_counts", "target_kind_counts", "action_kind_counts"):
        dict_val = raw.get(dict_key)
        if isinstance(dict_val, dict):
            safe_dict = {}
            for k, v in dict_val.items():
                # key 최대 40자 (카테고리 이름)
                if not isinstance(k, str):
                    continue
                safe_k = str(k)[:40]
                try:
                    safe_v = max(0, int(v))
                    safe_dict[safe_k] = safe_v
                except (TypeError, ValueError):
                    pass
            if safe_dict:
                out[dict_key] = safe_dict

    return out if out else None


def _build_observe_summary(raw: Optional[dict]) -> Optional[dict]:
    """WS result에서 받은 raw observe_summary를 허용 필드만 추출/sanitize.

    금지 키(cookie/session/token/authorization/password/html 등)는 포함하지 않는다.
    final_url_sanitized는 반드시 재검증한다.
    """
    if not isinstance(raw, dict):
        return None

    out: dict = {}

    # String enum 필드 — 길이 제한
    for key in ("target_kind", "url_category", "status_category",
                "error_category", "blocked_reason"):
        val = raw.get(key)
        if val is not None:
            out[key] = str(val)[:80]

    # final_url_sanitized — 반드시 재검증 (orchestrator 방어)
    out["final_url_sanitized"] = _sanitize_final_url_value(
        raw.get("final_url_sanitized")
    )

    # title — 길이 제한
    title = str(raw.get("title") or "")[:300]
    out["title"] = title
    try:
        out["title_len"] = int(raw.get("title_len") or len(title))
    except (TypeError, ValueError):
        out["title_len"] = len(title)

    # Bool 필드
    for key in ("login_required_hint", "html_truncated", "browser_headless"):
        if key in raw:
            out[key] = bool(raw[key])

    # Integer 필드
    for key in ("pages_observed_count", "modal_candidates_count", "browser_keep_open_ms"):
        val = raw.get(key)
        if val is not None:
            try:
                out[key] = max(0, int(val))
            except (TypeError, ValueError):
                out[key] = 0

    # page_structure_counts — 카운트 요약만, 텍스트 내용 금지
    psc = raw.get("page_structure_counts")
    if isinstance(psc, dict):
        safe_counts: dict = {}
        for k in _PAGE_STRUCTURE_COUNT_KEYS:
            try:
                safe_counts[k] = max(0, int(psc.get(k) or 0))
            except (TypeError, ValueError):
                safe_counts[k] = 0
        out["page_structure_counts"] = safe_counts

    # observed_at — ISO 타임스탬프 문자열
    ts = raw.get("observed_at")
    if isinstance(ts, str) and ts:
        out["observed_at"] = ts[:40]

    # 금지 키 방어 삭제
    for bad_key in _OBSERVE_FORBIDDEN_KEYS:
        out.pop(bad_key, None)

    return out if out else None


# ── Cleanup (smoke-test residual 정리) ──────────────────────────────────

def get_agent_cleanup_preview(agent_id: str) -> dict:
    """cleanup 판정을 위한 preview 정보 반환.

    Response:
    {
        "agent_id": str,
        "eligible": bool,
        "reason": str,
        "task_count": int,
        "task_status_counts": {...}
    }
    """
    from .local_agent_cleanup_policy import validate_cleanup_request

    with _lock:
        agent = _agents.get(agent_id)
        if agent is None:
            return {
                "agent_id": agent_id,
                "eligible": False,
                "reason": "agent_not_found",
                "task_count": 0,
            }

        # agent의 모든 task 상태 수집
        agent_tasks = [t for t in _tasks.values() if t.agent_id == agent_id]
        task_statuses = [t.status for t in agent_tasks]

        # cleanup 정책 검증 (dry_run=true로 preview 수행)
        policy = validate_cleanup_request(
            agent_id=agent_id,
            host=agent.host,
            label="",  # registration code label은 registry에 없으므로 빈값
            agent_status=get_agent_status(agent_id),
            task_statuses=task_statuses,
            dry_run=True,
            force=False,
            confirm=None,
            smoke_test=agent.smoke_test,
        )

        return {
            "agent_id": agent_id,
            "eligible": policy.eligible,
            "reason": policy.reason,
            "task_count": policy.task_count,
            "task_status_counts": policy.task_status_counts or {},
        }


def cleanup_agent_and_tasks(
    agent_id: str,
    *,
    dry_run: bool = True,
    force: bool = False,
    confirm: str | None = None,
    actor: str = "",
) -> dict:
    """cleanup agent와 task 정리.

    Policy:
    - smoke-test agent만 cleanup 대상
    - offline agent만 cleanup 대상
    - pending/running task 있으면 거부
    - dry_run=true: preview만 반환, 실제 삭제 안 함
    - dry_run=false: force=true + confirm 정확 일치 필수

    Response:
    {
        "agent_id": str,
        "dry_run": bool,
        "eligible": bool,
        "reason": str,
        "status": "preview" | "cleaned" | "error",
        "deleted": bool,
        "task_count": int,
        "tasks_deleted": int (실제 cleanup일 때만)
    }
    """
    from .local_agent_cleanup_policy import validate_cleanup_request

    with _lock:
        agent = _agents.get(agent_id)
        if agent is None:
            return {
                "agent_id": agent_id,
                "dry_run": dry_run,
                "eligible": False,
                "reason": "agent_not_found",
                "status": "error",
                "deleted": False,
                "task_count": 0,
            }

        # agent의 모든 task 상태 수집
        agent_tasks = [t for t in _tasks.values() if t.agent_id == agent_id]
        task_statuses = [t.status for t in agent_tasks]

        # cleanup 정책 검증
        policy = validate_cleanup_request(
            agent_id=agent_id,
            host=agent.host,
            label="",
            agent_status=get_agent_status(agent_id),
            task_statuses=task_statuses,
            dry_run=dry_run,
            force=force,
            confirm=confirm,
            smoke_test=agent.smoke_test,
        )

        # dry_run이거나 ineligible이면 preview 반환
        if dry_run or not policy.eligible:
            return {
                "agent_id": agent_id,
                "dry_run": dry_run,
                "eligible": policy.eligible,
                "reason": policy.reason,
                "status": "preview" if policy.eligible else "error",
                "deleted": False,
                "task_count": policy.task_count,
                "task_status_counts": policy.task_status_counts or {},
            }

        # 실제 cleanup 수행 (dry_run=false + eligible)
        # agent와 task 제거
        del _agents[agent_id]
        tasks_deleted = 0
        for task_id in list(_tasks.keys()):
            if _tasks[task_id].agent_id == agent_id:
                del _tasks[task_id]
                tasks_deleted += 1

        return {
            "agent_id": agent_id,
            "dry_run": dry_run,
            "eligible": policy.eligible,
            "reason": policy.reason,
            "status": "cleaned",
            "deleted": True,
            "task_count": policy.task_count,
            "tasks_deleted": tasks_deleted,
        }


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
    "expire_stale_tasks",
    "fail_active_tasks_for_agent",
    "KNOWN_TASK_STATUSES",
    "list_tasks_for_agent",
    "set_agent_connected", "set_agent_last_seen", "set_agent_disconnected",
    "get_active_task_count", "get_current_task_id", "get_agent_status",
    "cancel_task", "CancelNotAllowedError",
    "get_agent_cleanup_preview", "cleanup_agent_and_tasks",
]

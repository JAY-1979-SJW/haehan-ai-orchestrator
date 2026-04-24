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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


# ── 액션 정의 ────────────────────────────────────────────────────────────

# 액션 → risk_level 매핑.
# 미등록 액션은 UNKNOWN_ACTION 으로 거절된다.
ACTION_RISK: dict[str, str] = {
    "ping":               "low",
    "system_info":        "low",
    "list_allowed_apps":  "low",
    "open_url":           "low",
    "list_files_readonly": "medium",
    "capture_screenshot": "high",
}

# 서버가 즉시 응답 가능한 액션 (PC 의존 없음)
_SERVER_AUTO_COMPLETE: frozenset[str] = frozenset({
    "ping", "system_info", "list_allowed_apps",
})

# 허용된 PC 측 앱 (실제 실행은 browser/open_url 만 가능)
ALLOWED_APPS: list[str] = ["browser", "excel", "hwp", "cad"]

# Stage 2: WebSocket 으로 PC 에이전트에 위임해 자동 실행 허용되는 액션.
# 이 집합에 포함된 액션만 delivered → running → completed 흐름을 탄다.
#
# Stage 3: capture_screenshot 포함 — 단, high risk 이므로 반드시 승인 후(mark_approved)
# 에만 waiting_approval → queued 로 전환되어 이 경로로 전달된다. 미승인 상태는
# list_pending_for_agent() 에서 제외되어 WS 에 push 되지 않는다.
AUTO_EXECUTE_VIA_AGENT: frozenset[str] = frozenset({
    "ping", "system_info", "list_allowed_apps",
    "open_url", "list_files_readonly",
    "capture_screenshot",
})


# params / result 에서 절대 저장·노출 금지인 키
_SENSITIVE_KEYS: frozenset[str] = frozenset({
    "password", "passwd", "pwd",
    "token", "access_token", "refresh_token", "session_token",
    "device_token", "cookie", "cookies", "session",
    "client_secret", "secret", "api_secret", "api_key",
    "auth", "authorization",
})


def _strip_sensitive(params: dict) -> dict:
    """민감 키를 제거한 새 dict 반환 (저장·로그용)."""
    if not params:
        return {}
    return {k: v for k, v in params.items() if k.lower() not in _SENSITIVE_KEYS}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── 데이터 모델 ──────────────────────────────────────────────────────────

@dataclass
class LocalAgent:
    agent_id: str
    host: str            # 사람이 식별 가능한 PC 이름 (예: "skyjw-desktop")
    os_name: str         # "Windows 11" 등 (개인정보 제외)
    version: str         # 에이전트 버전 (예: "0.1.0")
    registered_at: str
    requested_by: str    # 등록을 요청한 actor
    token_hash: str      # SHA-256(device_token) — 원문은 저장 금지

    def to_safe(self) -> dict:
        """API 응답용 (token_hash 제외)."""
        return {
            "agent_id": self.agent_id,
            "host": self.host,
            "os_name": self.os_name,
            "version": self.version,
            "registered_at": self.registered_at,
            "requested_by": self.requested_by,
        }


@dataclass
class LocalAgentTask:
    task_id: str
    agent_id: str
    action: str
    params: dict          # 민감 키 제거된 상태로만 저장
    risk_level: str
    # queued / delivered / running / waiting_approval / completed / failed / rejected
    status: str
    requested_by: str
    created_at: str
    updated_at: str
    token_id: str = ""    # high risk 일 때만 채워짐
    result_summary: str = ""
    # Stage 2 추가 필드
    delivered_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    error_summary: str = ""
    # Stage 3 추가 필드 — 승인 게이트 통과 흔적
    approved_at: str = ""
    approved_by: str = ""
    rejected_at: str = ""
    reject_reason: str = ""

    def to_safe(self) -> dict:
        return {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "action": self.action,
            "params": self.params,        # 이미 민감값 제거됨
            "risk_level": self.risk_level,
            "status": self.status,
            "requested_by": self.requested_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "token_id": self.token_id,
            "result_summary": self.result_summary,
            "delivered_at": self.delivered_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error_summary": self.error_summary,
            "approved_at": self.approved_at,
            "approved_by": self.approved_by,
            "rejected_at": self.rejected_at,
            "reject_reason": self.reject_reason,
        }

    def to_dispatch(self) -> dict:
        """WebSocket 전달용 페이로드 (민감 필드 제거 후).

        high risk 작업은 승인 후에만 queued → delivered 흐름을 타므로,
        dispatch 시점에 approved_at 이 반드시 세팅돼 있어야 한다.
        `approved: True` 플래그는 클라이언트가 high-risk 승인 분기를 구별하는
        용도 — 미승인 시 클라이언트는 NOT_IMPLEMENTED_STAGE2 로 즉시 거절한다.
        """
        approved_flag = bool(
            self.risk_level == "high" and self.approved_at
        )
        return {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "action": self.action,
            "params": self.params,
            "risk_level": self.risk_level,
            "approved": approved_flag,
        }


# ── 인메모리 저장소 ──────────────────────────────────────────────────────

_lock = threading.Lock()
_agents: dict[str, LocalAgent] = {}
_tasks: dict[str, LocalAgentTask] = {}


def clear() -> None:
    """테스트 전용: 메모리 저장소 초기화."""
    with _lock:
        _agents.clear()
        _tasks.clear()


# ── 등록 / 조회 ──────────────────────────────────────────────────────────

class RegisterResult:
    """register_agent 반환 컨테이너 (token 원문은 1회만 노출)."""
    __slots__ = ("agent", "device_token")

    def __init__(self, agent: LocalAgent, device_token: str):
        self.agent = agent
        self.device_token = device_token


def register_agent(
    *, host: str, os_name: str, version: str, requested_by: str,
) -> RegisterResult:
    """새 에이전트 등록. agent_id + device_token 발급, 서버는 토큰 해시만 저장.

    device_token 원문은 호출자(라우터) 가 응답에 1회만 노출하고 폐기한다.
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


def attach_token(task_id: str, token_id: str) -> None:
    """high risk 작업에 승인 토큰 ID 연결 (라우터에서 호출)."""
    with _lock:
        t = _tasks.get(task_id)
        if t is None:
            return
        t.token_id = token_id
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


# ── Stage 2 전달/결과 ───────────────────────────────────────────────────

def list_pending_for_agent(agent_id: str) -> list[LocalAgentTask]:
    """해당 에이전트의 status=queued 작업 (오래된 것부터)."""
    with _lock:
        out = [t for t in _tasks.values()
               if t.agent_id == agent_id and t.status == "queued"]
    out.sort(key=lambda t: t.created_at)
    return out


def mark_delivered(agent_id: str, task_id: str) -> Optional[LocalAgentTask]:
    """queued → delivered. 다른 상태 (completed / waiting_approval 등) 에서는 변경 없음."""
    with _lock:
        t = _tasks.get(task_id)
        if t is None or t.agent_id != agent_id:
            return None
        if t.status != "queued":
            return t
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
        if t.status not in ("delivered", "queued"):
            return t
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
) -> Optional[LocalAgentTask]:
    """에이전트가 보고한 결과 반영. running/delivered/queued 에서만 동작.

    - success=True  → status=completed
    - success=False → status=failed + error_summary
    """
    with _lock:
        t = _tasks.get(task_id)
        if t is None or t.agent_id != agent_id:
            return None
        if t.status in ("completed", "failed", "rejected", "waiting_approval"):
            # 이미 종결된 작업은 결과를 재적용하지 않는다 (idempotent).
            return t
        now = _now_iso()
        if success:
            t.status = "completed"
            t.result_summary = (summary or "")[:500]
            t.error_summary = ""
        else:
            t.status = "failed"
            # error_summary 는 민감값이 섞일 수 있어 짧게만 보존
            msg = (error_code + ": " + (error or summary or "")).strip(": ")
            t.error_summary = msg[:500]
            t.result_summary = (summary or "")[:500]
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
    return ""


__all__ = [
    "ACTION_RISK", "ALLOWED_APPS", "AUTO_EXECUTE_VIA_AGENT",
    "LocalAgent", "LocalAgentTask", "RegisterResult",
    "UnknownActionError",
    "register_agent", "get_agent", "list_agents", "authenticate_agent",
    "enqueue_task", "get_task", "attach_token", "clear",
    "list_pending_for_agent", "mark_delivered", "mark_running", "apply_result",
    "find_task_by_id", "find_task_by_token_id",
    "mark_approved", "mark_rejected", "mark_expired",
]

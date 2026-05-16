"""데스크 앱 작업 수신 모듈 (DESK-4).

서버의 pending task 큐를 조회하고, 실행 위치별로 분류하여
안전한 표시 데이터를 제공한다.

실행 금지:
- 실제 외부 사이트 접속 금지
- 실제 브라우저 실행 금지
- 실제 로그인/게시/제출 금지
- 비밀번호/OTP/쿠키/세션 접근 금지
- DB write 금지

역할:
- LOCAL_AGENT_REQUIRED 작업 → "수신 준비" 상태 표시
- USER_DIRECT_REQUIRED 작업 → "사용자 직접 조작 필요" 안내
- BLOCKED 작업 → "차단됨" 표시
- SERVER_INTERNAL_ONLY 작업 → "서버 처리 중" 표시

금지 필드 (절대 포함 안 됨):
  approval_token, token_hash, password, otp, cookie, session,
  authorization, device_token, typed_text, raw_screenshot, base64
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── 실행 위치 상수 ────────────────────────────────────────────────────────────

EXEC_LOC_SERVER_INTERNAL = "SERVER_INTERNAL_ONLY"
EXEC_LOC_LOCAL_AGENT = "LOCAL_AGENT_REQUIRED"
EXEC_LOC_USER_DIRECT = "USER_DIRECT_REQUIRED"
EXEC_LOC_BLOCKED = "BLOCKED"

# ── 작업 상태 상수 ────────────────────────────────────────────────────────────

TASK_STATUS_PENDING = "pending"
TASK_STATUS_RECEIVED = "received"
TASK_STATUS_WAITING_USER = "waiting_user"
TASK_STATUS_RUNNING_PREVIEW = "running_preview"
TASK_STATUS_COMPLETED = "completed"
TASK_STATUS_FAILED = "failed"
TASK_STATUS_BLOCKED = "blocked"
TASK_STATUS_EXPIRED = "expired"

# ── 안전 금지 필드 ────────────────────────────────────────────────────────────

_FORBIDDEN_FIELDS: frozenset[str] = frozenset({
    "approval_token", "final_approval_token", "token_hash",
    "typed_text", "password", "otp", "cookie", "session",
    "authorization", "device_token", "localstorage", "sessionstorage",
    "raw_screenshot", "base64", "npki", "private_key",
    "certificate_password", "access_token", "refresh_token",
})

# ── 허용 다음 액션 ────────────────────────────────────────────────────────────

_NEXT_ACTIONS_BY_LOC: dict[str, list[str]] = {
    EXEC_LOC_LOCAL_AGENT: ["수신 확인", "상세 보기"],
    EXEC_LOC_USER_DIRECT: ["사용자 직접 조작 안내 보기"],
    EXEC_LOC_BLOCKED:     ["차단 사유 보기"],
    EXEC_LOC_SERVER_INTERNAL: ["상태 조회"],
}

# 안전 표시 메시지
_SAFETY_NOTICE_BY_LOC: dict[str, str] = {
    EXEC_LOC_LOCAL_AGENT:
        "로컬 에이전트가 수신 대기 중입니다. 실행은 사용자 승인 후 진행됩니다.",
    EXEC_LOC_USER_DIRECT:
        "이 작업은 사용자가 직접 수행해야 합니다. 비서앱은 안내만 제공합니다.",
    EXEC_LOC_BLOCKED:
        "보안 정책에 의해 이 작업은 차단되었습니다. 실행할 수 없습니다.",
    EXEC_LOC_SERVER_INTERNAL:
        "서버에서 자동 처리 중인 작업입니다.",
}


@dataclass
class DesktopTask:
    """데스크 앱 표시용 작업 모델 — 민감 필드 없음."""
    task_id: str
    title: str
    provider: str
    action_type: str
    execution_location: str         # EXEC_LOC_* 상수
    risk_level: str                 # low / medium / high
    approval_required: bool
    user_direct_required: bool
    status: str                     # TASK_STATUS_* 상수
    requested_at: str
    expires_at: str
    summary: str
    safety_notice: str
    allowed_next_actions: list[str] = field(default_factory=list)

    def is_executable_by_agent(self) -> bool:
        """로컬 에이전트가 수신·실행 준비 가능한 작업인지."""
        return self.execution_location == EXEC_LOC_LOCAL_AGENT

    def is_user_direct_required(self) -> bool:
        """사용자 직접 조작이 필요한 작업인지."""
        return self.execution_location == EXEC_LOC_USER_DIRECT

    def is_blocked(self) -> bool:
        """차단된 작업인지."""
        return self.execution_location == EXEC_LOC_BLOCKED

    def to_safe_dict(self) -> dict:
        """안전 필드만 포함한 dict — 민감 필드 없음."""
        return {
            "task_id": self.task_id,
            "title": self.title,
            "provider": self.provider,
            "action_type": self.action_type,
            "execution_location": self.execution_location,
            "risk_level": self.risk_level,
            "approval_required": self.approval_required,
            "user_direct_required": self.user_direct_required,
            "status": self.status,
            "requested_at": self.requested_at,
            "expires_at": self.expires_at,
            "summary": self.summary,
            "safety_notice": self.safety_notice,
            "allowed_next_actions": self.allowed_next_actions,
        }


def _classify_execution_location(raw: dict) -> str:
    """raw task dict에서 실행 위치를 분류한다."""
    exec_mode = raw.get("execution_mode", "")
    exec_loc = raw.get("execution_location", "")
    action_type = raw.get("action_type", "")
    payload = raw.get("payload", {})
    payload_exec_loc = payload.get("execution_location", "") if isinstance(payload, dict) else ""

    # 명시적 blocked
    if any(v in ("BLOCKED", "QUARANTINE") for v in (exec_mode, exec_loc, payload_exec_loc)):
        return EXEC_LOC_BLOCKED

    # 사용자 직접 필요
    if any(v in ("USER_DIRECT_REQUIRED", "USER_DIRECT") for v in (exec_loc, payload_exec_loc)):
        return EXEC_LOC_USER_DIRECT
    if action_type in ("wait_for_user_auth", "user_submit", "user_sign"):
        return EXEC_LOC_USER_DIRECT

    # 로컬 에이전트 필요
    if any(v in ("LOCAL_PLAYWRIGHT", "LOCAL_AGENT", "LOCAL_AGENT_REQUIRED")
           for v in (exec_mode, exec_loc, payload_exec_loc)):
        return EXEC_LOC_LOCAL_AGENT

    # 서버 내부 처리
    if any(v in ("SERVER", "SERVER_INTERNAL_ONLY", "OFFICIAL_API")
           for v in (exec_loc, payload_exec_loc)):
        return EXEC_LOC_SERVER_INTERNAL

    # 기본: 서버 내부
    return EXEC_LOC_SERVER_INTERNAL


def _strip_forbidden(raw: dict) -> dict:
    """민감 필드를 제거한 안전한 dict를 반환한다."""
    return {
        k: v for k, v in raw.items()
        if k.lower() not in _FORBIDDEN_FIELDS
    }


def classify_raw_task(raw: dict) -> DesktopTask:
    """raw task dict → DesktopTask 변환.

    raw 에 민감 필드가 있어도 안전 필드만 추출한다.
    실행을 수행하지 않는다.
    """
    safe = _strip_forbidden(raw)
    payload = safe.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}

    task_id = safe.get("task_id") or payload.get("task_id", "unknown")
    action_type = safe.get("action_type") or payload.get("action", "")
    provider = safe.get("domain") or payload.get("domain", safe.get("provider", ""))
    exec_loc = _classify_execution_location(raw)  # raw 전체로 분류 (필드 제거 전)
    risk_level = safe.get("risk_level") or payload.get("risk_level", "medium")
    requires_approval = bool(safe.get("requires_approval", exec_loc != EXEC_LOC_SERVER_INTERNAL))
    user_direct = exec_loc == EXEC_LOC_USER_DIRECT

    # 타임스탬프
    now_iso = datetime.now(timezone.utc).isoformat()
    requested_at = safe.get("requested_at") or safe.get("created_at", now_iso)
    expires_at = safe.get("expires_at", "")

    # 제목
    description = payload.get("description") or safe.get("description", "")
    title = description[:80] if description else f"{provider}/{action_type}"

    # 요약
    target_url = payload.get("target_url", "")
    summary_parts = []
    if provider:
        summary_parts.append(f"provider={provider}")
    if action_type:
        summary_parts.append(f"action={action_type}")
    if target_url:
        # URL은 도메인만 표시 (경로 불포함)
        try:
            from urllib.parse import urlparse
            parsed = urlparse(target_url)
            summary_parts.append(f"target={parsed.netloc or target_url[:40]}")
        except Exception:
            pass
    summary = " | ".join(summary_parts)[:120]

    # 현재 상태
    raw_state = safe.get("state", safe.get("status", ""))
    if exec_loc == EXEC_LOC_BLOCKED:
        status = TASK_STATUS_BLOCKED
    elif raw_state in ("PENDING", "pending", ""):
        status = TASK_STATUS_PENDING
    elif raw_state in ("ASSIGNED", "received"):
        status = TASK_STATUS_RECEIVED
    elif raw_state in ("COMPLETED", "completed"):
        status = TASK_STATUS_COMPLETED
    elif raw_state in ("FAILED", "failed"):
        status = TASK_STATUS_FAILED
    elif raw_state in ("WAITING_USER_AUTH", "waiting_user"):
        status = TASK_STATUS_WAITING_USER
    else:
        status = TASK_STATUS_PENDING

    return DesktopTask(
        task_id=task_id,
        title=title,
        provider=provider,
        action_type=action_type,
        execution_location=exec_loc,
        risk_level=risk_level,
        approval_required=requires_approval,
        user_direct_required=user_direct,
        status=status,
        requested_at=requested_at,
        expires_at=expires_at,
        summary=summary,
        safety_notice=_SAFETY_NOTICE_BY_LOC.get(exec_loc, ""),
        allowed_next_actions=_NEXT_ACTIONS_BY_LOC.get(exec_loc, []),
    )


@dataclass
class TaskQueueStatus:
    """작업 큐 요약 상태 — 안전 표시용."""
    total_pending: int = 0
    local_agent_count: int = 0
    user_direct_count: int = 0
    blocked_count: int = 0
    server_internal_count: int = 0
    tasks: list[DesktopTask] = field(default_factory=list)

    def to_tray_label(self) -> str:
        """tray 메뉴에 표시할 요약 문자열."""
        if self.total_pending == 0:
            return "수신 작업: 없음"
        parts = []
        if self.local_agent_count:
            parts.append(f"에이전트 {self.local_agent_count}건")
        if self.user_direct_count:
            parts.append(f"직접 조작 {self.user_direct_count}건")
        if self.blocked_count:
            parts.append(f"차단 {self.blocked_count}건")
        return f"수신 작업: {', '.join(parts)}" if parts else f"수신 작업: {self.total_pending}건"


def poll_pending_tasks(source: str = "local") -> TaskQueueStatus:
    """pending task 큐를 조회하고 분류한다.

    source="local"  → in-memory task_queue_schema 사용 (서버 미연결 시)
    source="server" → ops_router /ops/approvals HTTP 호출 (서버 연결 시)

    실행을 수행하지 않는다. 분류만 한다.
    """
    raw_tasks: list[dict] = []

    if source == "local":
        try:
            from ai_orchestrator.server.task_queue_schema import get_pending_tasks
            raw_tasks = get_pending_tasks(limit=50)
        except ImportError:
            logger.debug("task_queue_schema 미설치 — 빈 큐 반환")
        except Exception as e:
            logger.warning("local task queue 조회 실패: %s", e)

    elif source == "server":
        try:
            import urllib.request
            import json as _json
            req = urllib.request.Request(
                "http://localhost:8000/api/v1/ops/approvals",
                headers={"Authorization": "Bearer admin-token"},
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = _json.loads(resp.read().decode())
            raw_tasks = data.get("items", [])
        except Exception as e:
            logger.debug("server ops/approvals 조회 실패 (fallback to empty): %s", e)

    tasks = [classify_raw_task(r) for r in raw_tasks]

    return TaskQueueStatus(
        total_pending=len(tasks),
        local_agent_count=sum(1 for t in tasks if t.is_executable_by_agent()),
        user_direct_count=sum(1 for t in tasks if t.is_user_direct_required()),
        blocked_count=sum(1 for t in tasks if t.is_blocked()),
        server_internal_count=sum(
            1 for t in tasks
            if t.execution_location == EXEC_LOC_SERVER_INTERNAL
        ),
        tasks=tasks,
    )


def validate_no_secret_in_task(task: DesktopTask) -> list[str]:
    """DesktopTask 안전 검증 — 금지 필드 포함 여부 확인.

    반환: 위반 필드 목록 (빈 리스트면 안전)
    """
    d = task.to_safe_dict()
    violations = []
    for key, val in d.items():
        key_lower = key.lower()
        if key_lower in _FORBIDDEN_FIELDS:
            violations.append(key)
        if isinstance(val, str):
            val_lower = val.lower()
            for forbidden in _FORBIDDEN_FIELDS:
                # 값이 금지 키 자체인 경우만 — 단어 포함은 허용 (URL 등)
                if val_lower == forbidden:
                    violations.append(f"{key}={val}")
    return violations


__all__ = [
    "DesktopTask",
    "TaskQueueStatus",
    "classify_raw_task",
    "poll_pending_tasks",
    "validate_no_secret_in_task",
    "EXEC_LOC_LOCAL_AGENT",
    "EXEC_LOC_USER_DIRECT",
    "EXEC_LOC_BLOCKED",
    "EXEC_LOC_SERVER_INTERNAL",
    "TASK_STATUS_PENDING",
    "TASK_STATUS_RECEIVED",
    "TASK_STATUS_WAITING_USER",
    "TASK_STATUS_BLOCKED",
    "TASK_STATUS_COMPLETED",
    "TASK_STATUS_FAILED",
    "TASK_STATUS_EXPIRED",
    "_FORBIDDEN_FIELDS",
]

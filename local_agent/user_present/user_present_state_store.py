"""
로컬 Agent 사용자 직접 인증 상태 store

in-memory 기반 단순 store.
운영 DB write 없음.
민감정보(password/otp/token/cookie/session)는 저장 전 제거.
safe_to_execute는 항상 False.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

# ── 상태 enum ────────────────────────────────────────────────────────────────

STATE_IDLE = "IDLE"
STATE_TASK_RECEIVED = "TASK_RECEIVED"
STATE_OPENING_BROWSER = "OPENING_BROWSER"
STATE_READONLY_CHECKING = "READONLY_CHECKING"
STATE_WAITING_FOR_USER = "WAITING_FOR_USER"
STATE_USER_CONFIRMED = "USER_CONFIRMED"
STATE_CANCELLED = "CANCELLED"
STATE_BLOCKED = "BLOCKED"
STATE_FAILED = "FAILED"
# APPROVAL_REQUIRED: 정책상 사람 승인이 추가로 필요한 placeholder 상태.
# 본 공정에서는 전이 로직 미구현 — store 정의와 검증만 추가하여 기존
# user_present_task/approval 토큰 흐름과 충돌하지 않도록 한다.
STATE_APPROVAL_REQUIRED = "APPROVAL_REQUIRED"

# FINAL 상태: 이후 USER_CONFIRMED 전이 불가
_FINAL_STATES: frozenset[str] = frozenset({
    STATE_USER_CONFIRMED,
    STATE_CANCELLED,
    STATE_BLOCKED,
    STATE_FAILED,
})

# USER_CONFIRMED 전이 가능한 상태
_CONFIRMABLE_STATES: frozenset[str] = frozenset({
    STATE_WAITING_FOR_USER,
})

# CANCELLED 전이 가능한 상태
_CANCELLABLE_STATES: frozenset[str] = frozenset({
    STATE_WAITING_FOR_USER,
    STATE_READONLY_CHECKING,
    STATE_OPENING_BROWSER,
    STATE_TASK_RECEIVED,
    STATE_BLOCKED,
    STATE_FAILED,
})

# ── 사용자 화면 노출 금지 필드 ───────────────────────────────────────────────

_USER_FORBIDDEN_KEYS: frozenset[str] = frozenset({
    "password", "otp", "certificate_password", "financial_certificate_password",
    "token", "access_token", "refresh_token", "api_key", "device_token",
    "cookie", "session", "localStorage", "sessionStorage",
    "secret", "raw_audit", "audit_raw", "internal_policy", "full_policy",
    "cross_tenant_data", "other_user_tasks", "other_tenant_data",
    "server_path", "system_trace", "raw_validation_errors",
    "action_metadata", "detailed_audit_event", "raw_audit_log",
})

# 관리자 화면에도 raw sensitive는 노출 금지
_ADMIN_FORBIDDEN_KEYS: frozenset[str] = frozenset({
    "password", "otp", "certificate_password", "financial_certificate_password",
    "token", "access_token", "refresh_token", "api_key", "device_token",
    "cookie", "session", "localStorage", "sessionStorage",
    "secret", "raw_audit_log",
})

# 저장 금지 필드 (store 진입 전 제거)
_STORE_FORBIDDEN_KEYS: frozenset[str] = _USER_FORBIDDEN_KEYS


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class UserPresentStateStore:
    """thread-safe in-memory user-present 상태 store."""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create_user_present_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        """새 user-present 작업을 생성한다. 민감 필드는 저장 전 제거."""
        clean = {k: v for k, v in payload.items() if k not in _STORE_FORBIDDEN_KEYS}
        workflow_run_id = clean.get("workflow_run_id") or f"wf_run_{_now_iso()}"
        task: dict[str, Any] = {
            **clean,
            "workflow_run_id": workflow_run_id,
            "state": STATE_TASK_RECEIVED,
            "safe_to_execute": False,
            "safe_to_dispatch": False,
            "audit_required": True,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "confirmed_at": None,
            "cancelled_at": None,
        }
        with self._lock:
            self._store[workflow_run_id] = task
        return dict(task)

    def get_user_present_task(self, workflow_run_id: str) -> dict[str, Any] | None:
        with self._lock:
            task = self._store.get(workflow_run_id)
        return dict(task) if task else None

    def list_user_present_tasks(self, user_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            tasks = list(self._store.values())
        if user_id is not None:
            tasks = [t for t in tasks if t.get("user_id") == user_id]
        return [dict(t) for t in tasks]

    def _update_state(self, workflow_run_id: str, new_state: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            task = self._store.get(workflow_run_id)
            if task is None:
                raise KeyError(f"task not found: {workflow_run_id}")
            task = dict(task)
            task["state"] = new_state
            task["updated_at"] = _now_iso()
            task["safe_to_execute"] = False
            if extra:
                task.update(extra)
            self._store[workflow_run_id] = task
        return dict(task)

    def mark_waiting_for_user(self, workflow_run_id: str) -> dict[str, Any]:
        return self._update_state(workflow_run_id, STATE_WAITING_FOR_USER)

    def _transition(
        self, workflow_run_id: str, allowed: Any, target: str, stamp_key: str, error_detail: str
    ) -> dict[str, Any]:
        """상태 전이(mark_user_confirmed/cancelled 공통): 없으면 KeyError, 허용 상태가 아니면 ValueError."""
        task = self.get_user_present_task(workflow_run_id)
        if task is None:
            raise KeyError(f"task not found: {workflow_run_id}")
        if task["state"] not in allowed:
            raise ValueError(f"상태 전이 불가: {task['state']} → {error_detail}")
        return self._update_state(workflow_run_id, target, {stamp_key: _now_iso()})

    def mark_user_confirmed(self, workflow_run_id: str) -> dict[str, Any]:
        return self._transition(
            workflow_run_id,
            _CONFIRMABLE_STATES,
            STATE_USER_CONFIRMED,
            "confirmed_at",
            "USER_CONFIRMED. WAITING_FOR_USER 상태일 때만 가능합니다.",
        )

    def mark_user_cancelled(self, workflow_run_id: str) -> dict[str, Any]:
        return self._transition(workflow_run_id, _CANCELLABLE_STATES, STATE_CANCELLED, "cancelled_at", "CANCELLED.")

    def sanitize_user_present_task_for_user(self, task: dict[str, Any]) -> dict[str, Any]:
        """사용자 화면에 표시할 수 있는 필드만 반환한다."""
        return {k: v for k, v in task.items() if k not in _USER_FORBIDDEN_KEYS}

    def sanitize_user_present_task_for_admin(self, task: dict[str, Any]) -> dict[str, Any]:
        """관리자 화면에 표시할 수 있는 필드만 반환한다."""
        return {k: v for k, v in task.items() if k not in _ADMIN_FORBIDDEN_KEYS}

    def clear(self) -> None:
        """테스트 전용: store 초기화."""
        with self._lock:
            self._store.clear()


def validate_user_present_task(task: dict[str, Any]) -> list[str]:
    """작업 dict의 필수 필드와 정책 준수를 검증한다."""
    errors: list[str] = []
    required = ["workflow_run_id", "state", "safe_to_execute", "safe_to_dispatch", "audit_required", "created_at"]
    for field in required:
        if field not in task:
            errors.append(f"필수 필드 누락: {field}")

    if task.get("safe_to_execute") is not False:
        errors.append("safe_to_execute는 항상 False여야 한다")

    if task.get("state") not in {
        STATE_IDLE, STATE_TASK_RECEIVED, STATE_OPENING_BROWSER,
        STATE_READONLY_CHECKING, STATE_WAITING_FOR_USER,
        STATE_USER_CONFIRMED, STATE_CANCELLED, STATE_BLOCKED, STATE_FAILED,
        STATE_APPROVAL_REQUIRED,
    }:
        errors.append(f"유효하지 않은 state: {task.get('state')}")

    for forbidden in _USER_FORBIDDEN_KEYS:
        if forbidden in task:
            errors.append(f"task에 민감 필드 포함됨: {forbidden}")

    return errors


# ── 모듈 레벨 기본 store 인스턴스 ────────────────────────────────────────────

default_store = UserPresentStateStore()


def create_user_present_task(payload: dict[str, Any]) -> dict[str, Any]:
    return default_store.create_user_present_task(payload)


def get_user_present_task(workflow_run_id: str) -> dict[str, Any] | None:
    return default_store.get_user_present_task(workflow_run_id)


def list_user_present_tasks(user_id: str | None = None) -> list[dict[str, Any]]:
    return default_store.list_user_present_tasks(user_id)


def mark_waiting_for_user(workflow_run_id: str) -> dict[str, Any]:
    return default_store.mark_waiting_for_user(workflow_run_id)


def mark_user_confirmed(workflow_run_id: str) -> dict[str, Any]:
    return default_store.mark_user_confirmed(workflow_run_id)


def mark_user_cancelled(workflow_run_id: str) -> dict[str, Any]:
    return default_store.mark_user_cancelled(workflow_run_id)


def sanitize_user_present_task_for_user(task: dict[str, Any]) -> dict[str, Any]:
    return default_store.sanitize_user_present_task_for_user(task)


def sanitize_user_present_task_for_admin(task: dict[str, Any]) -> dict[str, Any]:
    return default_store.sanitize_user_present_task_for_admin(task)

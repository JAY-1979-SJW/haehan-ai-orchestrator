"""
서버 로컬 에이전트 task queue 스키마

DB schema 변경 없음.
in-memory contract adapter 수준으로 구현.
기존 _up_task_queue 구조와 충돌하지 않는 별도 namespace.

서버 역할:
- task_id 생성
- safe payload 생성
- 로컬 에이전트가 가져갈 작업 큐 제공
- 로컬 결과 수신
- 민감값 차단 검증

서버 금지:
- 외부 사이트 브라우저 접속
- Playwright 직접 실행
- cookie/session/password 저장
- 인증정보 저장
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any

# ── task_state 상수 ────────────────────────────────────────────────────────────

TASK_STATE_PENDING = "PENDING"
TASK_STATE_ASSIGNED = "ASSIGNED"
TASK_STATE_COMPLETED = "COMPLETED"
TASK_STATE_FAILED = "FAILED"
TASK_STATE_BLOCKED = "BLOCKED"

_ALL_STATES: frozenset[str] = frozenset({
    TASK_STATE_PENDING, TASK_STATE_ASSIGNED,
    TASK_STATE_COMPLETED, TASK_STATE_FAILED, TASK_STATE_BLOCKED,
})

# ── 금지 필드 ──────────────────────────────────────────────────────────────────

_FORBIDDEN_FIELDS: frozenset[str] = frozenset({
    "cookie", "cookies", "session", "Authorization", "password", "otp",
    "certificate_password", "certificate_file_path", "localStorage",
    "sessionStorage", "token", "access_token", "refresh_token",
    "npki", "private_key", "auth_header",
})

# ── in-memory task store ───────────────────────────────────────────────────────

_task_store: dict[str, dict[str, Any]] = {}
_store_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    """민감 필드를 제거하고 안전한 payload를 반환한다."""
    return {k: v for k, v in payload.items() if k not in _FORBIDDEN_FIELDS}


def create_task_record(task_payload: dict[str, Any]) -> dict[str, Any]:
    """
    task record를 생성하고 in-memory store에 저장한다.
    민감 필드는 제거된다.
    """
    safe = _sanitize(task_payload)
    task_id = safe.get("task_id") or str(uuid.uuid4())
    safe["task_id"] = task_id

    record = {
        "task_id": task_id,
        "state": TASK_STATE_PENDING,
        "created_at": _now_iso(),
        "assigned_at": None,
        "completed_at": None,
        "payload": safe,
        "result": None,
    }

    with _store_lock:
        _task_store[task_id] = record

    return dict(record)


def get_pending_tasks(limit: int = 10) -> list[dict[str, Any]]:
    """PENDING 상태 task 목록을 반환한다."""
    with _store_lock:
        tasks = [
            dict(r) for r in _task_store.values()
            if r["state"] == TASK_STATE_PENDING
        ]
    return tasks[:limit]


def get_task(task_id: str) -> dict[str, Any] | None:
    """task_id로 record를 조회한다."""
    with _store_lock:
        record = _task_store.get(task_id)
    return dict(record) if record else None


def mark_assigned(task_id: str) -> bool:
    """task를 ASSIGNED 상태로 변경한다."""
    with _store_lock:
        record = _task_store.get(task_id)
        if not record or record["state"] != TASK_STATE_PENDING:
            return False
        record["state"] = TASK_STATE_ASSIGNED
        record["assigned_at"] = _now_iso()
    return True


def mark_completed(task_id: str, result: dict[str, Any]) -> bool:
    """task를 COMPLETED 상태로 변경하고 result를 저장한다."""
    safe_result = _sanitize(result)
    with _store_lock:
        record = _task_store.get(task_id)
        if not record:
            return False
        record["state"] = TASK_STATE_COMPLETED
        record["completed_at"] = _now_iso()
        record["result"] = safe_result
    return True


def mark_failed(task_id: str, reason: str = "") -> bool:
    """task를 FAILED 상태로 변경한다."""
    with _store_lock:
        record = _task_store.get(task_id)
        if not record:
            return False
        record["state"] = TASK_STATE_FAILED
        record["completed_at"] = _now_iso()
        record["result"] = {"error": reason}
    return True


def validate_no_sensitive_fields(payload: dict[str, Any]) -> list[str]:
    """payload에 민감 필드가 없는지 검증한다. 위반 목록 반환."""
    return [f"금지 필드 포함: {k!r}" for k in payload if k in _FORBIDDEN_FIELDS]


def clear_store() -> None:
    """테스트용: in-memory store를 초기화한다."""
    with _store_lock:
        _task_store.clear()

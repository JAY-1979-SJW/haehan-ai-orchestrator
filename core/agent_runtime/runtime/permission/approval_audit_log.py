"""
권한 실행 audit log

권한 기반 실행의 사전·사후를 기록한다.
민감값(비밀번호/OTP/cookie/session/token)은 기록하지 않는다.
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any

_lock = threading.Lock()
_log: list[dict[str, Any]] = []

# ── 이벤트 타입 ────────────────────────────────────────────────────────────────

EVENT_PERMISSION_GRANTED = "PERMISSION_GRANTED"
EVENT_PERMISSION_REVOKED = "PERMISSION_REVOKED"
EVENT_EXECUTION_STARTED = "EXECUTION_STARTED"
EVENT_EXECUTION_COMPLETED = "EXECUTION_COMPLETED"
EVENT_EXECUTION_BLOCKED = "EXECUTION_BLOCKED"
EVENT_PERMISSION_EXPIRED = "PERMISSION_EXPIRED"
EVENT_PERMISSION_EXHAUSTED = "PERMISSION_EXHAUSTED"
EVENT_SCOPE_EXCEEDED = "SCOPE_EXCEEDED"


def _entry(event: str, **kwargs) -> dict[str, Any]:
    return {
        "log_id": str(uuid.uuid4()),
        "event": event,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        **{k: v for k, v in kwargs.items()},
    }


def log_permission_granted(permission_id: str, action: str, domain: str,
                            account: str = "", max_executions: int = 1,
                            granted_by: str = "user") -> dict[str, Any]:
    e = _entry(EVENT_PERMISSION_GRANTED,
               permission_id=permission_id, action=action, domain=domain,
               account=account, max_executions=max_executions, granted_by=granted_by)
    with _lock:
        _log.append(e)
    return e


def log_permission_revoked(permission_id: str, action: str, domain: str) -> dict[str, Any]:
    e = _entry(EVENT_PERMISSION_REVOKED,
               permission_id=permission_id, action=action, domain=domain)
    with _lock:
        _log.append(e)
    return e


def log_execution_started(permission_id: str, action: str, domain: str,
                           task_id: str = "", content_preview: str = "") -> dict[str, Any]:
    e = _entry(EVENT_EXECUTION_STARTED,
               permission_id=permission_id, action=action, domain=domain,
               task_id=task_id, content_preview=content_preview[:200])
    with _lock:
        _log.append(e)
    return e


def log_execution_completed(permission_id: str, action: str, domain: str,
                             task_id: str = "", ok: bool = True) -> dict[str, Any]:
    e = _entry(EVENT_EXECUTION_COMPLETED,
               permission_id=permission_id, action=action, domain=domain,
               task_id=task_id, ok=ok)
    with _lock:
        _log.append(e)
    return e


def log_execution_blocked(action: str, domain: str, reason: str,
                           permission_id: str = "", task_id: str = "") -> dict[str, Any]:
    e = _entry(EVENT_EXECUTION_BLOCKED,
               action=action, domain=domain, reason=reason,
               permission_id=permission_id, task_id=task_id)
    with _lock:
        _log.append(e)
    return e


def get_log(limit: int = 100) -> list[dict[str, Any]]:
    with _lock:
        return list(_log[-limit:])


def get_log_for_permission(permission_id: str) -> list[dict[str, Any]]:
    with _lock:
        return [e for e in _log if e.get("permission_id") == permission_id]


def clear_log() -> None:
    """테스트용 초기화."""
    with _lock:
        _log.clear()


def has_sensitive_data(entry: dict[str, Any]) -> bool:
    """log entry에 민감값이 없는지 검사 (True면 오염)."""
    forbidden = {"password", "otp", "cookie", "session", "token",
                 "cert_password", "npki", "auth_header"}
    return any(k in entry for k in forbidden)

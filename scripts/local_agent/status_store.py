"""Local Agent 상태 파일 읽기/쓰기.

data/local_agent/status.json에 실행 상태를 기록한다.
secret/session/cookie/token/password 값 절대 기록 금지.
"""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone
from typing import Any, Optional

_STATUS_DIR  = pathlib.Path("data/local_agent")
_STATUS_FILE = _STATUS_DIR / "status.json"
_LOCK_FILE   = _STATUS_DIR / "agent.lock"

# 기록 금지 키 목록
_FORBIDDEN_KEYS = frozenset({
    "password", "passwd", "pw",
    "session", "cookie", "token",
    "access_token", "refresh_token",
    "otp", "cert_password",
})


def _ensure_dir() -> None:
    _STATUS_DIR.mkdir(parents=True, exist_ok=True)


def _sanitize(data: dict[str, Any]) -> dict[str, Any]:
    """기록 금지 키 제거."""
    return {k: v for k, v in data.items() if k.lower() not in _FORBIDDEN_KEYS}


# ── 상태 파일 ──────────────────────────────────────────────────────────

def write_status(
    running: bool,
    task_id: str = "",
    domain: str = "",
    action: str = "",
    approved_scope: Optional[list[str]] = None,
    idle_timeout_s: int = 1800,
    reason: str = "",
    extra: Optional[dict[str, Any]] = None,
) -> None:
    _ensure_dir()
    payload: dict[str, Any] = {
        "running":        running,
        "task_id":        task_id,
        "domain":         domain,
        "action":         action,
        "approved_scope": approved_scope or [],
        "idle_timeout_s": idle_timeout_s,
        "updated_at":     datetime.now(timezone.utc).isoformat(),
    }
    if reason:
        payload["stop_reason"] = reason
    if extra:
        payload.update(_sanitize(extra))
    _STATUS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_status() -> dict[str, Any]:
    if not _STATUS_FILE.exists():
        return {"running": False}
    try:
        data = json.loads(_STATUS_FILE.read_text(encoding="utf-8"))
        return _sanitize(data)
    except Exception:
        return {"running": False, "error": "status file unreadable"}


# ── lock 파일 ──────────────────────────────────────────────────────────

def acquire_lock(task_id: str) -> bool:
    """Lock 획득. 이미 lock 존재 시 False 반환."""
    _ensure_dir()
    if _LOCK_FILE.exists():
        return False
    _LOCK_FILE.write_text(task_id, encoding="utf-8")
    return True


def release_lock() -> None:
    if _LOCK_FILE.exists():
        _LOCK_FILE.unlink()


def lock_exists() -> bool:
    return _LOCK_FILE.exists()


def lock_task_id() -> str:
    if not _LOCK_FILE.exists():
        return ""
    try:
        return _LOCK_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return ""

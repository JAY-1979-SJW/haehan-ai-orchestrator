"""L7 Persistence — 인증 이벤트 감사 로그 (JSONL, append-only).

비밀번호·토큰·JWT 는 절대 기록하지 않으며 이메일은 마스킹한다.
기록 실패는 삼켜서 로그인 흐름을 깨지 않는다.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path

from ai_orchestrator.paths.runtime import storage_dir

_log = logging.getLogger(__name__)
_LOCK = threading.Lock()
_AUDIT_PATH = storage_dir() / "auth_audit.jsonl"


def _get_audit_path() -> Path:
    return _AUDIT_PATH


def mask_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None if not email else "***"
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


def record_auth_event(
    event: str,
    outcome: str,
    actor_id: str | None = None,
    email: str | None = None,
    **extra: str | int | None,
) -> None:
    """인증 이벤트 1줄 기록. 예외는 전파하지 않는다."""
    try:
        row: dict[str, str | int | None] = {
            "ts": datetime.now(UTC).isoformat(),
            "event": event,
            "outcome": outcome,
            "actor_id": actor_id,
            "email": mask_email(email),
        }
        for k, v in extra.items():
            if k.lower() in {"password", "token", "jwt", "secret"}:
                continue
            row[k] = v
        path = _get_audit_path()
        with _LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 - 감사 기록 실패가 로그인·가입 흐름을 깨면 안 되어 실패 격리(경고 로그)
        _log.warning("auth audit write failed", exc_info=False)

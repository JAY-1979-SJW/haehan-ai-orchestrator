"""Local audit logging for the PC-side local agent.

Raw secrets are stripped before writing. Raw local audit files remain PC-local;
the server receives only safe summaries through task results.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.agent_runtime.common import config

logger = logging.getLogger(__name__)


_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "token",
        "access_token",
        "refresh_token",
        "session_token",
        "device_token",
        "cookie",
        "cookies",
        "session",
        "client_secret",
        "secret",
        "api_secret",
        "api_key",
        "auth",
        "authorization",
    }
)


def _strip_sensitive(d: Any) -> Any:
    if isinstance(d, dict):
        return {k: _strip_sensitive(v) for k, v in d.items() if k.lower() not in _SENSITIVE_KEYS}
    if isinstance(d, list):
        return [_strip_sensitive(x) for x in d]
    return d


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _fallback_audit_paths() -> list[Path]:
    paths: list[Path] = []
    env_path = os.getenv("HAEHAN_AGENT_AUDIT_FALLBACK", "").strip()
    if env_path:
        paths.append(Path(env_path))
    paths.append(Path.cwd() / "logs" / "local_agent_audit.jsonl")
    paths.append(Path(tempfile.gettempdir()) / "haehan_agent" / "audit.jsonl")
    return paths


def _append_jsonl(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def log_local_event(event_type: str, **fields: Any) -> bool:
    """Append one safe local audit event.

    Returns True when the primary audit path was written. If the primary path
    fails, returns False after writing a failure marker and the original event
    to the first writable fallback path. If every path fails, returns False and
    emits a process log error.
    """
    safe_fields = _strip_sensitive(fields)
    entry: dict[str, Any] = {
        "timestamp": _now_iso(),
        "event_type": event_type,
        **safe_fields,
    }
    path: Path = config.LOCAL_AUDIT_PATH
    try:
        _append_jsonl(path, entry)
        return True
    except OSError as e:
        failure_entry = {
            "timestamp": _now_iso(),
            "event_type": "local_audit_write_failed",
            "error_code": e.__class__.__name__,
            "original_event_type": event_type,
        }
        fallback_entry = {
            **entry,
            "audit_write_fallback": True,
            "primary_audit_error_code": e.__class__.__name__,
        }
        for fallback in _fallback_audit_paths():
            if fallback == path:
                continue
            try:
                _append_jsonl(fallback, failure_entry)
                _append_jsonl(fallback, fallback_entry)
                logger.error(
                    "local audit primary write failed; wrote fallback audit: %s",
                    e,
                )
                return False
            except OSError:
                continue
        logger.error("local audit write failed on all paths: %s | entry=%s", e, entry)
        return False


__all__ = ["log_local_event"]

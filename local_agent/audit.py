"""로컬 감사 로그 (PC 보관, 서버에는 요약만 보고).

토큰 / 패스워드 / 쿠키 등 민감 키는 _strip_sensitive() 로 제거 후 기록.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config

logger = logging.getLogger(__name__)


_SENSITIVE_KEYS: frozenset[str] = frozenset({
    "password", "passwd", "pwd",
    "token", "access_token", "refresh_token", "session_token",
    "device_token", "cookie", "cookies", "session",
    "client_secret", "secret", "api_secret", "api_key",
    "auth", "authorization",
})


def _strip_sensitive(d: Any) -> Any:
    if isinstance(d, dict):
        return {k: _strip_sensitive(v) for k, v in d.items()
                if k.lower() not in _SENSITIVE_KEYS}
    if isinstance(d, list):
        return [_strip_sensitive(x) for x in d]
    return d


def log_local_event(event_type: str, **fields: Any) -> None:
    """로컬 감사 로그에 한 줄 추가. 민감값은 자동 제거."""
    safe_fields = _strip_sensitive(fields)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        **safe_fields,
    }
    path: Path = config.LOCAL_AUDIT_PATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.error("로컬 감사 로그 기록 실패: %s | entry=%s", e, entry)


__all__ = ["log_local_event"]

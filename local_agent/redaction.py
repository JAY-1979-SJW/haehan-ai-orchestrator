"""Sensitive value redaction for desktop agent logs / errors / CLI output.

비밀 키는 어떤 코드 경로에서도 평문으로 출력되지 않아야 한다.
이 모듈은 dict / mapping / 문자열에 대해 정해진 키 집합을 마스킹한다.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "device_token",
        "registration_code",
        "authorization",
        "password",
        "password_hash",
        "token_hash",
        "code_hash",
        "code_salt",
        "salt",
    }
)

_MASK = "***REDACTED***"


def _is_sensitive(key: str) -> bool:
    return key.lower() in SENSITIVE_KEYS


def redact(value: Any) -> Any:
    """Return a deep copy with sensitive values replaced by a fixed mask."""
    if isinstance(value, Mapping):
        return {k: (_MASK if _is_sensitive(str(k)) else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact(v) for v in value)
    return value


def safe_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a small allow-listed summary safe for logs.

    예: register-with-code 응답 → {"agent_id":"la-...","code_id":"rc-...","host":"..."}
    device_token / registration_code 등은 절대 포함되지 않는다.
    """
    allow = {
        "agent_id",
        "code_id",
        "label",
        "host",
        "os_name",
        "version",
        "registered_at",
        "created_at",
        "expires_at",
        "allowed_actions",
        "status",
    }
    return {k: payload[k] for k in payload if k in allow}


__all__ = ["SENSITIVE_KEYS", "redact", "safe_summary"]

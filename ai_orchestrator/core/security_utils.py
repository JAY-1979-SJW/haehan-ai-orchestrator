"""Common security helpers for logs, audit events, and safe records."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

REDACTED = "***"
SENSITIVE_KEYS = (
    "password",
    "passwd",
    "pwd",
    "pw",
    "token",
    "access_token",
    "refresh_token",
    "id_token",
    "token_hash",
    "cookie",
    "session",
    "session_id",
    "storage_state",
    "secret",
    "client_secret",
    "authorization",
    "api_key",
    "apikey",
    "private_key",
    "credential",
    "otp",
    "verification_code",
    "auth_code",
)
EMAIL_RE = re.compile(r"(?i)([a-z0-9._%+-]{2})[a-z0-9._%+-]*@([a-z0-9.-]+\.[a-z]{2,})")
RRN_RE = re.compile(r"\b\d{6}-?[1-4]\d{6}\b")
CARD_RE = re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b")
BEARER_RE = re.compile(r"(?i)\b(bearer)\s+[a-z0-9._~+/=-]{12,}")
# 키 이름 없이 값만으로 드러나는 발급 토큰 — OpenAI/GitHub/Slack/AWS/JWT
OPENAI_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")
GITHUB_TOKEN_RE = re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b")
SLACK_TOKEN_RE = re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")
AWS_KEY_RE = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\b")


def mask_email(value: str) -> str:
    return EMAIL_RE.sub(lambda m: f"{m.group(1)}***@{m.group(2)}", value or "")


def mask_identifier(value: str) -> str:
    text = mask_email(value or "")
    if "@" in text:
        return text
    if len(text) <= 2:
        return "**" if text else ""
    if len(text) <= 6:
        return text[:1] + "***"
    return text[:2] + "***" + text[-2:]


def safe_preview(value: str, limit: int = 100) -> str:
    text = (value or "")[:limit]
    text = mask_email(text)
    text = RRN_RE.sub("[RRN_REDACTED]", text)
    text = CARD_RE.sub("[CARD_REDACTED]", text)
    text = BEARER_RE.sub(r"\1 [TOKEN_REDACTED]", text)
    text = JWT_RE.sub("[TOKEN_REDACTED]", text)
    text = OPENAI_KEY_RE.sub("[TOKEN_REDACTED]", text)
    text = GITHUB_TOKEN_RE.sub("[TOKEN_REDACTED]", text)
    text = SLACK_TOKEN_RE.sub("[TOKEN_REDACTED]", text)
    text = AWS_KEY_RE.sub("[TOKEN_REDACTED]", text)
    return text


def is_sensitive_key(key: str) -> bool:
    lowered = str(key).lower()
    return any(token in lowered for token in SENSITIVE_KEYS)


def redact_value(key: str, value: Any) -> Any:
    if is_sensitive_key(key):
        return REDACTED
    return redact_obj(value)


def redact_obj(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: redact_value(str(k), v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_obj(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_obj(item) for item in value)
    if isinstance(value, str):
        return safe_preview(value, limit=500)
    return value


def redact_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    return dict(redact_obj(data))


__all__ = [
    "REDACTED",
    "SENSITIVE_KEYS",
    "is_sensitive_key",
    "mask_email",
    "mask_identifier",
    "redact_mapping",
    "redact_obj",
    "redact_value",
    "safe_preview",
]

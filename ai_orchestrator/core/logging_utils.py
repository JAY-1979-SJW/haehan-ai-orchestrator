"""Logging helpers.

This module stays as a compatibility facade. New redaction behavior lives in
``scripts.common.security`` so browser, audit, credentials, and CLI code can share one
policy.
"""

from __future__ import annotations

import json
from typing import Any

from ai_orchestrator.core.security_utils import redact_obj


def mask_sensitive(data: Any) -> Any:
    """Return a deep-redacted copy of data safe for logs."""
    return redact_obj(data)


def safe_log_dict(**kwargs) -> dict:
    """Build a JSON-safe dict with sensitive values redacted."""
    return mask_sensitive(kwargs)


def truncate_large_text(text: str, max_len: int = 500) -> str:
    """Truncate large text while recording how many characters were cut."""
    if not isinstance(text, str):
        return str(text)[:max_len]
    if len(text) <= max_len:
        return text
    cut = len(text) - max_len
    return text[:max_len] + f"...[+{cut}chars truncated]"


def safe_json(obj: Any) -> str:
    """Serialize an object to JSON, falling back to ``str`` when needed."""

    def _default(o):
        return str(o)

    return json.dumps(obj, ensure_ascii=False, default=_default)

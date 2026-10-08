"""Learned Site Profile Store — AI가 성공한 구조를 안전하게 저장한다."""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

# 저장 금지 키 접두어 — exact prefix/full match 방식
# "password_stored" 같은 내부 safe marker(_stored suffix)는 허용
_FORBIDDEN_STORE_PREFIXES = frozenset([
    "password", "passwd", "otp_value", "pin_value", "secret_value",
    "cookie_value", "session_value", "token_value", "storage_state",
    "cert_password", "certificate_password", "npki",
    "auth_header", "private_key", "account_number",
    "credit_card", "ssn", "resident_number",
])

# 허용 패턴: _stored suffix가 있으면 safe marker로 허용
_SAFE_MARKER_SUFFIX = "_stored"

_STORE: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


def _is_forbidden_key(key: str) -> bool:
    """저장 금지 key 여부. _stored suffix safe marker는 허용."""
    k = key.lower()
    if k.endswith(_SAFE_MARKER_SUFFIX):
        return False
    return any(k == prefix or k.startswith(prefix + "_") or k.startswith(prefix + ".")
               for prefix in _FORBIDDEN_STORE_PREFIXES)


def _sanitize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """민감 키 제거."""
    return {k: v for k, v in entry.items() if not _is_forbidden_key(k)}


def _validate_entry(entry: dict[str, Any]) -> list[str]:
    errors = []
    for k in entry:
        if _is_forbidden_key(k):
            errors.append(f"금지 키 포함: {k}")
    return errors


def save_learned_profile(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    host: str,
    site_type: str,
    workflow_template_id: str | None = None,
    safe_selector_candidates: dict[str, list[str]] | None = None,
    capability_hints: list[str] | None = None,
    action_risk_mapping: dict[str, str] | None = None,
    non_sensitive_labels: list[str] | None = None,
) -> dict[str, Any]:
    """
    성공한 workflow 구조를 저장한다.
    민감정보는 저장하지 않는다.
    """
    if not host:
        raise ValueError("host 필수")

    entry: dict[str, Any] = {
        "host": host,
        "site_type": site_type,
        "learned_at": datetime.now(timezone.utc).isoformat(),
        "workflow_template_id": workflow_template_id,
        "safe_selector_candidates": safe_selector_candidates or {},
        "capability_hints": capability_hints or [],
        "action_risk_mapping": action_risk_mapping or {},
        "non_sensitive_labels": non_sensitive_labels or [],
        # 안전 경계
        "password_stored": False,
        "otp_stored": False,
        "cookie_stored": False,
        "session_stored": False,
        "storage_state_stored": False,
        "cert_password_stored": False,
    }

    sanitized = _sanitize_entry(entry)
    errors = _validate_entry(sanitized)
    if errors:
        raise ValueError(f"저장 금지 항목 포함: {errors}")

    with _LOCK:
        _STORE[host] = sanitized

    return dict(sanitized)


def get_learned_profile(host: str) -> dict[str, Any] | None:
    with _LOCK:
        return dict(_STORE[host]) if host in _STORE else None


def update_learned_profile(host: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    """기존 learned profile에 안전한 정보를 추가한다."""
    # sanitize 전에 원본 updates를 검증 (forbidden key 차단)
    errors = _validate_entry(updates)
    if errors:
        raise ValueError(f"저장 금지 항목 포함: {errors}")
    sanitized_updates = _sanitize_entry(updates)
    errors = _validate_entry(sanitized_updates)
    if errors:
        raise ValueError(f"저장 금지 항목 포함: {errors}")

    with _LOCK:
        if host not in _STORE:
            return None
        _STORE[host].update(sanitized_updates)
        _STORE[host]["updated_at"] = datetime.now(timezone.utc).isoformat()
        return dict(_STORE[host])


def list_learned_hosts() -> list[str]:
    with _LOCK:
        return list(_STORE.keys())


def delete_learned_profile(host: str) -> bool:
    with _LOCK:
        if host in _STORE:
            del _STORE[host]
            return True
        return False


def clear_all() -> None:
    with _LOCK:
        _STORE.clear()


def has_learned_profile(host: str) -> bool:
    with _LOCK:
        return host in _STORE

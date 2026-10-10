"""
로컬 에이전트 결과 sanitizer

로컬 실행 결과에서 민감값을 제거한다.
URL host / title hint / download metadata / extracted readonly data만 허용.
cookie/session/password/OTP/cert 관련 값이 있으면 제거 후 WARN 처리.
"""
from __future__ import annotations

from typing import Any

# ── 민감 필드 목록 ─────────────────────────────────────────────────────────────

_SENSITIVE_FIELDS: frozenset[str] = frozenset({
    "cookie", "cookies", "session", "token", "password", "otp",
    "certificate_password", "cert_password", "auth_token",
    "access_token", "refresh_token", "npki_data", "private_key",
    "localStorage", "sessionStorage", "Authorization", "auth_header",
    "certificate_file_path", "npki", "credential",
})

# ── 고정 안전 필드 ─────────────────────────────────────────────────────────────

_FIXED_SAFE_FIELDS: dict[str, Any] = {
    "sensitive_data_collected": False,
    "cookie_exported": False,
    "session_exported": False,
    "password_collected": False,
    "otp_collected": False,
    "certificate_password_collected": False,
}

# ── extracted_data 내부 민감 키 ────────────────────────────────────────────────

_SENSITIVE_EXTRACTED_KEYS: frozenset[str] = frozenset({
    "cookie", "session", "password", "otp", "token",
    "certificate_password", "npki", "auth_header",
    "localStorage", "sessionStorage", "private_key",
})


def sanitize_result(result: dict[str, Any]) -> dict[str, Any]:
    """
    결과 dict에서 민감 필드를 제거하고 안전한 결과를 반환한다.
    고정 안전 필드는 항상 False로 설정한다.
    """
    removed: list[str] = []
    safe: dict[str, Any] = {}

    for k, v in result.items():
        if k in _SENSITIVE_FIELDS:
            removed.append(k)
        else:
            safe[k] = v

    # extracted_data 내부 민감 키 제거
    if "extracted_data" in safe and isinstance(safe["extracted_data"], dict):
        safe["extracted_data"] = _sanitize_extracted(safe["extracted_data"])

    # 고정 안전 필드 강제 설정
    safe.update(_FIXED_SAFE_FIELDS)

    if removed:
        safe["_sanitized_fields"] = removed

    return safe


def validate_sanitized_result(result: dict[str, Any]) -> list[str]:
    """
    sanitize된 결과에 민감 필드가 없는지 검증한다.
    위반 목록 반환 (빈 = 안전).
    """
    violations: list[str] = []

    for field in _SENSITIVE_FIELDS:
        val = result.get(field)
        if val not in (None, False, "", [], {}):
            violations.append(f"민감 필드 잔존: {field!r} = {str(val)[:30]!r}")

    for field, expected in _FIXED_SAFE_FIELDS.items():
        if result.get(field) is not expected:
            violations.append(f"고정 필드 불일치: {field!r} = {result.get(field)!r}")

    return violations


def _sanitize_extracted(data: dict[str, Any]) -> dict[str, Any]:
    """extracted_data 내부 민감 키를 제거한다."""
    return {k: v for k, v in data.items() if k not in _SENSITIVE_EXTRACTED_KEYS}

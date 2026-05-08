"""
로컬 세션 경계 모듈

인증 대기/완료/자동 재개 흐름에서도 민감정보가 서버로 넘어가지 않도록 강제한다.

검증 항목:
- cookie_exported = false
- session_exported = false
- password_collected = false
- otp_collected = false
- certificate_password_collected = false
- sensitive_data_collected = false
- storage_state_exported = false
"""
from __future__ import annotations

from typing import Any

# ── 필수 안전 필드 및 기대값 ──────────────────────────────────────────────────

_REQUIRED_SAFE_FIELDS: dict[str, bool] = {
    "cookie_exported": False,
    "session_exported": False,
    "password_collected": False,
    "otp_collected": False,
    "certificate_password_collected": False,
    "sensitive_data_collected": False,
    "storage_state_exported": False,
}

# ── 서버 전송 금지 필드 ───────────────────────────────────────────────────────

_FORBIDDEN_EXPORT_FIELDS: frozenset[str] = frozenset({
    "cookie", "cookies", "session", "session_token",
    "password", "otp", "certificate_password", "cert_password",
    "token", "access_token", "refresh_token", "auth_token",
    "npki", "npki_data", "private_key",
    "localStorage", "sessionStorage", "storage_state",
    "Authorization", "auth_header", "credential",
})


def enforce_session_boundary(result: dict[str, Any]) -> dict[str, Any]:
    """
    result dict에 세션 경계 안전 필드를 강제 적용하고
    금지 필드를 제거한다.

    반환: 강화된 safe result
    """
    safe = dict(result)

    # 금지 필드 제거
    removed = []
    for field in list(safe.keys()):
        if field in _FORBIDDEN_EXPORT_FIELDS:
            del safe[field]
            removed.append(field)

    # extracted_data 내부 금지 필드 제거
    if "extracted_data" in safe and isinstance(safe["extracted_data"], dict):
        safe["extracted_data"] = {
            k: v for k, v in safe["extracted_data"].items()
            if k not in _FORBIDDEN_EXPORT_FIELDS
        }

    # 필수 안전 필드 강제 설정
    safe.update(_REQUIRED_SAFE_FIELDS)

    if removed:
        safe["_boundary_removed_fields"] = removed

    return safe


def validate_session_boundary(result: dict[str, Any]) -> list[str]:
    """
    result에 세션 경계 위반이 없는지 검증한다.
    위반 목록 반환 (빈 = 안전).
    """
    violations: list[str] = []

    # 필수 안전 필드 확인
    for field, expected in _REQUIRED_SAFE_FIELDS.items():
        actual = result.get(field)
        if actual is not expected:
            violations.append(
                f"세션 경계 위반: {field!r} = {actual!r} (기대: {expected!r})"
            )

    # 금지 필드 존재 여부 확인
    for field in _FORBIDDEN_EXPORT_FIELDS:
        val = result.get(field)
        if val not in (None, False, "", [], {}):
            violations.append(f"금지 필드 노출: {field!r}")

    # extracted_data 내부 금지 필드 확인
    extracted = result.get("extracted_data", {})
    if isinstance(extracted, dict):
        for field in _FORBIDDEN_EXPORT_FIELDS:
            val = extracted.get(field)
            if val not in (None, False, "", [], {}):
                violations.append(f"extracted_data 금지 필드 노출: {field!r}")

    return violations


def get_boundary_safe_defaults() -> dict[str, Any]:
    """세션 경계 안전 기본값을 반환한다."""
    return dict(_REQUIRED_SAFE_FIELDS)


def is_safe_for_export(result: dict[str, Any]) -> bool:
    """result가 서버 전송에 안전한지 확인한다."""
    return len(validate_session_boundary(result)) == 0

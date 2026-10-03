"""
쓰기/발행 작업 결과 sanitizer

실행 결과에서 민감값 제거.
safe result 고정 필드 보장.
"""
from __future__ import annotations

from typing import Any

# ── 제거 대상 필드 ─────────────────────────────────────────────────────────────

_REMOVE_FIELDS: frozenset[str] = frozenset({
    "password", "otp", "cookie", "cookies", "session",
    "token", "access_token", "refresh_token",
    "certificate_password", "cert_password",
    "npki", "npki_data", "private_key",
    "auth_header", "Authorization",
    "localStorage", "sessionStorage", "storage_state",
})

# ── 고정 safe 필드 ─────────────────────────────────────────────────────────────

_FIXED_SAFE_FIELDS: dict[str, Any] = {
    "sensitive_data_collected": False,
    "cookie_exported": False,
    "session_exported": False,
    "password_collected": False,
    "otp_collected": False,
    "certificate_password_collected": False,
    "storage_state_exported": False,
}


def sanitize_write_result(result: dict[str, Any]) -> dict[str, Any]:
    """
    쓰기/발행 작업 결과에서 민감값을 제거하고 safe 필드를 강제한다.
    """
    safe = {k: v for k, v in result.items() if k not in _REMOVE_FIELDS}
    safe.update(_FIXED_SAFE_FIELDS)
    return safe


def validate_write_result(result: dict[str, Any]) -> list[str]:
    """safe 필드 위반 사항 목록 반환. 빈 리스트면 안전."""
    violations = []
    for field in _REMOVE_FIELDS:
        if field in result and result[field] not in (None, False, ""):
            violations.append(f"민감 필드 노출: {field}")
    for field, expected in _FIXED_SAFE_FIELDS.items():
        if result.get(field) != expected:
            violations.append(f"safe 필드 위반: {field}={result.get(field)!r} (기대값: {expected!r})")
    return violations


def build_write_result(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    task_id: str,
    action: str,
    ok: bool,
    domain: str = "",
    permission_id: str = "",
    message_ko: str = "",
    published_url: str = "",
    **extra,
) -> dict[str, Any]:
    """
    쓰기/발행 작업의 안전한 결과 dict를 생성한다.
    민감 필드를 포함하지 않는다.
    """
    result: dict[str, Any] = {
        "task_id": task_id,
        "action": action,
        "ok": ok,
        "domain": domain,
        "permission_id": permission_id,
        "message_ko": message_ko,
        "published_url": published_url,
        "server_browser_used": False,
    }
    # extra에서 민감 필드 제외
    for k, v in extra.items():
        if k not in _REMOVE_FIELDS:
            result[k] = v
    result.update(_FIXED_SAFE_FIELDS)
    return result

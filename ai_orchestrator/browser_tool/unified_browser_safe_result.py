"""
통합 브라우저 안전 결과 스키마

민감 데이터 필드 없음.
cookie/session/password/OTP/인증서 비밀번호 값 없음.
"""
from __future__ import annotations

from typing import Any

# ── final_status 상수 ─────────────────────────────────────────────────────────

STATUS_SUCCESS = "SUCCESS"
STATUS_FAILED = "FAILED"
STATUS_FALLBACK_REQUIRED = "FALLBACK_REQUIRED"
STATUS_LOCAL_HANDOFF_CREATED = "LOCAL_HANDOFF_CREATED"
STATUS_USER_ACTION_REQUIRED = "USER_ACTION_REQUIRED"
STATUS_BLOCKED = "BLOCKED"

# ── execution_used 상수 ───────────────────────────────────────────────────────

EXEC_SERVER_BROWSER = "SERVER_BROWSER"
EXEC_LOCAL_AGENT = "LOCAL_AGENT"
EXEC_USER_DIRECT = "USER_DIRECT"
EXEC_BLOCKED = "BLOCKED"

_FIXED_SAFE_FIELDS: dict[str, Any] = {
    "sensitive_data_collected": False,
    "cookie_exported": False,
    "session_exported": False,
    "password_collected": False,
    "otp_collected": False,
    "certificate_password_collected": False,
}

_SENSITIVE_RESULT_FIELDS: frozenset[str] = frozenset({
    "cookie", "cookies", "session", "token", "password", "otp",
    "cert_password", "certificate_password", "auth_token",
    "access_token", "refresh_token", "npki_data", "private_key",
    "credential",
})


def build_safe_result(
    task_id: str,
    ok: bool,
    execution_used: str,
    final_status: str,
    fallback_reason: str | None = None,
    security_signals: list[str] | None = None,
    message_ko: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    안전한 결과 dict를 생성한다.
    민감 데이터 필드는 항상 False/None.
    """
    result: dict[str, Any] = {
        "task_id": task_id,
        "ok": ok,
        "execution_used": execution_used,
        "final_status": final_status,
        "fallback_reason": fallback_reason,
        "security_signals": security_signals or [],
        "message_ko": message_ko,
        **_FIXED_SAFE_FIELDS,
    }
    if extra:
        # extra에서 민감 필드 제거 후 병합
        safe_extra = {k: v for k, v in extra.items() if k not in _SENSITIVE_RESULT_FIELDS}
        result.update(safe_extra)
    return result


def validate_safe_result(result: dict[str, Any]) -> list[str]:
    """
    결과에 민감 데이터 필드가 없는지 검증한다.
    위반 목록 반환 (빈 리스트 = 안전).
    """
    violations: list[str] = []
    for field in _SENSITIVE_RESULT_FIELDS:
        if field in result and result[field] not in (None, False, "", [], {}):
            violations.append(f"민감 필드 노출: {field!r}")
    # 고정 필드 검증
    for field, expected in _FIXED_SAFE_FIELDS.items():
        if result.get(field) is not expected:
            violations.append(f"고정 필드 값 불일치: {field!r} = {result.get(field)!r} (expected {expected!r})")
    return violations

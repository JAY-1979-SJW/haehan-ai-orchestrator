"""
통합 브라우저 작업 입출력 스키마

민감 데이터 필드 없음.
cookie/session/password/OTP/인증서 비밀번호 값 없음.
"""
from __future__ import annotations

from typing import Any

# ── 허용 action ────────────────────────────────────────────────────────────────

ALLOWED_TASK_ACTIONS: frozenset[str] = frozenset({
    "open", "read", "search", "navigate", "open_url",
    "public_read", "login", "login_wait",
    "report_generate", "api_call", "internal",
    "db_query", "backend_api",
})

# ── 차단 action ────────────────────────────────────────────────────────────────

BLOCKED_TASK_ACTIONS: frozenset[str] = frozenset({
    "cookie_export", "session_export", "password_save",
    "cert_file_access", "npki_access", "auto_sign", "e_signature",
    "bid_submit", "auto_bid_submit", "auto_payment", "auto_transfer",
    "auto_contract_submit", "token_export", "auth_header_export",
    "localStorage_dump", "sessionStorage_dump",
})

_REQUIRED_TASK_FIELDS: tuple[str, ...] = ("task_id", "action", "target_url")

_SENSITIVE_FIELDS: frozenset[str] = frozenset({
    "cookie", "cookies", "session", "token", "password", "otp",
    "cert_password", "certificate_password", "auth_token",
    "access_token", "refresh_token", "npki", "private_key",
})


def validate_task_input(task: dict[str, Any]) -> dict[str, Any]:
    """
    task 입력 schema를 검증하고 결과를 반환한다.
    민감 필드 포함 시 FAIL.
    """
    violations: list[str] = []

    # 필수 필드
    for f in _REQUIRED_TASK_FIELDS:
        if not task.get(f):
            violations.append(f"필수 필드 누락: {f!r}")

    # 차단 action
    action = (task.get("action") or "").lower()
    if action in BLOCKED_TASK_ACTIONS:
        violations.append(f"차단 action: {action!r}")

    # 민감 필드 포함 여부
    for f in _SENSITIVE_FIELDS:
        if f in task:
            violations.append(f"민감 필드 포함: {f!r}")

    return {
        "valid": len(violations) == 0,
        "violations": violations,
        "action": action,
        "task_id": task.get("task_id", ""),
    }


def build_safe_task(task: dict[str, Any]) -> dict[str, Any]:
    """
    task에서 허용 필드만 추출하여 안전한 task dict를 반환한다.
    민감 필드는 제거된다.
    """
    allowed_fields = {
        "task_id", "action", "target_url", "domain",
        "preferred_execution", "allow_server_first", "allow_local_fallback",
        "requires_user_presence", "readonly", "timeout_seconds",
        "site_category", "metadata",
    }
    safe = {k: v for k, v in task.items() if k in allowed_fields}
    return safe

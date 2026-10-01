"""
Universal Safe Result

모든 사이트 workflow에 공통으로 사용하는 safe result 구조.
민감값 없음. safe 필드 강제.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

# ── 공통 status 상수 ──────────────────────────────────────────────────────────

STATUS_COMPLETED             = "COMPLETED"
STATUS_PERMISSION_REQUIRED   = "PERMISSION_REQUIRED"
STATUS_USER_DIRECT_REQUIRED  = "USER_DIRECT_REQUIRED"
STATUS_BLOCKED               = "BLOCKED"
STATUS_FAILED                = "FAILED"
STATUS_WARN                  = "WARN"
STATUS_WARN_AUTH             = "WARN_AUTH_REQUIRED"
STATUS_WARN_PERMISSION       = "WARN_PERMISSION_REQUIRED"

# ── safe 필드 ─────────────────────────────────────────────────────────────────

_FIXED_SAFE_FIELDS: dict[str, Any] = {
    "password_collected": False,
    "otp_collected": False,
    "certificate_password_collected": False,
    "cookie_exported": False,
    "session_exported": False,
    "storage_state_exported": False,
    "server_browser_used": False,
}

# ── 민감 필드 제거 목록 ───────────────────────────────────────────────────────

_REMOVE_FIELDS: frozenset[str] = frozenset({
    "password", "otp", "cookie", "cookies", "session",
    "token", "access_token", "refresh_token",
    "certificate_password", "cert_password",
    "npki", "npki_data", "private_key",
    "auth_header", "Authorization",
    "localStorage", "sessionStorage", "storage_state",
})


def build_universal_result(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    task_id: str | None = None,
    site_id: str = "",
    workflow_id: str = "",
    status: str = STATUS_COMPLETED,
    actions_executed: list[str] | None = None,
    actions_pending_permission: list[str] | None = None,
    actions_user_direct_required: list[str] | None = None,
    blocked_actions: list[str] | None = None,
    safe_outputs: dict[str, Any] | None = None,
    audit_log_ids: list[str] | None = None,
    message_ko: str = "",
    **extra,
) -> dict[str, Any]:
    """
    공통 universal safe result를 생성한다.
    민감 필드를 포함하지 않는다.
    """
    result: dict[str, Any] = {
        "task_id": task_id or str(uuid.uuid4()),
        "site_id": site_id,
        "workflow_id": workflow_id,
        "status": status,
        "execution_used": "LOCAL_PLAYWRIGHT",
        "actions_executed": actions_executed or [],
        "actions_pending_permission": actions_pending_permission or [],
        "actions_user_direct_required": actions_user_direct_required or [],
        "blocked_actions": blocked_actions or [],
        "safe_outputs": {
            k: v for k, v in (safe_outputs or {}).items()
            if k not in _REMOVE_FIELDS
        },
        "audit_log_ids": audit_log_ids or [],
        "message_ko": message_ko,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    # extra에서 민감 필드 제외
    for k, v in extra.items():
        if k not in _REMOVE_FIELDS:
            result[k] = v
    result.update(_FIXED_SAFE_FIELDS)
    return result


def sanitize_universal_result(result: dict[str, Any]) -> dict[str, Any]:
    """기존 result dict에서 민감값 제거 및 safe 필드 강제."""
    safe = {k: v for k, v in result.items() if k not in _REMOVE_FIELDS}
    # safe_outputs 내부도 정리
    if "safe_outputs" in safe:
        safe["safe_outputs"] = {
            k: v for k, v in safe["safe_outputs"].items()
            if k not in _REMOVE_FIELDS
        }
    safe.update(_FIXED_SAFE_FIELDS)
    return safe


def validate_universal_result(result: dict[str, Any]) -> list[str]:
    """safe 필드 위반 목록 반환. 빈 리스트면 안전."""
    violations = []
    for field in _REMOVE_FIELDS:
        if field in result and result[field] not in (None, False, ""):
            violations.append(f"민감 필드 노출: {field}")
    for field, expected in _FIXED_SAFE_FIELDS.items():
        if result.get(field) != expected:
            violations.append(f"safe 필드 위반: {field}={result.get(field)!r}")
    return violations


def merge_step_results(
    base: dict[str, Any],
    step_result: dict[str, Any],
    step_id: str,
) -> dict[str, Any]:
    """step 실행 결과를 universal result에 병합한다."""
    # safe_outputs에 step 결과 추가
    so = base.get("safe_outputs", {})
    so[step_id] = {
        k: v for k, v in step_result.items() if k not in _REMOVE_FIELDS
    }
    base["safe_outputs"] = so
    return base

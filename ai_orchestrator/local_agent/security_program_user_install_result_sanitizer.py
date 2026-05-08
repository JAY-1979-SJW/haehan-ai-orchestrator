"""Security Program User Install Result Sanitizer — 사용자 설치 모드 결과 sanitizer."""
from __future__ import annotations

from typing import Any

# 서버 보고 허용 필드
_ALLOWED_FIELDS = frozenset((
    "task_id",
    "status",
    "installer_safe_name",
    "source_host",
    "sha256",
    "signature_status",
    "signer_subject",
    "file_size_bytes",
    "target_domain",
    "message",
    "opened",
    "auto_execute",
    "install_detected",
    "signals_before",
    "signals_after",
    "signals_resolved",
    "user_action_required",
    "retry_ready",
    # safe fields
    "cookie_exported",
    "session_exported",
    "password_collected",
    "otp_collected",
    "certificate_password_collected",
    "storage_state_exported",
    "server_browser_used",
))

# 서버 보고 금지 prefix
_FORBIDDEN_PREFIXES = (
    "local_path", "full_path", "installer_path",
    "password", "otp", "cert_password", "cookie", "session",
    "token", "storage_state", "registry", "npki", "cert_file",
    "private_key", "raw_log", "installer_log",
)

_SAFE_FIELDS = (
    "cookie_exported", "session_exported", "password_collected",
    "otp_collected", "certificate_password_collected",
    "storage_state_exported", "server_browser_used",
)


def sanitize_user_install_result(raw_result: dict[str, Any]) -> dict[str, Any]:
    """결과에서 민감 정보를 제거하고 허용 필드만 반환."""
    sanitized: dict[str, Any] = {}

    for key, value in raw_result.items():
        if _is_forbidden_key(key):
            continue
        if key in _ALLOWED_FIELDS:
            sanitized[key] = value

    # safe fields 강제 False
    for f in _SAFE_FIELDS:
        sanitized[f] = False

    # auto_execute는 항상 False (AI는 자동 실행 안함)
    if "auto_execute" not in sanitized:
        sanitized["auto_execute"] = False

    return sanitized


def check_no_sensitive_data(result: dict[str, Any]) -> list[str]:
    """결과에 민감 정보가 포함되어 있으면 위반 목록 반환."""
    violations: list[str] = []

    for key, value in result.items():
        if _is_forbidden_key(key) and value:
            violations.append(f"금지 필드: {key}")

    for f in _SAFE_FIELDS:
        if result.get(f) is True:
            violations.append(f"safe field 위반: {f} = True")

    if result.get("auto_execute") is True:
        violations.append("auto_execute = True (사용자 직접 실행 모드 위반)")

    return violations


def _is_forbidden_key(key: str) -> bool:
    key_lower = key.lower()
    for prefix in _FORBIDDEN_PREFIXES:
        if key_lower == prefix or key_lower.startswith(prefix + "_") or prefix in key_lower.split("_"):
            return True
    return False

"""Security Program Install Result Sanitizer — 설치 결과에서 민감 정보를 제거한다."""
from __future__ import annotations

from typing import Any

# 서버 보고 허용 필드
_ALLOWED_FIELDS = frozenset((
    "task_id",
    "domain",
    "installer_safe_name",
    "source_host",
    "status",
    "error_category",
    "install_detected",
    "restart_required",
    "retry_ready",
    "server_browser_used",
    "signal_count",
    "signals",
    "requires_security_program",
    "requires_user_action",
))

# 서버 보고 금지 필드 (prefix 기반)
_FORBIDDEN_PREFIXES = (
    "password", "otp", "cert_password", "cookie", "session",
    "token", "storage_state", "local_path", "full_path",
    "registry", "npki", "cert_file", "private_key",
    "installer_log", "raw_log",
)

# 항상 False여야 하는 safe fields
_SAFE_FIELDS = (
    "cookie_exported",
    "session_exported",
    "password_collected",
    "otp_collected",
    "certificate_password_collected",
    "storage_state_exported",
    "server_browser_used",
)


def sanitize_install_result(raw_result: dict[str, Any]) -> dict[str, Any]:
    """
    설치 결과에서 민감 정보를 제거하고 안전한 필드만 반환한다.

    Returns:
        허용 필드만 포함된 dict + safe fields 항상 False
    """
    sanitized: dict[str, Any] = {}

    for key, value in raw_result.items():
        if _is_forbidden_key(key):
            continue
        if key in _ALLOWED_FIELDS:
            sanitized[key] = value

    # safe fields 강제 False
    for f in _SAFE_FIELDS:
        sanitized[f] = False

    return sanitized


def check_result_has_no_sensitive_data(result: dict[str, Any]) -> list[str]:
    """결과에 민감 정보가 포함되어 있으면 위반 목록 반환."""
    violations: list[str] = []

    for key, value in result.items():
        if _is_forbidden_key(key) and value:
            violations.append(f"금지 필드 포함: {key}")

    for f in _SAFE_FIELDS:
        if result.get(f) is True:
            violations.append(f"safe field 위반: {f} = True")

    return violations


def build_safe_report(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    task_id: str,
    domain: str,
    installer_safe_name: str,
    source_host: str,
    status: str,
    install_detected: bool = False,
    restart_required: bool = False,
    retry_ready: bool = False,
    error_category: str | None = None,
) -> dict[str, Any]:
    """안전한 보고 dict를 생성한다 (민감 정보 없음)."""
    report: dict[str, Any] = {
        "task_id": task_id,
        "domain": domain,
        "installer_safe_name": installer_safe_name,
        "source_host": source_host,
        "status": status,
        "install_detected": install_detected,
        "restart_required": restart_required,
        "retry_ready": retry_ready,
    }
    if error_category:
        report["error_category"] = error_category

    for f in _SAFE_FIELDS:
        report[f] = False

    return report


def _is_forbidden_key(key: str) -> bool:
    key_lower = key.lower()
    for prefix in _FORBIDDEN_PREFIXES:
        if key_lower == prefix or key_lower.startswith(prefix + "_"):
            return True
    return False

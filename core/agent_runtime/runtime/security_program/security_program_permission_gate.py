"""Security Program Permission Gate — 설치 권한 객체 생성 및 검증."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

# 허용 action
_ALLOWED_INSTALL_ACTION = "install_security_program"

# 최대 실행 횟수 (설치는 1회만)
_MAX_EXECUTIONS = 1


def create_install_permission(
    domain: str,
    installer_name: str,
    source_host: str,
    installer_hash: str | None = None,
    duration_seconds: int = 3600,
) -> dict[str, Any]:
    """
    보안프로그램 설치 권한 객체를 생성한다.

    Returns:
        {
            "permission_id": str,
            "action": "install_security_program",
            "domain": str,
            "installer_name": str,   # 안전한 파일명만 (경로 제외)
            "source_host": str,
            "installer_hash": str|None,
            "max_executions": 1,
            "execution_count": 0,
            "expires_at": str,
            "requires_user_uac": True,
            "audit_log_required": True,
            "status": "ACTIVE",
        }
    """
    _validate_installer_name(installer_name)
    _validate_domain(domain)
    _validate_source_host(source_host)

    expires_at = (datetime.now(UTC) + timedelta(seconds=duration_seconds)).isoformat()

    return {
        "permission_id": str(uuid.uuid4()),
        "action": _ALLOWED_INSTALL_ACTION,
        "domain": domain,
        "installer_name": _safe_filename(installer_name),
        "source_host": source_host,
        "installer_hash": installer_hash,
        "max_executions": _MAX_EXECUTIONS,
        "execution_count": 0,
        "expires_at": expires_at,
        "requires_user_uac": True,
        "audit_log_required": True,
        "status": "ACTIVE",
    }


def validate_permission(
    permission: dict[str, Any],
    action: str,
    domain: str,
    installer_name: str,
    source_host: str,
    installer_hash: str | None = None,
) -> dict[str, Any]:
    """
    권한 객체의 유효성을 검증한다.

    Returns:
        {"valid": bool, "reason": str|None, "can_execute": bool}
    """
    if permission.get("status") != "ACTIVE":
        return _invalid(f"권한 비활성: {permission.get('status')}")

    if permission.get("action") != action:
        return _invalid(f"action 불일치: {permission.get('action')} != {action}")

    if permission.get("domain") != domain:
        return _invalid(f"domain 불일치: {permission.get('domain')} != {domain}")

    if permission.get("source_host") != source_host:
        return _invalid("source_host 불일치")

    if _safe_filename(installer_name) != permission.get("installer_name"):
        return _invalid("installer_name 불일치")

    # 해시 검증 (제공된 경우)
    if installer_hash and permission.get("installer_hash") and installer_hash != permission["installer_hash"]:
        return _invalid("installer hash 불일치")

    # 만료 확인
    try:
        expires_at = datetime.fromisoformat(permission["expires_at"])
        if datetime.now(UTC) > expires_at:
            return _invalid("권한 만료")
    except (KeyError, ValueError):
        return _invalid("만료 시각 파싱 오류")

    # 실행 횟수 확인
    if permission.get("execution_count", 0) >= permission.get("max_executions", 1):
        return _invalid("최대 실행 횟수 초과")

    return {"valid": True, "reason": None, "can_execute": True}


def consume_permission(permission: dict[str, Any]) -> dict[str, Any]:
    """권한을 소비한다 (실행 횟수 증가 + EXHAUSTED 처리)."""
    permission = dict(permission)
    permission["execution_count"] = permission.get("execution_count", 0) + 1
    if permission["execution_count"] >= permission.get("max_executions", 1):
        permission["status"] = "EXHAUSTED"
    return permission


def revoke_permission(permission: dict[str, Any]) -> dict[str, Any]:
    """권한을 철회한다."""
    permission = dict(permission)
    permission["status"] = "REVOKED"
    return permission


def _safe_filename(name: str) -> str:
    """경로 구분자를 제거하고 파일명만 반환."""
    return name.replace("\\", "/").split("/")[-1]


def _validate_installer_name(name: str) -> None:
    safe = _safe_filename(name)
    if not safe:
        raise ValueError("installer_name이 비어 있습니다.")
    forbidden = (".bat", ".cmd", ".ps1", ".js", ".vbs", ".pfx", ".p12", ".key", ".pem", ".crt", ".cer")
    ext = ("." + safe.rsplit(".", 1)[-1]).lower() if "." in safe else ""
    if ext in forbidden:
        raise ValueError(f"허용되지 않는 확장자: {ext}")


def _validate_domain(domain: str) -> None:
    if not domain or "." not in domain:
        raise ValueError(f"도메인 형식 오류: {domain}")


def _validate_source_host(host: str) -> None:
    if not host or "." not in host:
        raise ValueError(f"source_host 형식 오류: {host}")


def _invalid(reason: str) -> dict[str, Any]:
    return {"valid": False, "reason": reason, "can_execute": False}

"""
사용자 위임 권한 정책

권한 객체 구조 정의, 유효성 검증, 범위 초과 판별.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from ai_orchestrator.contracts.action_risk_policy import (
    is_blocked,
    is_delegatable,
)

# ── 권한 상태 상수 ─────────────────────────────────────────────────────────────

PERM_ACTIVE = "ACTIVE"
PERM_REVOKED = "REVOKED"
PERM_EXPIRED = "EXPIRED"
PERM_EXHAUSTED = "EXHAUSTED"

# ── 결과 상수 ──────────────────────────────────────────────────────────────────

CHECK_ALLOWED = "EXECUTION_ALLOWED"
CHECK_PERMISSION_REQUIRED = "PERMISSION_REQUIRED"
CHECK_EXPIRED = "PERMISSION_EXPIRED"
CHECK_REVOKED = "PERMISSION_REVOKED"
CHECK_EXHAUSTED = "PERMISSION_EXHAUSTED"
CHECK_SCOPE_EXCEEDED = "PERMISSION_SCOPE_EXCEEDED"
CHECK_BLOCKED = "BLOCKED_ACTION"

# ── 최대 허용 횟수 기본값 ─────────────────────────────────────────────────────

DEFAULT_MAX_EXECUTIONS = 1
MAX_BULK_LIMIT = 50  # 스팸 방지: 단일 권한 최대 실행 횟수 상한


def build_permission(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    action: str,
    domain: str,
    account: str = "",
    task_scope: str = "",
    duration_seconds: int = 3600,
    max_executions: int = DEFAULT_MAX_EXECUTIONS,
    granted_by: str = "user",
    permission_id: str | None = None,
    content_preview: str = "",
) -> dict[str, Any]:
    """
    사용자 위임 권한 객체를 생성한다.

    비밀번호/OTP/cert_password/cookie/session/token/인증서/NPKI/
    전자서명/투찰/결제/송금 관련 action은 권한 생성 자체를 거부한다.
    """
    if is_blocked(action):
        raise ValueError(f"권한 부여 불가 action: {action!r}. BLOCKED 등급은 사용자 위임 대상이 아닙니다.")
    if not is_delegatable(action):
        raise ValueError(f"위임 불가 action: {action!r}. USER_DELEGATED_PERMISSION_REQUIRED 등급만 위임 가능합니다.")

    # 스팸 방지
    if max_executions > MAX_BULK_LIMIT:
        raise ValueError(f"max_executions {max_executions}는 최대 허용({MAX_BULK_LIMIT})을 초과합니다.")

    now = datetime.now(tz=UTC)
    return {
        "permission_id": permission_id or str(uuid.uuid4()),
        "action": action,
        "domain": domain,
        "account": account,
        "task_scope": task_scope,
        "content_preview": content_preview,
        "granted_by": granted_by,
        "granted_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=duration_seconds)).isoformat(),
        "max_executions": max_executions,
        "execution_count": 0,
        "status": PERM_ACTIVE,
        "revoked_at": None,
    }


def _is_expired(permission: dict[str, Any]) -> bool:
    expires_at_str = permission.get("expires_at", "")
    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.now(tz=UTC) > expires_at:
                return True
        except ValueError:
            pass
    return False


def _scope_violation(
    permission: dict[str, Any], action: str, domain: str, account: str, task_scope: str
) -> dict[str, Any] | None:
    if permission.get("action") != action:
        return {
            "result": CHECK_SCOPE_EXCEEDED,
            "reason": f"action 불일치: 권한={permission.get('action')!r}, 요청={action!r}",
        }
    if permission.get("domain") and permission["domain"] != domain:
        return {
            "result": CHECK_SCOPE_EXCEEDED,
            "reason": f"domain 불일치: 권한={permission['domain']!r}, 요청={domain!r}",
        }
    if permission.get("account") and account and permission["account"] != account:
        return {"result": CHECK_SCOPE_EXCEEDED, "reason": "account 불일치"}
    if permission.get("task_scope") and task_scope and permission["task_scope"] != task_scope:
        return {"result": CHECK_SCOPE_EXCEEDED, "reason": "task_scope 불일치"}
    return None


def check_permission(
    permission: dict[str, Any] | None,
    action: str,
    domain: str,
    account: str = "",
    task_scope: str = "",
) -> dict[str, Any]:
    """
    권한이 요청된 실행을 허용하는지 검증한다.

    반환: {"result": CHECK_*, "reason": str}
    """
    if is_blocked(action):
        return {"result": CHECK_BLOCKED, "reason": f"BLOCKED 등급 action: {action!r}"}

    if permission is None:
        return {"result": CHECK_PERMISSION_REQUIRED, "reason": "권한 없음"}

    status = permission.get("status")
    if status == PERM_REVOKED:
        return {"result": CHECK_REVOKED, "reason": "권한이 철회됨"}
    if status == PERM_EXHAUSTED:
        return {"result": CHECK_EXHAUSTED, "reason": "최대 실행 횟수 소진"}

    # 만료 검사
    if _is_expired(permission):
        return {"result": CHECK_EXPIRED, "reason": "권한 만료됨"}

    # scope 검사
    scope_violation = _scope_violation(permission, action, domain, account, task_scope)
    if scope_violation is not None:
        return scope_violation

    # 횟수 검사
    max_exec = permission.get("max_executions", DEFAULT_MAX_EXECUTIONS)
    exec_count = permission.get("execution_count", 0)
    if exec_count >= max_exec:
        return {"result": CHECK_EXHAUSTED, "reason": f"최대 실행 횟수({max_exec}) 소진"}

    return {"result": CHECK_ALLOWED, "reason": "권한 유효"}


def revoke_permission(permission: dict[str, Any]) -> dict[str, Any]:
    """권한을 철회 처리한다. (원본 dict를 수정하고 반환)"""
    permission["status"] = PERM_REVOKED
    permission["revoked_at"] = datetime.now(tz=UTC).isoformat()
    return permission


def increment_execution(permission: dict[str, Any]) -> dict[str, Any]:
    """실행 횟수를 증가시키고 소진 시 EXHAUSTED로 전환한다."""
    permission["execution_count"] = permission.get("execution_count", 0) + 1
    if permission["execution_count"] >= permission.get("max_executions", DEFAULT_MAX_EXECUTIONS):
        permission["status"] = PERM_EXHAUSTED
    return permission

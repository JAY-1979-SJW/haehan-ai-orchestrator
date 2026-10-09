"""
사용자 위임 권한 저장소 (in-memory, 프로세스 범위)

권한은 permission_id로 관리된다.
비밀번호/OTP/cert_password/cookie/session/token은 저장하지 않는다.
"""

from __future__ import annotations

import threading
from typing import Any

from core.agent_runtime.runtime.permission.delegated_permission_policy import (
    CHECK_ALLOWED,
    PERM_ACTIVE,
    build_permission,
    check_permission,
    increment_execution,
    revoke_permission,
)

_lock = threading.Lock()
_store: dict[str, dict[str, Any]] = {}


def grant_permission(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    action: str,
    domain: str,
    account: str = "",
    task_scope: str = "",
    duration_seconds: int = 3600,
    max_executions: int = 1,
    granted_by: str = "user",
    content_preview: str = "",
) -> dict[str, Any]:
    """권한을 생성하고 저장소에 등록한다."""
    perm = build_permission(
        action=action,
        domain=domain,
        account=account,
        task_scope=task_scope,
        duration_seconds=duration_seconds,
        max_executions=max_executions,
        granted_by=granted_by,
        content_preview=content_preview,
    )
    with _lock:
        _store[perm["permission_id"]] = perm
    return perm


def get_permission(permission_id: str) -> dict[str, Any] | None:
    """permission_id로 권한 객체를 조회한다."""
    with _lock:
        return _store.get(permission_id)


def revoke(permission_id: str) -> bool:
    """권한을 철회한다. 성공 여부 반환."""
    with _lock:
        perm = _store.get(permission_id)
        if perm is None:
            return False
        revoke_permission(perm)
        return True


def use_permission(
    permission_id: str, action: str, domain: str, account: str = "", task_scope: str = ""
) -> dict[str, Any]:
    """
    권한 유효성 검사 후 실행 횟수를 증가시킨다.

    반환: {"result": CHECK_*, "reason": str, "permission": dict|None}
    """
    with _lock:
        perm = _store.get(permission_id)
        check = check_permission(perm, action, domain, account, task_scope)
        if check["result"] == CHECK_ALLOWED and perm is not None:
            increment_execution(perm)
        return {**check, "permission": perm}


def list_active_permissions() -> list[dict[str, Any]]:
    """현재 ACTIVE 상태 권한 목록 반환."""
    with _lock:
        return [p for p in _store.values() if p.get("status") == PERM_ACTIVE]


def clear_all() -> None:
    """테스트용 전체 초기화."""
    with _lock:
        _store.clear()



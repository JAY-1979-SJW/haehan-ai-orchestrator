"""Universal Agent Session — 연속 지시 세션을 관리한다."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from core.agent_runtime.runtime.permission.delegated_permission_store import (
    get_permission,
    grant_permission,
    revoke,
)
from core.agent_runtime.runtime.universal.learned_site_profile_store import (
    has_learned_profile,
)
from core.agent_runtime.runtime.universal.natural_language_task_api import (
    execute_natural_language_task,
)

_SAFE_FIELDS = [
    "cookie_exported",
    "session_exported",
    "password_collected",
    "otp_collected",
    "certificate_password_collected",
    "storage_state_exported",
    "server_browser_used",
]

_SESSIONS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


def create_session(
    host: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """새 agent 세션을 생성한다."""
    session_id = str(uuid.uuid4())
    session = {
        "session_id": session_id,
        "host": host or "unknown",
        "user_id": user_id or "anonymous",
        "created_at": datetime.now(UTC).isoformat(),
        "task_history": [],
        "granted_permissions": [],
        "learned_profile_loaded": has_learned_profile(host or "") if host else False,
    }
    with _LOCK:
        _SESSIONS[session_id] = session
    return dict(session)


def get_session(session_id: str) -> dict[str, Any] | None:
    with _LOCK:
        s = _SESSIONS.get(session_id)
        return dict(s) if s else None


def run_task_in_session(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    session_id: str,
    instruction: str,
    page_data: dict[str, Any] | None = None,
    url: str | None = None,
    runner_fn: Callable | None = None,
    page_fetch_fn: Callable | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    세션 내에서 자연어 지시를 실행한다.
    이전 세션의 권한 부여를 재사용한다.
    """
    with _LOCK:
        session = _SESSIONS.get(session_id)
    if not session:
        return {
            "status": "FAILED",
            "message_ko": f"세션 없음: {session_id}",
            "task_id": str(uuid.uuid4()),
            **dict.fromkeys(_SAFE_FIELDS, False),
        }

    # 세션의 권한 map 구성
    permission_map: dict[str, bool] = {}
    for perm_id in session.get("granted_permissions", []):
        perm = get_permission(perm_id)
        if perm and perm.get("status") == "ACTIVE":
            action = perm.get("action", "")
            if action:
                permission_map[action] = True

    task_id = str(uuid.uuid4())
    result = execute_natural_language_task(
        instruction=instruction,
        url=url,
        page_data=page_data,
        permission_map=permission_map,
        runner_fn=runner_fn,
        page_fetch_fn=page_fetch_fn,
        task_id=task_id,
        dry_run=dry_run,
        save_learned=True,
    )

    # 세션 이력 기록
    history_entry = {
        "task_id": task_id,
        "instruction": instruction,
        "intent": result.get("intent", "UNKNOWN"),
        "status": result.get("status"),
        "executed_at": datetime.now(UTC).isoformat(),
    }
    with _LOCK:
        if session_id in _SESSIONS:
            _SESSIONS[session_id]["task_history"].append(history_entry)

    return result


def grant_session_permission(
    session_id: str,
    action: str,
    domain: str,
    duration_seconds: int = 3600,
    max_executions: int = 10,
) -> dict[str, Any] | None:
    """세션에 권한을 부여한다."""
    with _LOCK:
        session = _SESSIONS.get(session_id)
    if not session:
        return None

    try:
        perm = grant_permission(
            action=action,
            domain=domain,
            duration_seconds=duration_seconds,
            max_executions=max_executions,
        )
        perm_id = perm["permission_id"]
        with _LOCK:
            if session_id in _SESSIONS:
                _SESSIONS[session_id]["granted_permissions"].append(perm_id)
        return {"permission_id": perm_id, "action": action, "domain": domain}
    except ValueError as e:
        return {"error": str(e), "action": action}


def revoke_session_permission(session_id: str, permission_id: str) -> bool:
    with _LOCK:
        session = _SESSIONS.get(session_id)
    if not session:
        return False
    try:
        revoke(permission_id)
        with _LOCK:
            if session_id in _SESSIONS:
                perms = _SESSIONS[session_id]["granted_permissions"]
                if permission_id in perms:
                    perms.remove(permission_id)
        return True
    except Exception:  # noqa: BLE001 - 세션 권한 회수(revoke_session_permission) 중 예외 시 False 반환 — 회수 실패를 알리는 fail-closed, 권한을 추가로 부여하는 동작 없음
        return False


def get_session_history(session_id: str) -> list[dict[str, Any]]:
    with _LOCK:
        session = _SESSIONS.get(session_id)
    return list(session.get("task_history", [])) if session else []


def close_session(session_id: str) -> bool:
    with _LOCK:
        if session_id in _SESSIONS:
            del _SESSIONS[session_id]
            return True
    return False


def clear_all_sessions() -> None:
    with _LOCK:
        _SESSIONS.clear()

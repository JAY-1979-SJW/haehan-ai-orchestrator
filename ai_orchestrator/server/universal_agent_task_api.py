"""Universal Agent Task API — server task 생성/조회. 외부 URL은 항상 local agent handoff."""
from __future__ import annotations

import threading
import uuid
from typing import Any

from ai_orchestrator.server.execution_location_guard import (
    LOCAL_AGENT_REQUIRED, build_local_agent_handoff,
)
from ai_orchestrator.server.universal_agent_models import (
    UniversalAgentTask, build_task_from_input, validate_task_model,
)
from ai_orchestrator.server.external_url_blocker import (
    block_external_fetch_from_server,
)

_LOCK = threading.Lock()
_TASKS: dict[str, UniversalAgentTask] = {}

_SAFE_FIELDS = (
    "cookie_exported", "session_exported", "password_collected",
    "otp_collected", "certificate_password_collected",
    "storage_state_exported", "server_browser_used",
)


def create_task(
    action: str,
    target_url: str = "",
    payload: dict[str, Any] | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    """
    task를 생성한다. 외부 URL이면 자동으로 LOCAL_AGENT_REQUIRED로 분류하고
    handoff payload를 포함한 결과를 반환한다.

    서버에서는 외부 URL fetch/title 미리 가져오기/screenshot/selector discovery를
    수행하지 않는다.
    """
    task_id = task_id or str(uuid.uuid4())
    task = build_task_from_input(
        task_id=task_id,
        action=action,
        target_url=target_url,
        payload=payload,
    )

    # validation
    v = validate_task_model(task.to_dict())
    if not v["valid"]:
        return {
            "ok": False,
            "status": "BLOCKED",
            "task_id": task_id,
            "blocked_reason": v.get("blocked_reason", "VALIDATION_ERROR"),
            "reason": v["reason"],
            **{f: False for f in _SAFE_FIELDS},
        }

    with _LOCK:
        _TASKS[task_id] = task

    result: dict[str, Any] = task.to_dict()
    result["ok"] = True

    if task.execution_location == LOCAL_AGENT_REQUIRED:
        # handoff payload 추가
        handoff = build_local_agent_handoff({
            "task_id": task_id,
            "target_url": target_url,
            "action": action,
        })
        result["local_agent_handoff"] = handoff
        result["status"] = "WAITING_LOCAL_AGENT"

    # safe fields 강제
    for f in _SAFE_FIELDS:
        result[f] = False

    return result


def get_task(task_id: str) -> dict[str, Any] | None:
    """task 상태 조회."""
    with _LOCK:
        task = _TASKS.get(task_id)
    if not task:
        return None
    d = task.to_dict()
    d["ok"] = True
    return d


def update_task_result(task_id: str, status: str, result: dict[str, Any] | None = None) -> bool:
    """local agent로부터 결과를 받아 task 상태 업데이트."""
    with _LOCK:
        task = _TASKS.get(task_id)
        if not task:
            return False
        # server_browser_used=True 결과는 거부
        if result and result.get("server_browser_used") is True:
            return False
        task.status = status
        if result:
            # safe fields는 강제 False
            sanitized = dict(result)
            for f in _SAFE_FIELDS:
                sanitized[f] = False
            task.payload["result"] = sanitized
        return True


def list_pending_local_agent_tasks() -> list[dict[str, Any]]:
    """local agent가 처리해야 할 대기 중 task 목록."""
    with _LOCK:
        tasks = [
            t.to_dict() for t in _TASKS.values()
            if t.execution_location == LOCAL_AGENT_REQUIRED
            and t.status == "WAITING_LOCAL_AGENT"
        ]
    return tasks


def reject_server_external_fetch(url: str, purpose: str = "") -> dict[str, Any]:
    """서버 코드에서 외부 fetch 시도 시 호출 — safe blocked 결과 반환."""
    return block_external_fetch_from_server(url, purpose=purpose)


def clear_all() -> None:
    with _LOCK:
        _TASKS.clear()

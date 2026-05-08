"""Universal Agent Models — server task 모델 + execution_location 검증."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from ai_orchestrator.server.execution_location_guard import (
    SERVER_INTERNAL_ONLY, LOCAL_AGENT_REQUIRED, USER_DIRECT_REQUIRED, BLOCKED,
    classify_execution_location_for_server,
    BLOCKED_SERVER_BROWSER_LAUNCH,
)
from ai_orchestrator.server.server_egress_policy import (
    is_external_url, sanitize_blocked_url_for_log,
)

_VALID_LOCATIONS = frozenset((
    SERVER_INTERNAL_ONLY, LOCAL_AGENT_REQUIRED, USER_DIRECT_REQUIRED, BLOCKED,
))

_SAFE_FIELDS = (
    "cookie_exported", "session_exported", "password_collected",
    "otp_collected", "certificate_password_collected",
    "storage_state_exported", "server_browser_used",
)


@dataclass
class UniversalAgentTask:
    """server에서 관리하는 universal agent task."""
    task_id: str
    action: str = ""
    target_url: str = ""
    execution_location: str = SERVER_INTERNAL_ONLY
    server_browser_used: bool = False
    local_agent_required: bool = False
    blocked_reason: str | None = None
    target_host: str = ""
    target_url_sanitized: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    status: str = "TASK_CREATED"

    def to_dict(self) -> dict[str, Any]:
        d = {
            "task_id": self.task_id,
            "action": self.action,
            "target_url": self.target_url,
            "execution_location": self.execution_location,
            "local_agent_required": self.local_agent_required,
            "blocked_reason": self.blocked_reason,
            "target_host": self.target_host,
            "target_url_sanitized": self.target_url_sanitized,
            "payload": self.payload,
            "status": self.status,
        }
        # safe fields는 항상 False (server_browser_used 포함)
        for f in _SAFE_FIELDS:
            d[f] = False
        return d


def validate_task_model(task_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Task dict의 execution_location 정합성 + server_browser_used False 강제 검증.
    위반이면 {"valid": False, "reason": "..."} 반환.
    """
    target_url = task_dict.get("target_url", "")
    execution_location = task_dict.get("execution_location")
    server_browser_used = task_dict.get("server_browser_used", False)

    # server_browser_used=True는 항상 위반
    if server_browser_used is True:
        return {
            "valid": False,
            "reason": "server_browser_used=True는 허용되지 않습니다.",
            "blocked_reason": BLOCKED_SERVER_BROWSER_LAUNCH,
        }

    # external URL인데 execution_location이 LOCAL_AGENT_REQUIRED 아니면 위반
    if target_url and is_external_url(target_url):
        if execution_location and execution_location != LOCAL_AGENT_REQUIRED \
           and execution_location != USER_DIRECT_REQUIRED \
           and execution_location != BLOCKED:
            return {
                "valid": False,
                "reason": (
                    f"외부 URL ({sanitize_blocked_url_for_log(target_url)})은 "
                    f"execution_location=LOCAL_AGENT_REQUIRED여야 합니다. "
                    f"현재: {execution_location}"
                ),
                "expected": LOCAL_AGENT_REQUIRED,
                "declared": execution_location,
            }

    # execution_location 값이 enum에 있어야 함
    if execution_location and execution_location not in _VALID_LOCATIONS:
        return {
            "valid": False,
            "reason": f"알 수 없는 execution_location: {execution_location}",
        }

    return {"valid": True, "reason": None}


def build_task_from_input(
    task_id: str,
    action: str,
    target_url: str = "",
    payload: dict[str, Any] | None = None,
) -> UniversalAgentTask:
    """입력으로부터 자동 분류된 UniversalAgentTask 생성."""
    raw = {
        "task_id": task_id,
        "action": action,
        "target_url": target_url,
        "payload": payload or {},
    }
    cls = classify_execution_location_for_server(raw)
    location = cls["execution_location"]
    host = cls.get("target_host", "")

    return UniversalAgentTask(
        task_id=task_id,
        action=action,
        target_url=target_url,
        execution_location=location,
        server_browser_used=False,
        local_agent_required=(location == LOCAL_AGENT_REQUIRED),
        blocked_reason=cls.get("blocked_reason"),
        target_host=host,
        target_url_sanitized=sanitize_blocked_url_for_log(target_url),
        payload=payload or {},
        status=("WAITING_LOCAL_AGENT" if location == LOCAL_AGENT_REQUIRED else "TASK_CREATED"),
    )

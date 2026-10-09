"""Common local tool execution contract.

This module is the narrow contract used before attaching site-specific tools
such as Naver workflows. It validates the common rail only: tool namespace,
approval state, execution location, and sensitive field boundaries.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "common-tool-runtime/v1"

TOOL_BROWSER = "browser"
TOOL_AI = "ai"
TOOL_SITE = "site"
ALLOWED_TOOL_NAMESPACES = frozenset({TOOL_BROWSER, TOOL_AI, TOOL_SITE})

EXECUTION_LOCAL_AGENT = "local_agent"
EXECUTION_SERVER = "server"
ALLOWED_EXECUTION_LOCATIONS = frozenset({EXECUTION_LOCAL_AGENT, EXECUTION_SERVER})

RISK_READ = "read"
RISK_PREPARE = "prepare"
RISK_WRITE = "write"
ALLOWED_RISK_LEVELS = frozenset({RISK_READ, RISK_PREPARE, RISK_WRITE})

PHASE_REQUESTED = "requested"
PHASE_APPROVAL_CHECKED = "approval_checked"
PHASE_DISPATCHED = "dispatched"
PHASE_RUNNING = "running"
PHASE_COMPLETED = "completed"
PHASE_FAILED = "failed"
PHASE_BLOCKED = "blocked"
ALLOWED_PHASES = frozenset(
    {
        PHASE_REQUESTED,
        PHASE_APPROVAL_CHECKED,
        PHASE_DISPATCHED,
        PHASE_RUNNING,
        PHASE_COMPLETED,
        PHASE_FAILED,
        PHASE_BLOCKED,
    }
)

FORBIDDEN_FIELD_NAMES = frozenset(
    {
        "authorization",
        "auth_header",
        "api_key",
        "access_token",
        "refresh_token",
        "device_token",
        "token",
        "secret",
        "password",
        "otp",
        "cookie",
        "cookies",
        "session",
        "localstorage",
        "sessionstorage",
        "private_key",
        "certificate_password",
        "certificate_file_path",
        "npki",
    }
)

SAFE_RESULT_FLAGS: dict[str, Any] = {
    "sensitive_data_collected": False,
    "cookie_exported": False,
    "session_exported": False,
    "password_collected": False,
    "token_exported": False,
}


class CommonToolRuntimeError(ValueError):
    """Raised when a common tool task/result violates the runtime contract."""


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _normalize_key(key: Any) -> str:
    return str(key).replace("-", "_").replace(" ", "_").lower()


def _find_forbidden_fields(value: Any, *, prefix: str = "") -> list[str]:
    violations: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = _normalize_key(key)
            path = f"{prefix}.{key}" if prefix else str(key)
            if normalized in FORBIDDEN_FIELD_NAMES:
                violations.append(path)
            violations.extend(_find_forbidden_fields(child, prefix=path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(_find_forbidden_fields(child, prefix=f"{prefix}[{index}]"))
    return violations


def build_common_tool_task(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    *,
    tool_namespace: str,
    action: str,
    execution_location: str = EXECUTION_LOCAL_AGENT,
    risk_level: str = RISK_READ,
    requires_approval: bool = False,
    approval_id: str | None = None,
    params: dict[str, Any] | None = None,
    task_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task = {
        "schema_version": SCHEMA_VERSION,
        "task_id": task_id or str(uuid.uuid4()),
        "tool_namespace": tool_namespace,
        "action": action,
        "execution_location": execution_location,
        "risk_level": risk_level,
        "requires_approval": requires_approval,
        "approval_id": approval_id,
        "params": params or {},
        "phase": PHASE_REQUESTED,
        "created_at": utc_now_iso(),
        "metadata": metadata or {},
    }
    validate_common_tool_task(task, raise_on_error=True)
    return task


def _task_field_violations(task: dict[str, Any]) -> list[str]:
    violations: list[str] = []

    if task.get("schema_version") != SCHEMA_VERSION:
        violations.append("schema_version mismatch")
    if not task.get("task_id"):
        violations.append("task_id missing")
    if task.get("tool_namespace") not in ALLOWED_TOOL_NAMESPACES:
        violations.append(f"invalid tool_namespace: {task.get('tool_namespace')!r}")
    if not task.get("action"):
        violations.append("action missing")
    if task.get("execution_location") not in ALLOWED_EXECUTION_LOCATIONS:
        violations.append(f"invalid execution_location: {task.get('execution_location')!r}")
    if task.get("risk_level") not in ALLOWED_RISK_LEVELS:
        violations.append(f"invalid risk_level: {task.get('risk_level')!r}")
    if task.get("phase") not in ALLOWED_PHASES:
        violations.append(f"invalid phase: {task.get('phase')!r}")

    requires_approval = bool(task.get("requires_approval"))
    if task.get("risk_level") == RISK_WRITE and not requires_approval:
        violations.append("write risk requires approval")
    if requires_approval and not task.get("approval_id"):
        violations.append("approval_id missing for approval-required task")
    return violations


def validate_common_tool_task(task: dict[str, Any], *, raise_on_error: bool = False) -> list[str]:
    violations = _task_field_violations(task)

    forbidden = _find_forbidden_fields(task)
    if forbidden:
        violations.append("forbidden field(s): " + ", ".join(sorted(forbidden)))

    if raise_on_error and violations:
        raise CommonToolRuntimeError("; ".join(violations))
    return violations


def build_common_tool_result(
    *,
    task_id: str,
    ok: bool,
    phase: str,
    message: str = "",
    data: dict[str, Any] | None = None,
    error_code: str = "",
) -> dict[str, Any]:
    result = {
        "schema_version": SCHEMA_VERSION,
        "task_id": task_id,
        "ok": ok,
        "phase": phase,
        "message": message,
        "data": data or {},
        "error_code": error_code,
        "created_at": utc_now_iso(),
        **SAFE_RESULT_FLAGS,
    }
    validate_common_tool_result(result, raise_on_error=True)
    return result


def validate_common_tool_result(result: dict[str, Any], *, raise_on_error: bool = False) -> list[str]:
    violations: list[str] = []

    if result.get("schema_version") != SCHEMA_VERSION:
        violations.append("schema_version mismatch")
    if not result.get("task_id"):
        violations.append("task_id missing")
    if result.get("phase") not in ALLOWED_PHASES:
        violations.append(f"invalid phase: {result.get('phase')!r}")
    for field, expected in SAFE_RESULT_FLAGS.items():
        if result.get(field) is not expected:
            violations.append(f"unsafe result flag: {field}")

    forbidden = _find_forbidden_fields(result)
    if forbidden:
        violations.append("forbidden field(s): " + ", ".join(sorted(forbidden)))

    if raise_on_error and violations:
        raise CommonToolRuntimeError("; ".join(violations))
    return violations


def dry_run_common_tool_flow(task: dict[str, Any]) -> dict[str, Any]:
    """Validate the common rail without executing browser/server side effects."""
    violations = validate_common_tool_task(task)
    if violations:
        return build_common_tool_result(
            task_id=str(task.get("task_id") or ""),
            ok=False,
            phase=PHASE_BLOCKED,
            message="common tool task blocked by contract",
            data={"violations": violations},
            error_code="COMMON_TOOL_CONTRACT_VIOLATION",
        )

    return build_common_tool_result(
        task_id=str(task["task_id"]),
        ok=True,
        phase=PHASE_COMPLETED,
        message="common tool task passed dry-run contract",
        data={
            "tool_namespace": task["tool_namespace"],
            "action": task["action"],
            "execution_location": task["execution_location"],
            "risk_level": task["risk_level"],
            "dry_run": True,
        },
    )

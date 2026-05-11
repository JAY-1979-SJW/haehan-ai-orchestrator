"""Read-only CAD tool executor for the local agent."""

from __future__ import annotations

from typing import Any

from .controller_loader import cad_ping
from .tool_catalog import build_call_args, get_tool_binding, normalize_tool_id


def cad_execute(tool_id: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a read-only CAD tool through the local CAD adapter."""
    normalized = normalize_tool_id(tool_id)
    binding = get_tool_binding(normalized)
    if binding is None:
        return {
            "ok": False,
            "status": "BLOCKED",
            "error_code": "CAD_TOOL_NOT_AUTO_EXECUTABLE",
            "message": f"{normalized} is not a read-only auto-executable CAD tool.",
        }

    ping = cad_ping()
    if not ping["ok"]:
        return {
            "ok": False,
            "status": "FAILED",
            "error_code": "CAD_ADAPTER_UNAVAILABLE",
            "ping": ping,
        }

    from local_worker_plugins.cad_app_controller.cad_local_command_session import CadLocalCommandSession

    session = CadLocalCommandSession()
    connect = session.connect(initialize_seconds=5.0)
    if not connect.success:
        return {
            "ok": False,
            "status": connect.status,
            "error_code": "CAD_CONNECT_FAILED",
            "message": connect.message,
            "errors": connect.errors,
            "warnings": connect.warnings,
        }

    module_id, method_name = binding
    call_args = build_call_args(normalized, args or {})
    result = session.execute_tool(module_id, method_name, args=call_args)
    return {
        "ok": result.success,
        "status": result.status,
        "tool_id": normalized,
        "module_id": module_id,
        "method_name": method_name,
        "message": result.message,
        "metadata": result.metadata,
        "errors": result.errors,
        "warnings": result.warnings,
        "connect": connect.metadata,
    }

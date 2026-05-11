"""MCP-facing local CAD adapter helpers.

These helpers keep the MCP layer away from AutoCAD internals. MCP calls local
agent actions, and the local agent owns CAD adapter/backend selection.
"""

from __future__ import annotations

import json
from typing import Any


def cad_local_adapter_ping_payload() -> dict[str, Any]:
    """Ping local CAD adapter through the local agent action registry."""
    from local_agent.actions import execute_action

    result = execute_action("cad.ping", {})
    return _action_result_to_payload("cad.ping", result)


def cad_local_adapter_status_payload() -> dict[str, Any]:
    """Return local CAD adapter status through the local agent action registry."""
    from local_agent.actions import execute_action

    result = execute_action("cad.status", {})
    return _action_result_to_payload("cad.status", result)


def cad_local_autocad_ping_payload(timeout_seconds: int = 10) -> dict[str, Any]:
    """Ping AutoCAD backend through local agent action registry."""
    from local_agent.actions import execute_action

    result = execute_action("cad.autocad_ping", {"timeout_seconds": timeout_seconds})
    return _action_result_to_payload("cad.autocad_ping", result)


def cad_local_bridge_health_payload(timeout_seconds: int = 5) -> dict[str, Any]:
    """Return end-to-end CAD bridge health for MCP clients.

    This keeps the official FastMCP tool surface thin: MCP calls one local
    helper, the helper calls the local agent action registry, and the local
    agent owns adapter/backend details. AutoCAD backend ping is timeout-limited
    so MCP clients get a bounded response even when COM is not responding.
    """
    adapter_ping = cad_local_adapter_ping_payload()
    adapter_status = cad_local_adapter_status_payload()
    autocad_ping = cad_local_autocad_ping_payload(timeout_seconds=timeout_seconds)

    adapter_ok = bool(adapter_ping.get("success")) and bool(adapter_status.get("success"))
    autocad_ok = bool(autocad_ping.get("success"))
    return {
        "action": "cad.bridge_health",
        "success": adapter_ok,
        "summary": "cad_bridge_ready" if adapter_ok else "cad_bridge_unavailable",
        "mcp_bridge": {
            "pattern": "FastMCP tool -> local_agent.actions.execute_action -> cad adapter",
            "adapter_connected": adapter_ok,
            "autocad_backend_connected": autocad_ok,
            "autocad_backend_status": autocad_ping.get("summary") or autocad_ping.get("error_code"),
            "timeout_seconds": int(timeout_seconds),
        },
        "adapter_ping": adapter_ping,
        "adapter_status": adapter_status,
        "autocad_ping": autocad_ping,
        "warnings": [] if autocad_ok else ["MCP/local adapter is reachable, but AutoCAD backend ping did not succeed."],
    }


def cad_agent_health_payload() -> dict[str, Any]:
    from local_agent.cad.http_agent_client import cad_agent_health

    return _cad_agent_payload("cad.agent_health", cad_agent_health())


def cad_agent_connect_payload(timeout_seconds: int = 20) -> dict[str, Any]:
    from local_agent.cad.http_agent_client import cad_agent_connect

    return _cad_agent_payload("cad.agent_connect", cad_agent_connect(timeout_seconds=timeout_seconds))


def cad_agent_status_payload() -> dict[str, Any]:
    from local_agent.cad.http_agent_client import cad_agent_status

    return _cad_agent_payload("cad.agent_status", cad_agent_status())


def cad_agent_active_document_payload(timeout_seconds: int = 10) -> dict[str, Any]:
    from local_agent.cad.http_agent_client import cad_agent_active_document

    return _cad_agent_payload("cad.agent_active_document", cad_agent_active_document(timeout_seconds=timeout_seconds))


def cad_local_adapter_execute_payload(tool_id: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a read-only CAD tool through local agent action registry."""
    from local_agent.actions import execute_action

    result = execute_action("cad.execute", {"tool_id": tool_id, "args": args or {}})
    return _action_result_to_payload("cad.execute", result)


def cad_local_adapter_ping_json() -> str:
    return _json(cad_local_adapter_ping_payload())


def cad_local_adapter_status_json() -> str:
    return _json(cad_local_adapter_status_payload())


def cad_local_autocad_ping_json(timeout_seconds: int = 10) -> str:
    return _json(cad_local_autocad_ping_payload(timeout_seconds))


def cad_local_bridge_health_json(timeout_seconds: int = 5) -> str:
    return _json(cad_local_bridge_health_payload(timeout_seconds))


def cad_agent_health_json() -> str:
    return _json(cad_agent_health_payload())


def cad_agent_connect_json(timeout_seconds: int = 20) -> str:
    return _json(cad_agent_connect_payload(timeout_seconds))


def cad_agent_status_json() -> str:
    return _json(cad_agent_status_payload())


def cad_agent_active_document_json(timeout_seconds: int = 10) -> str:
    return _json(cad_agent_active_document_payload(timeout_seconds))


def cad_local_adapter_execute_json(tool_id: str, args: dict[str, Any] | None = None) -> str:
    return _json(cad_local_adapter_execute_payload(tool_id, args))


def _action_result_to_payload(action: str, result: object) -> dict[str, Any]:
    return {
        "action": action,
        "success": bool(getattr(result, "success", False)),
        "summary": str(getattr(result, "summary", "")),
        "data": getattr(result, "data", {}) if isinstance(getattr(result, "data", {}), dict) else {},
        "error": str(getattr(result, "error", "")),
        "error_code": str(getattr(result, "error_code", "")),
    }


def _cad_agent_payload(action: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "action": action,
        "success": bool(result.get("ok")),
        "summary": str(result.get("status") or result.get("message") or action),
        "data": result,
        "error": str(result.get("error", "")),
        "error_code": "" if result.get("ok") else "CAD_AGENT_FAILED",
    }


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)

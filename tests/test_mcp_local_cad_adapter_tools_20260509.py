import json
import asyncio

import pytest

pytestmark = pytest.mark.external_cad

from mcp_server.local_cad_adapter_tools import (
    cad_local_adapter_execute_json,
    cad_local_adapter_ping_json,
    cad_local_adapter_status_json,
    cad_local_autocad_ping_json,
    cad_local_bridge_health_json,
)


def test_mcp_local_cad_adapter_ping_json():
    payload = json.loads(cad_local_adapter_ping_json())

    assert payload["action"] == "cad.ping"
    assert payload["success"] is True
    assert payload["data"]["cad_controller_import_ok"] is True


def test_mcp_local_cad_adapter_status_json():
    payload = json.loads(cad_local_adapter_status_json())

    assert payload["action"] == "cad.status"
    assert payload["success"] is True
    assert payload["data"]["module_count"] >= 8


def test_mcp_local_autocad_ping_json(monkeypatch):
    import local_agent.cad as cad

    monkeypatch.setattr(
        cad,
        "autocad_ping",
        lambda timeout_seconds=10: {"ok": True, "status": "OK", "name": "AutoCAD", "timeout_seconds": timeout_seconds},
    )

    payload = json.loads(cad_local_autocad_ping_json(timeout_seconds=2))

    assert payload["action"] == "cad.autocad_ping"
    assert payload["success"] is True
    assert payload["data"]["name"] == "AutoCAD"


def test_mcp_local_bridge_health_json(monkeypatch):
    import local_agent.cad as cad

    monkeypatch.setattr(
        cad,
        "autocad_ping",
        lambda timeout_seconds=10: {"ok": True, "status": "OK", "name": "AutoCAD", "timeout_seconds": timeout_seconds},
    )

    payload = json.loads(cad_local_bridge_health_json(timeout_seconds=2))

    assert payload["action"] == "cad.bridge_health"
    assert payload["success"] is True
    assert payload["mcp_bridge"]["adapter_connected"] is True
    assert payload["mcp_bridge"]["autocad_backend_connected"] is True


def test_mcp_local_cad_adapter_execute_blocks_non_readonly_tool():
    payload = json.loads(cad_local_adapter_execute_json("layer.delete", {}))

    assert payload["action"] == "cad.execute"
    assert payload["success"] is False
    assert payload["error_code"] == "CAD_TOOL_NOT_AUTO_EXECUTABLE"


def test_fastmcp_registers_local_cad_adapter_tools_when_available():
    import mcp_server.server as server

    assert server._MCP_AVAILABLE is True
    tools = asyncio.run(server.mcp.list_tools())
    names = {tool.name for tool in tools}
    assert "cad_local_adapter_ping" in names
    assert "cad_local_adapter_status" in names
    assert "cad_local_autocad_ping" in names
    assert "cad_local_bridge_health" in names
    assert "cad_local_adapter_execute" in names


def test_fastmcp_call_tool_invokes_local_cad_adapter_ping():
    import mcp_server.server as server

    result = asyncio.run(server.mcp.call_tool("cad_local_adapter_ping", {}))
    content, metadata = result
    payload = json.loads(content[0].text)

    assert payload["action"] == "cad.ping"
    assert payload["success"] is True
    assert metadata["result"] == content[0].text


def test_fastmcp_call_tool_invokes_local_cad_bridge_health(monkeypatch):
    import local_agent.cad as cad
    import mcp_server.server as server

    monkeypatch.setattr(
        cad,
        "autocad_ping",
        lambda timeout_seconds=10: {"ok": True, "status": "OK", "name": "AutoCAD", "timeout_seconds": timeout_seconds},
    )

    result = asyncio.run(server.mcp.call_tool("cad_local_bridge_health", {"timeout_seconds": 2}))
    content, metadata = result
    payload = json.loads(content[0].text)

    assert payload["action"] == "cad.bridge_health"
    assert payload["mcp_bridge"]["adapter_connected"] is True
    assert payload["mcp_bridge"]["autocad_backend_connected"] is True
    assert metadata["result"] == content[0].text

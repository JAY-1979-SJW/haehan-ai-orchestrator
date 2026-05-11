from local_agent.actions import execute_action
from local_agent.websocket_client import process_task


def test_cad_adapter_is_modular_package_with_compat_wrapper():
    import local_agent.cad as cad
    import local_agent.cad_adapter as wrapper
    from local_agent.cad.tool_catalog import is_read_only_tool

    assert wrapper.cad_ping is cad.cad_ping
    assert wrapper.cad_status is cad.cad_status
    assert wrapper.cad_execute is cad.cad_execute
    assert is_read_only_tool("layer.list") is True
    assert is_read_only_tool("layer.delete") is False


def test_cad_ping_action_imports_local_cad_controller():
    result = execute_action("cad.ping", {})

    assert result.success is True
    assert result.summary == "cad_ping_ok"
    assert result.data["cad_work_root_exists"] is True
    assert result.data["cad_controller_import_ok"] is True


def test_cad_status_lists_physical_modules():
    result = execute_action("cad.status", {})

    assert result.success is True
    assert result.data["module_count"] >= 8
    module_ids = {item["module_id"] for item in result.data["modules"]}
    assert "layer_tools" in module_ids
    assert "geometry_tools" in module_ids


def test_cad_autocad_ping_action_uses_backend_ping(monkeypatch):
    from local_agent.cad import backend_ping

    monkeypatch.setattr(
        backend_ping,
        "autocad_ping",
        lambda timeout_seconds=10: {"ok": True, "status": "OK", "name": "AutoCAD", "timeout_seconds": timeout_seconds},
    )

    result = execute_action("cad.autocad_ping", {"timeout_seconds": 3})

    assert result.success is True
    assert result.summary == "cad_autocad_ping_ok"
    assert result.data["name"] == "AutoCAD"


def test_cad_ping_runs_through_websocket_task_processor():
    task = {
        "type": "task",
        "task_id": "cad-ping-test",
        "action": "cad.ping",
        "params": {},
        "risk_level": "low",
    }

    result = process_task(task)

    assert result["type"] == "result"
    assert result["task_id"] == "cad-ping-test"
    assert result["success"] is True
    assert result["summary"] == "cad_ping_ok"


def test_cad_execute_blocks_non_readonly_tool_before_cad_connection():
    result = execute_action("cad.execute", {"tool_id": "layer.delete", "args": {}})

    assert result.success is False
    assert result.error_code == "CAD_TOOL_NOT_AUTO_EXECUTABLE"
    assert result.data["status"] == "BLOCKED"

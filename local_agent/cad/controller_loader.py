"""CAD controller discovery and status helpers."""

from __future__ import annotations

import importlib
from typing import Any

from .config import ensure_cad_work_on_path, get_cad_work_root


def cad_ping() -> dict[str, Any]:
    """Return local CAD adapter availability without touching AutoCAD."""
    root = get_cad_work_root()
    root_exists = root.exists()
    import_ok = False
    error = ""
    if root_exists:
        try:
            ensure_cad_work_on_path()
            importlib.import_module("local_worker_plugins.cad_app_controller")
            import_ok = True
        except Exception as exc:
            error = str(exc)

    return {
        "ok": root_exists and import_ok,
        "adapter": "local_agent.cad",
        "cad_work_root": str(root),
        "cad_work_root_exists": root_exists,
        "cad_controller_import_ok": import_ok,
        "error": error,
    }


def cad_status() -> dict[str, Any]:
    """Return adapter/module status without opening or modifying drawings."""
    ping = cad_ping()
    if not ping["ok"]:
        return {"ok": False, "ping": ping}

    from local_worker_plugins.cad_app_controller.autocad_com_adapter import AutoCadComAdapter
    from local_worker_plugins.cad_app_controller.cad_tool_module_bindings import (
        validate_cad_tool_module_bindings,
    )

    ok, warnings = validate_cad_tool_module_bindings(AutoCadComAdapter)
    adapter = AutoCadComAdapter()
    bindings = adapter.get_tool_module_bindings()
    return {
        "ok": ok,
        "ping": ping,
        "module_count": len(bindings),
        "modules": bindings,
        "warnings": warnings,
    }

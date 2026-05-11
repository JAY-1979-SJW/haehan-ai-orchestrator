"""Local agent wrapper for the AutoCAD .NET bridge file protocol."""

from __future__ import annotations

from typing import Any

from .config import ensure_cad_work_on_path


def dotnet_bridge_prepare(command: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    """Write a request for the AutoCAD .NET bridge to execute."""
    root = ensure_cad_work_on_path()
    from local_worker_plugins.cad_app_controller.cad_dotnet_bridge_client import write_dotnet_bridge_request

    result = write_dotnet_bridge_request(command, args or {})
    return _cad_action_result_to_dict(result, {"cad_work_root": str(root)})


def dotnet_bridge_read_result() -> dict[str, Any]:
    """Read the latest AutoCAD .NET bridge result."""
    root = ensure_cad_work_on_path()
    from local_worker_plugins.cad_app_controller.cad_dotnet_bridge_client import read_dotnet_bridge_result

    result = read_dotnet_bridge_result()
    return _cad_action_result_to_dict(result, {"cad_work_root": str(root)})


def dotnet_bridge_install_bundle() -> dict[str, Any]:
    """Install the AutoCAD .NET bridge bundle through the local adapter."""
    root = ensure_cad_work_on_path()
    from local_worker_plugins.cad_app_controller.cad_dotnet_bundle_manager import install_user_autoload_bundle

    result = install_user_autoload_bundle()
    return _cad_action_result_to_dict(result, {"cad_work_root": str(root)})


def dotnet_bridge_verify_bundle() -> dict[str, Any]:
    """Verify the installed AutoCAD .NET bridge bundle preflight."""
    root = ensure_cad_work_on_path()
    from local_worker_plugins.cad_app_controller.cad_dotnet_bundle_manager import verify_user_autoload_bundle

    result = verify_user_autoload_bundle()
    return _cad_action_result_to_dict(result, {"cad_work_root": str(root)})


def _cad_action_result_to_dict(result: object, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = getattr(result, "metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    data = {
        "ok": bool(getattr(result, "success", False)),
        "action": str(getattr(result, "action", "")),
        "status": str(getattr(result, "status", "")),
        "message": str(getattr(result, "message", "")),
        "metadata": metadata,
        "errors": list(getattr(result, "errors", []) or []),
        "warnings": list(getattr(result, "warnings", []) or []),
    }
    if extra:
        data.update(extra)
    return data

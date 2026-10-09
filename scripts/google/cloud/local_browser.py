"""Google Cloud read-only contract to local browser task conversion."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from core.agent_runtime.runtime.common_tool_runtime import (
    EXECUTION_LOCAL_AGENT,
    RISK_READ,
    TOOL_BROWSER,
    build_common_tool_task,
    dry_run_common_tool_flow,
)

from . import router

LOCAL_BROWSER_ACTION = "web_open_url_readonly"


def _target_host(target_url: str) -> str:
    return urlparse(target_url).netloc


def build_cloud_readonly_browser_task(
    service: str,
    task: str = "open",
    args: list[str] | None = None,
) -> dict[str, Any]:
    """Build a local-agent read-only browser task from a Cloud router result."""
    cloud_result = router.run_cloud(service, task, args or [])
    if cloud_result.get("mode") != "read_only_open" or cloud_result.get("ok") is not True:
        return {
            "ok": False,
            "reason": "cloud_contract_not_readonly_open",
            "service": service,
            "task": task or "open",
            "cloud_mode": cloud_result.get("mode"),
            "cloud_ok": cloud_result.get("ok"),
            "state_change": False,
            "local_agent_task": None,
        }

    target_url = str(cloud_result["target_url"])
    surface = cloud_result.get("surface", {})
    local_task = build_common_tool_task(
        tool_namespace=TOOL_BROWSER,
        action=LOCAL_BROWSER_ACTION,
        execution_location=EXECUTION_LOCAL_AGENT,
        risk_level=RISK_READ,
        requires_approval=False,
        params={
            "url": target_url,
            "target_url_host": _target_host(target_url),
            "wait_until": "domcontentloaded",
            "timeout_ms": 15000,
            "max_html_chars": 500000,
            "allow_private_network": False,
        },
        metadata={
            "site_id": "google",
            "google_tab": "cloud",
            "cloud_service": service,
            "cloud_surface": surface.get("key"),
            "cloud_action": cloud_result.get("action_key"),
            "source": "google_cloud_readonly_router",
        },
    )
    return {
        "ok": True,
        "service": service,
        "task": task or "open",
        "cloud_mode": cloud_result.get("mode"),
        "state_change": False,
        "local_agent_task": local_task,
    }


def dry_run_cloud_readonly_browser_task(
    service: str,
    task: str = "open",
    args: list[str] | None = None,
) -> dict[str, Any]:
    """Validate Cloud read-only browser conversion without opening a browser."""
    conversion = build_cloud_readonly_browser_task(service, task, args or [])
    if not conversion.get("ok"):
        return conversion
    dry_run = dry_run_common_tool_flow(conversion["local_agent_task"])
    return {
        **conversion,
        "dry_run_result": dry_run,
    }


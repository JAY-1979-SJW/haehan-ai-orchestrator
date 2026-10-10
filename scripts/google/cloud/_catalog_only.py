"""Shared safe helpers for Google Cloud wrappers."""
from __future__ import annotations

from scripts.google.common import workflows

from .registry import get_action, get_surface

FORBIDDEN_EXECUTION = (
    "gcloud",
    "google_cloud_api",
    "browser_final_click",
    "iam_change",
    "billing_change",
    "secret_value_access",
    "deploy_or_resource_mutation",
)


def _read_action_key(surface_key: str) -> str:
    action_key = f"{surface_key}_open"
    get_action(action_key)
    return action_key


def _is_readonly_open_task(surface_key: str, task: str) -> bool:
    normalized = (task or "open").strip().lower()
    return normalized in {"open", "read", "readonly", "read_only", _read_action_key(surface_key)}


def readonly_open_result(service: str, surface_key: str, task: str = "open") -> dict:
    action_key = _read_action_key(surface_key)
    action = workflows.get_action(action_key)
    return {
        "ok": True,
        "service": service,
        "task": task or "open",
        "mode": "read_only_open",
        "state_change": False,
        "execution_allowed": True,
        "requires_approval": False,
        "action_key": action_key,
        "target_url": action.target_url,
        "surface": get_surface(surface_key),
        "browser_navigation": {
            "type": "readonly_target_open",
            "target_url": action.target_url,
            "live_open": False,
            "final_click_allowed": False,
        },
    }


def catalog_only_result(service: str, surface_key: str, task: str = "open") -> dict:
    if _is_readonly_open_task(surface_key, task):
        return readonly_open_result(service, surface_key, task)
    return {
        "ok": False,
        "service": service,
        "task": task or "open",
        "mode": "catalog_only",
        "state_change": False,
        "execution_allowed": False,
        "forbidden_execution": list(FORBIDDEN_EXECUTION),
        "surface": get_surface(surface_key),
    }

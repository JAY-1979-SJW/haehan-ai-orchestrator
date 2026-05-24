"""Google Cloud registry derived from the locked Google tab registry."""
from __future__ import annotations

from scripts.google.live_inputs import build_live_input_coverage
from scripts.google.tab_registry import build_google_tab_summary

CLOUD_TAB_KEY = "cloud"
CLOUD_LIVE_INPUT_ACTIONS = ("cloud_create_api_credential", "cloud_iam_change_role")


def cloud_summary() -> dict:
    summary = build_google_tab_summary()
    cloud = next(tab for tab in summary["tabs"] if tab["key"] == CLOUD_TAB_KEY)
    live_supported = {item["action_key"] for item in build_live_input_coverage()["supported"]}
    cloud["live_input_supported_actions"] = [
        action["key"] for action in cloud["actions"] if action["key"] in live_supported
    ]
    cloud["prepare_or_open_only_approval_actions"] = [
        action["key"]
        for action in cloud["actions"]
        if action["requires_approval"] and action["key"] not in live_supported
    ]
    return cloud


def list_surfaces() -> list[dict]:
    return list(cloud_summary()["surfaces"])


def list_actions() -> list[dict]:
    return list(cloud_summary()["actions"])


def get_surface(surface_key: str) -> dict:
    for surface in list_surfaces():
        if surface["key"] == surface_key:
            return surface
    raise KeyError(f"unknown Google Cloud surface: {surface_key}")


def get_action(action_key: str) -> dict:
    for action in list_actions():
        if action["key"] == action_key:
            return action
    raise KeyError(f"unknown Google Cloud action: {action_key}")


def is_live_input_supported(action_key: str) -> bool:
    return action_key in CLOUD_LIVE_INPUT_ACTIONS


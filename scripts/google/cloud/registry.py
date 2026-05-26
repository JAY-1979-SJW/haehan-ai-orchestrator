"""Google Cloud registry derived from the locked Google tab registry."""
from __future__ import annotations

from scripts.google.live_inputs import build_live_input_coverage
from scripts.google.tab_registry import build_google_tab_summary

CLOUD_TAB_KEY = "cloud"
CLOUD_LIVE_INPUT_ACTIONS = (
    "maps_platform_change_key_or_quota",
    "cloud_create_api_credential",
    "cloud_iam_change_role",
    "cloud_billing_budget_or_link",
    "cloud_run_deploy_service",
    "compute_engine_create_vm",
    "cloud_storage_create_bucket",
    "bigquery_run_query_or_export",
    "gke_apply_change",
    "cloud_sql_change_instance",
    "pubsub_create_or_publish",
    "secret_manager_create_update",
    "cloud_logging_create_sink",
    "cloud_monitoring_create_alert",
)


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

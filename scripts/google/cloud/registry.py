"""Google Cloud registry derived from the locked Google tab registry."""
from __future__ import annotations

from scripts.google.common.tab_live_summary import tab_summary_with_live_inputs

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
    return tab_summary_with_live_inputs(CLOUD_TAB_KEY)


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

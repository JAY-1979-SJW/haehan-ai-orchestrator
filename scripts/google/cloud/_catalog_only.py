"""Shared safe catalog-only helpers for Google Cloud wrappers."""
from __future__ import annotations

from .registry import get_surface

FORBIDDEN_EXECUTION = (
    "gcloud",
    "google_cloud_api",
    "browser_final_click",
    "iam_change",
    "billing_change",
    "secret_value_access",
    "deploy_or_resource_mutation",
)


def catalog_only_result(service: str, surface_key: str, task: str = "open") -> dict:
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


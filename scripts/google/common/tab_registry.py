"""Google sub-tab registry and classification helpers.

This module keeps Google automation manageable without moving the existing
surface/action catalogs yet. Every Google surface and workflow action must map
to exactly one sub-tab before deeper module splits are made.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlparse

from scripts.google.common import surfaces
from scripts.google.common import workflows


@dataclass(frozen=True)
class GoogleTab:
    key: str
    label: str
    owner_package: str
    policy: str
    surface_keys: tuple[str, ...]


GOOGLE_TABS: tuple[GoogleTab, ...] = (
    GoogleTab(
        key="search",
        label="Search and home",
        owner_package="scripts.google.search",
        policy="browser_readonly",
        surface_keys=("google_home",),
    ),
    GoogleTab(
        key="identity",
        label="Identity and account",
        owner_package="scripts.google.identity",
        policy="user_present_or_oauth_only",
        surface_keys=("google_account",),
    ),
    GoogleTab(
        key="workspace",
        label="Workspace",
        owner_package="scripts.google.workspace",
        policy="api_preferred_private_data",
        surface_keys=(
            "gmail",
            "drive",
            "calendar",
            "docs",
            "sheets",
            "slides",
            "forms",
            "meet",
            "chat",
            "contacts",
            "keep",
            "tasks",
        ),
    ),
    GoogleTab(
        key="cloud",
        label="Google Cloud",
        owner_package="scripts.google.cloud",
        policy="manual_read_api_preferred_approval_required",
        surface_keys=(
            "cloud_console",
            "maps_platform",
            "cloud_apis_credentials",
            "cloud_iam",
            "cloud_billing",
            "cloud_run",
            "compute_engine",
            "cloud_storage",
            "bigquery",
            "gke",
            "cloud_sql",
            "pubsub",
            "secret_manager",
            "cloud_logging",
            "cloud_monitoring",
        ),
    ),
    GoogleTab(
        key="ai",
        label="Google AI",
        owner_package="scripts.google.ai",
        policy="manual_read_approval_required_for_prompt_key_or_deploy",
        surface_keys=("ai_studio", "gemini", "vertex_ai"),
    ),
    GoogleTab(
        key="youtube",
        label="YouTube",
        owner_package="scripts.google.youtube",
        policy="api_preferred_publish_approval_required",
        surface_keys=("youtube", "youtube_studio"),
    ),
    GoogleTab(
        key="marketing",
        label="Marketing and business",
        owner_package="scripts.google.marketing",
        policy="manual_read_api_preferred_spend_or_public_write_approval_required",
        surface_keys=(
            "search_console",
            "business_profile",
            "analytics",
            "tag_manager",
            "ads",
            "merchant_center",
            "adsense",
            "looker_studio",
        ),
    ),
    GoogleTab(
        key="developer",
        label="Developer tools and public docs",
        owner_package="scripts.google.developer",
        policy="public_read_or_user_present_developer_actions",
        surface_keys=(
            "android_developers",
            "play_console",
            "firebase_console",
            "google_developers",
            "chrome_developers",
            "apps_script",
            "colab",
        ),
    ),
    GoogleTab(
        key="media",
        label="Personal media",
        owner_package="scripts.google.media",
        policy="manual_read_private_media_approval_required",
        surface_keys=("photos",),
    ),
)


def _surface_to_tab() -> dict[str, GoogleTab]:
    mapping: dict[str, GoogleTab] = {}
    for tab in GOOGLE_TABS:
        for surface_key in tab.surface_keys:
            if surface_key in mapping:
                raise ValueError(f"duplicate Google surface tab mapping: {surface_key}")
            mapping[surface_key] = tab
    return mapping


def classify_surface(surface_key: str) -> GoogleTab:
    mapping = _surface_to_tab()
    try:
        return mapping[surface_key]
    except KeyError as exc:
        raise KeyError(f"Google surface is not assigned to a tab: {surface_key}") from exc


def classify_action(action_key: str) -> GoogleTab:
    action = workflows.get_action(action_key)
    return classify_surface(action.surface_key)


def _host(url: str) -> str:
    return urlparse(url).netloc or "(no-host)"


def build_google_tab_summary() -> dict:
    surface_catalog = surfaces.build_surface_catalog()
    action_catalog = workflows.build_action_catalog()
    surface_tab_map = _surface_to_tab()

    by_key = {item["key"]: item for item in surface_catalog["surfaces"]}
    missing_surfaces = sorted(set(by_key) - set(surface_tab_map))
    stale_mappings = sorted(set(surface_tab_map) - set(by_key))
    if missing_surfaces or stale_mappings:
        raise ValueError(
            "Google tab registry mismatch: "
            f"missing_surfaces={missing_surfaces}, stale_mappings={stale_mappings}"
        )

    summary: dict[str, Any] = {
        "site_id": "google",
        "tabs": [],
        "counts": {
            "tabs": len(GOOGLE_TABS),
            "surfaces": surface_catalog["counts"]["surfaces"],
            "actions": action_catalog["counts"]["actions"],
            "read_actions": action_catalog["counts"]["read_actions"],
            "approval_actions": action_catalog["counts"]["approval_actions"],
        },
        "host_warnings": [],
    }

    actions_by_surface: dict[str, list[dict]] = defaultdict(list)
    for action in action_catalog["actions"]:
        actions_by_surface[action["surface_key"]].append(action)

    for tab in GOOGLE_TABS:
        tab_surfaces = [by_key[key] for key in tab.surface_keys]
        tab_actions = [action for key in tab.surface_keys for action in actions_by_surface.get(key, [])]
        hosts = sorted({_host(item["url"]) for item in tab_surfaces} | {_host(item["target_url"]) for item in tab_actions})
        summary["tabs"].append(
            {
                **asdict(tab),
                "surface_count": len(tab_surfaces),
                "action_count": len(tab_actions),
                "read_action_count": sum(1 for action in tab_actions if not action["requires_approval"]),
                "approval_action_count": sum(1 for action in tab_actions if action["requires_approval"]),
                "hosts": hosts,
                "surfaces": [
                    {
                        "key": item["key"],
                        "label": item["label"],
                        "host": _host(item["url"]),
                        "risk": item["risk"],
                        "access_mode": item["access_mode"],
                        "status": item["status"],
                    }
                    for item in tab_surfaces
                ],
                "actions": [
                    {
                        "key": action["key"],
                        "surface_key": action["surface_key"],
                        "host": _host(action["target_url"]),
                        "operation": action["operation"],
                        "requires_approval": action["requires_approval"],
                        "status": action["status"],
                    }
                    for action in tab_actions
                ],
            }
        )

    surface_host = {item["key"]: _host(item["url"]) for item in surface_catalog["surfaces"]}
    for action in action_catalog["actions"]:
        expected = surface_host.get(action["surface_key"])
        actual = _host(action["target_url"])
        if expected and actual != expected:
            summary["host_warnings"].append(
                {
                    "action_key": action["key"],
                    "surface_key": action["surface_key"],
                    "surface_host": expected,
                    "action_host": actual,
                    "reason": "action target host differs from registered surface host",
                }
            )

    return summary


__all__ = [
    "GOOGLE_TABS",
    "GoogleTab",
    "build_google_tab_summary",
    "classify_action",
    "classify_surface",
]

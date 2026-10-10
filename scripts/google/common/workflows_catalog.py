"""Catalog builders and savers for Google work actions and adapter profiles."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from scripts.google.common.report_io import save_json_with_latest

from scripts.google.common.workflows_common import ACTION_CATALOG_DIR, ADAPTER_CATALOG_DIR, APPROVAL_PHRASE, LATEST_ACTION_CATALOG, LATEST_ADAPTER_CATALOG, LATEST_UNDEVELOPED_REPORT, UNDEVELOPED_REPORT_DIR, GoogleWorkAction, _adapter_profile_for_action, _surface_map
from scripts.google.common.workflows_actions import GOOGLE_WORK_ACTIONS


def build_adapter_profiles(
    actions: Iterable[GoogleWorkAction] = GOOGLE_WORK_ACTIONS,
) -> tuple:
    profiles = []
    for action in actions:
        profiles.append(_adapter_profile_for_action(action))
    return tuple(profiles)


def build_action_catalog(actions: Iterable[GoogleWorkAction] = GOOGLE_WORK_ACTIONS) -> dict:
    surface_by_key = _surface_map()
    adapters = {adapter.action_key: asdict(adapter) for adapter in build_adapter_profiles(actions)}
    items = []
    for action in actions:
        item = asdict(action)
        item["surface"] = surface_by_key.get(action.surface_key, {})
        item["execution_adapter"] = adapters.get(action.key, {})
        items.append(item)
    return {
        "site_id": "google",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "pipeline": "discover -> plan -> prepare -> approval -> execute -> verify -> log",
            "default_execution": "blocked_until_prepared_and_approved",
            "approval_phrase": APPROVAL_PHRASE,
            "secrets": "redact; never print passwords, tokens, cookies, or secret values",
        },
        "counts": {
            "actions": len(items),
            "read_actions": sum(1 for item in items if not item["requires_approval"]),
            "approval_actions": sum(1 for item in items if item["requires_approval"]),
            "adapter_profiles": len(adapters),
        },
        "actions": items,
    }


def save_action_catalog(catalog: dict | None = None, path: Path | None = None) -> Path:
    catalog = catalog or build_action_catalog()
    return save_json_with_latest(catalog, ACTION_CATALOG_DIR, LATEST_ACTION_CATALOG, "google_work_action_catalog", path)


def build_adapter_catalog(actions: Iterable[GoogleWorkAction] = GOOGLE_WORK_ACTIONS) -> dict:
    profiles = [asdict(profile) for profile in build_adapter_profiles(actions)]
    return {
        "site_id": "google",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "complete_definition": (
                "every action has an execution adapter profile, evidence "
                "requirements, verification checks, and final state policy"
            ),
            "state_change_default": "blocked_until_explicit_approval",
            "approved_execution": "open target/handoff and require final confirmation evidence",
        },
        "counts": {
            "adapter_profiles": len(profiles),
            "live_browser_capable": sum(1 for item in profiles if "browser" in item["adapter_type"]),
            "approval_handoff": sum(1 for item in profiles if item["final_state_policy"] != "read_only"),
        },
        "adapters": profiles,
    }


def save_adapter_catalog(catalog: dict | None = None, path: Path | None = None) -> Path:
    catalog = catalog or build_adapter_catalog()
    return save_json_with_latest(catalog, ADAPTER_CATALOG_DIR, LATEST_ADAPTER_CATALOG, "google_execution_adapter_catalog", path)


def build_undeveloped_report(actions: Iterable[GoogleWorkAction] = GOOGLE_WORK_ACTIONS) -> dict:
    """Separate implemented Google work from gated or missing development work."""
    from scripts.google.common import live_inputs

    action_catalog = build_action_catalog(actions)
    adapter_by_action = {
        adapter["action_key"]: adapter for adapter in build_adapter_catalog(actions)["adapters"]
    }
    live_coverage = live_inputs.build_live_input_coverage()
    live_supported = {item["action_key"]: item for item in live_coverage["supported"]}
    readonly_complete: list[dict] = []
    live_input_supported: list[dict] = []
    prepare_or_open_only: list[dict] = []
    production_final_blocked: list[dict] = []
    missing_adapter_profiles: list[dict] = []

    for action in action_catalog["actions"]:
        adapter = adapter_by_action.get(action["key"])
        item = {
            "action_key": action["key"],
            "surface_key": action["surface_key"],
            "operation": action["operation"],
            "label": action["label"],
            "requires_approval": action["requires_approval"],
            "required_inputs": action["required_inputs"],
            "target_url": action["target_url"],
            "adapter_key": adapter.get("adapter_key") if adapter else "",
        }
        if not adapter:
            item["development_status"] = "missing_adapter_profile"
            missing_adapter_profiles.append(item)
            continue
        if not action["requires_approval"]:
            item["development_status"] = "implemented_readonly"
            item["final_state_policy"] = "read_only"
            readonly_complete.append(item)
            continue
        item["final_state_policy"] = adapter["final_state_policy"]
        item["production_final_status"] = "not_approved_for_agent_execution"
        production_final_blocked.append(item)
        if action["key"] in live_supported:
            item["development_status"] = "implemented_live_input_no_final_submit"
            item["live_input_mode"] = live_supported[action["key"]]["live_input_mode"]
            live_input_supported.append(item)
        else:
            item["development_status"] = "prepare_or_open_only"
            item["live_input_mode"] = "not_implemented"
            prepare_or_open_only.append(item)

    return {
        "site_id": "google",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "baseline": "Google Home -> My Account -> registered subdomain -> approval URL",
            "read_surfaces": "implemented_readonly",
            "approval_actions": "prepare first, user approval required before any final external state change",
            "live_input": "supported actions may prefill non-secret values with no_final_submit",
            "final_execution": "blocked for agent unless a separate production adapter is explicitly approved",
        },
        "counts": {
            "actions": len(action_catalog["actions"]),
            "readonly_complete": len(readonly_complete),
            "approval_actions": action_catalog["counts"]["approval_actions"],
            "live_input_supported": len(live_input_supported),
            "prepare_or_open_only": len(prepare_or_open_only),
            "production_final_blocked": len(production_final_blocked),
            "missing_adapter_profiles": len(missing_adapter_profiles),
        },
        "readonly_complete": readonly_complete,
        "live_input_supported": live_input_supported,
        "prepare_or_open_only": prepare_or_open_only,
        "production_final_blocked": production_final_blocked,
        "missing_adapter_profiles": missing_adapter_profiles,
    }


def save_undeveloped_report(report: dict | None = None, path: Path | None = None) -> Path:
    report = report or build_undeveloped_report()
    return save_json_with_latest(report, UNDEVELOPED_REPORT_DIR, LATEST_UNDEVELOPED_REPORT, "google_work_undeveloped", path)

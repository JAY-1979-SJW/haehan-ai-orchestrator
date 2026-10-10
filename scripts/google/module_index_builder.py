"""Build and validate the Google module boundary index."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.google.common import domain_taxonomy, surfaces, workflows
from scripts.google.module_contracts import (
    GOOGLE_TOP_MODULE,
    SUBMODULE_OWNERS,
    SURFACE_IMPLEMENTATION_MODULES,
)


ROOT = Path(__file__).resolve().parents[2]


def _module_path(module_name: str) -> Path:
    parts = module_name.split(".")
    package_path = ROOT.joinpath(*parts)
    py_path = package_path.with_suffix(".py")
    if package_path.is_dir():
        return package_path
    return py_path


def _surface_keys_by_group() -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {key: [] for key in domain_taxonomy.GROUPS}
    for surface_key, group_key in domain_taxonomy.SURFACE_GROUPS.items():
        grouped.setdefault(group_key, []).append(surface_key)
    return {key: sorted(values) for key, values in grouped.items()}


def _surface_by_key() -> dict[str, dict[str, Any]]:
    return {item["key"]: item for item in surfaces.build_surface_catalog()["surfaces"]}


def _tab_gate(handling: str) -> str:
    if handling == "approval_required":
        return "explicit_user_approval"
    if handling == "no_final_submit":
        return "prepare_prefill_only_final_click_user"
    if handling == "secret_sensitive":
        return "secret_value_export_blocked"
    if handling in {"readonly_private", "readonly_sensitive"}:
        return "readonly_with_context_redaction"
    return "readonly_allowed"


def _domain_modules(taxonomy: dict[str, Any]) -> list[dict[str, Any]]:
    surface_catalog = _surface_by_key()
    modules: list[dict[str, Any]] = []
    for item in sorted(taxonomy["domains"], key=lambda row: (row["domain_group"], row["surface_key"])):
        surface_key = item["surface_key"]
        group_key = item["domain_group"]
        owner = SUBMODULE_OWNERS[group_key]
        implementation_module = SURFACE_IMPLEMENTATION_MODULES.get(surface_key, owner["module"])
        module_path = _module_path(implementation_module)
        page_tabs = item["page_tabs"]
        approval_tabs = [tab["tab_key"] for tab in page_tabs if tab["approval_required"]]
        no_final_submit_tabs = [tab["tab_key"] for tab in page_tabs if tab["handling"] == "no_final_submit"]
        secret_tabs = [tab["tab_key"] for tab in page_tabs if tab["handling"] == "secret_sensitive"]
        surface = surface_catalog[surface_key]
        modules.append(
            {
                "surface_key": surface_key,
                "label": item["label"],
                "domain_group": group_key,
                "section": item["section"],
                "subsection": item["subsection"],
                "owner_module": owner["module"],
                "implementation_module": implementation_module,
                "implementation_path": str(module_path.relative_to(ROOT)).replace("\\", "/"),
                "implementation_exists": module_path.exists(),
                "entry_url": surface["url"],
                "host": item["host"],
                "access_mode": surface["access_mode"],
                "status": surface["status"],
                "handling_policy": item["handling_policy"],
                "approval_level": item["approval_level"],
                "data_classification": item["data_classification"],
                "page_tab_count": len(page_tabs),
                "approval_tab_count": len(approval_tabs),
                "no_final_submit_tabs": no_final_submit_tabs,
                "secret_tabs": secret_tabs,
                "page_tabs": page_tabs,
                "user_can_request": item["user_can_request"],
                "approval_required_for": item["approval_required_for"],
                "not_allowed": item["not_allowed"],
            }
        )
    return modules


def _page_tab_modules(domain_modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    modules: list[dict[str, Any]] = []
    for domain in domain_modules:
        for index, tab in enumerate(domain["page_tabs"], start=1):
            handling = tab["handling"]
            modules.append(
                {
                    "key": f"{domain['surface_key']}.{tab['tab_key']}",
                    "surface_key": domain["surface_key"],
                    "tab_key": tab["tab_key"],
                    "label": tab["label"],
                    "domain_group": domain["domain_group"],
                    "owner_module": domain["implementation_module"],
                    "entry_url": domain["entry_url"],
                    "host": domain["host"],
                    "tab_order": index,
                    "handling": handling,
                    "state_change_possible": bool(tab["state_change_possible"]),
                    "approval_required": bool(tab["approval_required"]),
                    "secret_sensitive": handling == "secret_sensitive",
                    "no_final_submit": handling == "no_final_submit",
                    "gate": _tab_gate(handling),
                    "final_submit": tab["final_submit"],
                    "user_can_request": tab["user_can_request"],
                    "not_allowed": domain["not_allowed"],
                }
            )
    return modules


def _action_modules() -> list[dict[str, Any]]:
    action_catalog = workflows.build_action_catalog()
    modules: list[dict[str, Any]] = []
    for action in sorted(action_catalog["actions"], key=lambda row: (row["surface_key"], row["key"])):
        category = "approval" if action["requires_approval"] else "read"
        modules.append(
            {
                "key": action["key"],
                "surface_key": action["surface_key"],
                "label": action["label"],
                "operation": action["operation"],
                "target_url": action["target_url"],
                "risk": action["risk"],
                "category": category,
                "requires_approval": action["requires_approval"],
                "required_inputs": action["required_inputs"],
                "prepare_outputs": action["prepare_outputs"],
                "execute_mode": action["execute_mode"],
                "status": action["status"],
                "approval_phrase": action["approval_phrase"] if action["requires_approval"] else "",
                "gate": "explicit_user_approval" if action["requires_approval"] else "readonly_allowed",
            }
        )
    return modules


def _input_field_modules(action_modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    modules: list[dict[str, Any]] = []
    for action in action_modules:
        for index, field_name in enumerate(action["required_inputs"], start=1):
            lower = field_name.lower()
            secret_like = any(token in lower for token in ("secret", "token", "password", "key", "credential"))
            modules.append(
                {
                    "key": f"{action['key']}.{field_name}",
                    "action_key": action["key"],
                    "surface_key": action["surface_key"],
                    "field_name": field_name,
                    "field_order": index,
                    "category": "secret" if secret_like else ("approval_input" if action["requires_approval"] else "readonly_parameter"),
                    "ai_prefill_allowed": bool(action["requires_approval"] and not secret_like),
                    "user_review_required": bool(action["requires_approval"]),
                    "secret_value_allowed": False,
                    "validation_gate": "secret_value_blocked" if secret_like else "non_empty_and_surface_scoped",
                    "final_submit_dependency": "user_approval_required" if action["requires_approval"] else "none",
                }
            )
    return modules


def _final_control_modules(
    page_tab_modules: list[dict[str, Any]],
    action_modules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    modules: list[dict[str, Any]] = []
    for tab in page_tab_modules:
        if not tab["state_change_possible"]:
            continue
        modules.append(
            {
                "key": f"{tab['key']}.final_control",
                "source": "page_tab",
                "surface_key": tab["surface_key"],
                "tab_key": tab["tab_key"],
                "action_key": "",
                "label": tab["label"],
                "control_policy": "user_only" if tab["approval_required"] else "prefill_only",
                "ai_click_allowed": False,
                "user_click_required": True,
                "approval_phrase": "GOOGLE_APPROVED_EXECUTE" if tab["approval_required"] else "",
                "gate": tab["gate"],
            }
        )
    for action in action_modules:
        if not action["requires_approval"]:
            continue
        modules.append(
            {
                "key": f"{action['key']}.final_control",
                "source": "work_action",
                "surface_key": action["surface_key"],
                "tab_key": "",
                "action_key": action["key"],
                "label": action["label"],
                "control_policy": "user_only",
                "ai_click_allowed": False,
                "user_click_required": True,
                "approval_phrase": action["approval_phrase"],
                "gate": action["gate"],
            }
        )
    return modules


def _evidence_modules(action_modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    modules: list[dict[str, Any]] = []
    for action in action_modules:
        evidence_items = [
            "surface_context",
            "sanitized_input_summary",
            "before_state_snapshot",
            *action["prepare_outputs"],
        ]
        if action["requires_approval"]:
            evidence_items.extend(["approval_record", "final_result_snapshot"])
        else:
            evidence_items.append("readonly_result_snapshot")
        modules.append(
            {
                "key": f"{action['key']}.evidence",
                "action_key": action["key"],
                "surface_key": action["surface_key"],
                "category": "approval_evidence" if action["requires_approval"] else "readonly_evidence",
                "required_items": sorted(set(evidence_items)),
                "redaction_required": True,
                "store_raw_secret": False,
                "resume_support": "next_ai_can_resume_from_evidence",
            }
        )
    return modules


def build_google_module_index() -> dict[str, Any]:
    taxonomy = domain_taxonomy.build_google_domain_taxonomy()
    surface_catalog = surfaces.build_surface_catalog()
    catalog_keys = {item["key"] for item in surface_catalog["surfaces"]}
    taxonomy_keys = {item["surface_key"] for item in taxonomy["domains"]}
    grouped = _surface_keys_by_group()

    submodules: list[dict[str, Any]] = []
    for group_key, group in sorted(domain_taxonomy.GROUPS.items(), key=lambda item: item[1]["priority"]):
        owner = SUBMODULE_OWNERS[group_key]
        module_path = _module_path(owner["module"])
        surface_keys = grouped.get(group_key, [])
        domain_items = [item for item in taxonomy["domains"] if item["surface_key"] in surface_keys]
        approval_surfaces = [
            item["surface_key"]
            for item in domain_items
            if item["approval_level"] != "readonly_allowed"
        ]
        secret_surfaces = [
            item["surface_key"]
            for item in domain_items
            if item["data_classification"] == "secret_sensitive"
        ]
        submodules.append(
            {
                "group": group_key,
                "label": group["label"],
                "section": group["section"],
                "module": owner["module"],
                "module_path": str(module_path.relative_to(ROOT)).replace("\\", "/"),
                "module_exists": module_path.exists(),
                "router_tasks": owner["router_tasks"],
                "mode": owner["mode"],
                "status": owner["status"],
                "surface_count": len(surface_keys),
                "surfaces": surface_keys,
                "approval_surface_count": len(approval_surfaces),
                "approval_surfaces": sorted(approval_surfaces),
                "secret_surfaces": sorted(secret_surfaces),
            }
        )

    duplicate_surfaces = sorted(
        key for key in domain_taxonomy.SURFACE_GROUPS if list(domain_taxonomy.SURFACE_GROUPS).count(key) > 1
    )
    missing_catalog_surfaces = sorted(taxonomy_keys - catalog_keys)
    missing_taxonomy_surfaces = sorted(catalog_keys - taxonomy_keys)
    missing_owner_groups = sorted(set(domain_taxonomy.GROUPS) - set(SUBMODULE_OWNERS))
    missing_modules = [item["group"] for item in submodules if not item["module_exists"]]
    domain_modules = _domain_modules(taxonomy)
    page_tab_modules = _page_tab_modules(domain_modules)
    action_modules = _action_modules()
    input_field_modules = _input_field_modules(action_modules)
    final_control_modules = _final_control_modules(page_tab_modules, action_modules)
    evidence_modules = _evidence_modules(action_modules)
    missing_domain_implementations = [
        item["surface_key"] for item in domain_modules if not item["implementation_exists"]
    ]
    domain_modules_without_tabs = [
        item["surface_key"] for item in domain_modules if item["page_tab_count"] <= 0
    ]
    action_surface_keys = {item["surface_key"] for item in action_modules}
    domain_surface_keys = {item["surface_key"] for item in domain_modules}
    missing_action_surface_modules = sorted(action_surface_keys - domain_surface_keys)
    domain_modules_without_read_action = sorted(
        domain_surface_keys - {item["surface_key"] for item in action_modules if item["category"] == "read"}
    )
    page_tab_modules_without_gate = [item["key"] for item in page_tab_modules if not item["gate"]]
    input_fields_allowing_secret_values = [
        item["key"] for item in input_field_modules if item["secret_value_allowed"]
    ]
    final_controls_ai_click_allowed = [
        item["key"] for item in final_control_modules if item["ai_click_allowed"]
    ]
    evidence_modules_allowing_raw_secret = [
        item["key"] for item in evidence_modules if item["store_raw_secret"]
    ]

    ok = not (
        duplicate_surfaces
        or missing_catalog_surfaces
        or missing_taxonomy_surfaces
        or missing_owner_groups
        or missing_modules
        or missing_domain_implementations
        or domain_modules_without_tabs
        or missing_action_surface_modules
        or domain_modules_without_read_action
        or page_tab_modules_without_gate
        or input_fields_allowing_secret_values
        or final_controls_ai_click_allowed
        or evidence_modules_allowing_raw_secret
    )
    return {
        "ok": ok,
        "site": "google",
        "mode": "dry_run_no_browser_write",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "top_module": GOOGLE_TOP_MODULE,
        "submodule_count": len(submodules),
        "domain_module_count": len(domain_modules),
        "page_tab_module_count": len(page_tab_modules),
        "work_action_module_count": len(action_modules),
        "input_field_module_count": len(input_field_modules),
        "final_control_module_count": len(final_control_modules),
        "evidence_module_count": len(evidence_modules),
        "surface_count": len(catalog_keys),
        "taxonomy_surface_count": len(taxonomy_keys),
        "approval_boundary": GOOGLE_TOP_MODULE["final_action_policy"],
        "login_boundary": GOOGLE_TOP_MODULE["session_policy"],
        "secret_boundary": GOOGLE_TOP_MODULE["secret_policy"],
        "submodules": submodules,
        "domain_modules": domain_modules,
        "page_tab_modules": page_tab_modules,
        "work_action_modules": action_modules,
        "input_field_modules": input_field_modules,
        "final_control_modules": final_control_modules,
        "evidence_modules": evidence_modules,
        "checks": {
            "catalog_matches_taxonomy": not missing_catalog_surfaces and not missing_taxonomy_surfaces,
            "all_groups_have_owner": not missing_owner_groups,
            "all_owner_modules_exist": not missing_modules,
            "all_domain_modules_have_implementation": not missing_domain_implementations,
            "all_domain_modules_have_page_tabs": not domain_modules_without_tabs,
            "all_action_modules_have_domain_module": not missing_action_surface_modules,
            "all_domain_modules_have_read_action": not domain_modules_without_read_action,
            "all_page_tab_modules_have_gate": not page_tab_modules_without_gate,
            "no_input_field_allows_secret_value": not input_fields_allowing_secret_values,
            "no_final_control_allows_ai_click": not final_controls_ai_click_allowed,
            "no_evidence_module_stores_raw_secret": not evidence_modules_allowing_raw_secret,
            "duplicate_surface_ownership": duplicate_surfaces,
            "missing_catalog_surfaces": missing_catalog_surfaces,
            "missing_taxonomy_surfaces": missing_taxonomy_surfaces,
            "missing_owner_groups": missing_owner_groups,
            "missing_modules": missing_modules,
            "missing_domain_implementations": missing_domain_implementations,
            "domain_modules_without_tabs": domain_modules_without_tabs,
            "missing_action_surface_modules": missing_action_surface_modules,
            "domain_modules_without_read_action": domain_modules_without_read_action,
            "page_tab_modules_without_gate": page_tab_modules_without_gate,
            "input_fields_allowing_secret_values": input_fields_allowing_secret_values,
            "final_controls_ai_click_allowed": final_controls_ai_click_allowed,
            "evidence_modules_allowing_raw_secret": evidence_modules_allowing_raw_secret,
        },
    }

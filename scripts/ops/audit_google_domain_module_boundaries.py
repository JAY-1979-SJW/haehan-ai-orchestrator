"""Audit locked Google domain/module/page/action/input/control/evidence boundaries."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXPECTED_COUNTS = {
    "submodule_count": 10,
    "domain_module_count": 50,
    "page_tab_module_count": 185,
    "work_action_module_count": 96,
    "input_field_module_count": 140,
    "final_control_module_count": 143,
    "evidence_module_count": 96,
    "surface_count": 50,
}


def audit() -> dict[str, Any]:
    from scripts.google import module_check

    payload = module_check.build_google_module_index()
    failures: list[str] = []
    warnings: list[str] = []

    if not payload.get("ok"):
        failures.append("google module index ok=false")

    for key, expected in EXPECTED_COUNTS.items():
        actual = payload.get(key)
        if actual != expected:
            failures.append(f"{key} {actual} != {expected}")

    checks = payload.get("checks") or {}
    required_true_checks = (
        "catalog_matches_taxonomy",
        "all_groups_have_owner",
        "all_owner_modules_exist",
        "all_domain_modules_have_implementation",
        "all_domain_modules_have_page_tabs",
        "all_action_modules_have_domain_module",
        "all_domain_modules_have_read_action",
        "all_page_tab_modules_have_gate",
        "no_input_field_allows_secret_value",
        "no_final_control_allows_ai_click",
        "no_evidence_module_stores_raw_secret",
    )
    for key in required_true_checks:
        if checks.get(key) is not True:
            failures.append(f"check failed: {key}")

    final_controls = payload.get("final_control_modules") or []
    bad_controls = [
        item["key"]
        for item in final_controls
        if item.get("ai_click_allowed") or not item.get("user_click_required")
    ]
    if bad_controls:
        failures.append("unsafe final controls: " + ", ".join(bad_controls[:20]))

    evidence_modules = payload.get("evidence_modules") or []
    raw_secret_evidence = [item["key"] for item in evidence_modules if item.get("store_raw_secret")]
    if raw_secret_evidence:
        failures.append("raw secret evidence modules: " + ", ".join(raw_secret_evidence[:20]))

    approval_actions = [
        item for item in payload.get("work_action_modules", [])
        if item.get("requires_approval")
    ]
    control_keys = {item["key"] for item in final_controls}
    missing_controls = [
        f"{action['key']}.final_control"
        for action in approval_actions
        if f"{action['key']}.final_control" not in control_keys
    ]
    if missing_controls:
        failures.append("approval actions missing final controls: " + ", ".join(missing_controls[:20]))

    secret_tabs = [
        item["key"]
        for item in payload.get("page_tab_modules", [])
        if item.get("secret_sensitive") and item.get("gate") != "secret_value_export_blocked"
    ]
    if secret_tabs:
        failures.append("secret tabs without export block gate: " + ", ".join(secret_tabs[:20]))

    for key in ("domain_modules", "page_tab_modules", "work_action_modules"):
        if not payload.get(key):
            failures.append(f"{key} empty")

    return {
        "ok": not failures,
        "counts": {key: payload.get(key) for key in EXPECTED_COUNTS},
        "failures": failures,
        "warnings": warnings,
        "lock": {
            "top_module": payload.get("top_module", {}).get("key"),
            "login_boundary": payload.get("login_boundary"),
            "approval_boundary": payload.get("approval_boundary"),
            "secret_boundary": payload.get("secret_boundary"),
        },
    }


def main() -> int:
    report = audit()
    try:
        from scripts.google import work_records

        work_records.checkpoint(
            step=(
                "google domain module boundary audit: "
                + ("PASS" if report["ok"] else "FAIL")
                + f", counts={report['counts']}"
            ),
            command="python scripts/ops/audit_google_domain_module_boundaries.py",
            verification=(
                "RESULT="
                + ("PASS_GOOGLE_DOMAIN_MODULE_BOUNDARIES" if report["ok"] else "FAIL_GOOGLE_DOMAIN_MODULE_BOUNDARIES")
            ),
            report="data/runtime/ai_work_records/google/latest.json",
            touched=[
                "scripts/ops/audit_google_domain_module_boundaries.py",
                "scripts/google/work_records.py",
            ],
            next_step="keep google boundary changes inside google lane and rerun boundary audit",
        )
    except Exception as exc:
        report.setdefault("warnings", []).append(f"work_record_checkpoint_failed:{type(exc).__name__}")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(
        "RESULT="
        + ("PASS_GOOGLE_DOMAIN_MODULE_BOUNDARIES" if report["ok"] else "FAIL_GOOGLE_DOMAIN_MODULE_BOUNDARIES")
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

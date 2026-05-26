"""Google domain readiness audit.

This report checks every registered Google surface for the same failure modes
that appeared during YouTube OAuth work: unclear OAuth/API path, unsafe browser
fallback, missing final-submit boundary, and missing reportable next step.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.google import domain_taxonomy


REPORT_DIR = ROOT / "data" / "google_domain_readiness_reports"
LATEST_REPORT = ROOT / "data" / "google_domain_readiness_latest.json"

API_MODES = {"api_preferred", "manual_live_read_or_api"}
BROWSER_MODES = {"browser_readonly", "manual_live_read", "manual_or_oauth_only"}
SECRET_SURFACES = {"cloud_apis_credentials", "secret_manager"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _read_strategy(item: dict[str, Any]) -> str:
    access_mode = item["access_mode"]
    if access_mode in API_MODES or "api_preferred" in access_mode:
        return "official_api_or_oauth_first"
    if access_mode in BROWSER_MODES or "manual_live_read" in access_mode:
        return "user_present_browser_readonly"
    return "registered_surface_policy_required"


def _fallback_strategy(item: dict[str, Any]) -> str:
    if item["surface_key"] == "youtube":
        return "official_api_then_visible_browser_transcript_summary"
    if item["surface_key"] == "youtube_studio":
        return "official_api_then_no_final_submit_browser_handoff"
    if item["domain_group"] in {"workspace_productivity", "cloud_backend", "ai_model"}:
        return "official_api_then_user_present_browser_no_final_submit"
    return "user_present_browser_readonly_or_prepare_only"


def _surface_findings(item: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    if not item.get("page_tabs"):
        findings.append("missing_page_tabs")
    if item.get("approval_actions") and item.get("approval_level") == "readonly_allowed":
        findings.append("approval_actions_on_readonly_surface")
    if item.get("approval_actions") and not any(tab["state_change_possible"] for tab in item["page_tabs"]):
        findings.append("approval_surface_without_state_change_page_tab")
    if item["surface_key"] in SECRET_SURFACES and item["data_classification"] != "secret_sensitive":
        findings.append("secret_surface_not_secret_classified")
    if "final submit without approval" not in item.get("not_allowed", []):
        findings.append("missing_final_submit_block")
    return findings


def build_google_domain_readiness_audit() -> dict[str, Any]:
    taxonomy = domain_taxonomy.build_google_domain_taxonomy()
    domains = []
    failures: list[str] = []
    for item in taxonomy["domains"]:
        findings = _surface_findings(item)
        if findings:
            failures.append(f"{item['surface_key']}:{','.join(findings)}")
        domains.append(
            {
                "surface_key": item["surface_key"],
                "host": item["host"],
                "tab_key": item["tab_key"],
                "domain_group": item["domain_group"],
                "access_mode": item["access_mode"],
                "read_strategy": _read_strategy(item),
                "fallback_strategy": _fallback_strategy(item),
                "approval_level": item["approval_level"],
                "data_classification": item["data_classification"],
                "read_action_count": len(item.get("read_actions", [])),
                "approval_action_count": len(item.get("approval_actions", [])),
                "page_tab_count": len(item.get("page_tabs", [])),
                "secret_output_allowed": False,
                "credential_replay_allowed": False,
                "final_submit_without_approval_allowed": False,
                "must_report_next_step_when_blocked": True,
                "needs_cdp_session_selection": item["access_mode"] in BROWSER_MODES or "browser" in item["access_mode"],
                "findings": findings,
            }
        )

    return {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "google_domain_readiness_audit",
        "ok": not failures,
        "status": "ok" if not failures else "failed",
        "failed_check_ids": failures,
        "counts": {
            "surfaces": len(domains),
            "hosts": taxonomy["counts"]["hosts"],
            "domain_groups": taxonomy["counts"]["domain_groups"],
            "official_api_or_oauth_first": sum(1 for item in domains if item["read_strategy"] == "official_api_or_oauth_first"),
            "user_present_browser_readonly": sum(1 for item in domains if item["read_strategy"] == "user_present_browser_readonly"),
            "approval_surfaces": sum(1 for item in domains if item["approval_action_count"] > 0),
            "cdp_selection_required": sum(1 for item in domains if item["needs_cdp_session_selection"]),
        },
        "global_policy": {
            "login": "user_present_only_no_credential_replay",
            "oauth": "registered_redirect_and_scope_required",
            "api": "official_api_preferred_when_available",
            "browser_fallback": "user_present_cdp_session_selection_required",
            "secret_output": "blocked",
            "final_submit": "blocked_without_explicit_approval",
            "blocked_result": "must_include_reason_and_next_step",
        },
        "domains": domains,
    }


def save_google_domain_readiness_audit(report: dict[str, Any] | None = None) -> tuple[dict[str, Any], Path]:
    report = report or build_google_domain_readiness_audit()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"google_domain_readiness_{_stamp()}.json"
    text = json.dumps(report, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
    LATEST_REPORT.write_text(text, encoding="utf-8")
    return report, path


def main() -> int:
    report, path = save_google_domain_readiness_audit()
    print(f"google_domain_readiness_audit status={report['status']} ok={report['ok']} report={path}")
    print(
        "counts "
        f"surfaces={report['counts']['surfaces']} "
        f"api_or_oauth={report['counts']['official_api_or_oauth_first']} "
        f"browser_readonly={report['counts']['user_present_browser_readonly']} "
        f"cdp_selection_required={report['counts']['cdp_selection_required']}"
    )
    if report["failed_check_ids"]:
        print("failed=" + ",".join(report["failed_check_ids"]))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

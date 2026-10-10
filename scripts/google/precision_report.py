"""Build a domain/page precision verification report from Google evidence."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.google.common import live_inputs, subdomain_logic, tab_logic, workflows
from scripts.google import live_surface_explorer
from scripts.google.ai_usage_labels import build_google_ai_usage_labels, label_for_surface

ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "docs" / "reports"
DATA_REPORT_DIR = ROOT / "data" / "google_precision_reports"
LATEST_REPORT = ROOT / "data" / "google_precision_report_latest.json"


def _utc() -> str:
    return datetime.now(UTC).isoformat()


def _load_manifest() -> dict[str, Any]:
    source = live_inputs.LATEST_LIVE_INPUT_MANIFEST
    if not source.exists():
        return {"status": "missing", "items": [], "counts": {"total": 0, "filled": 0, "blocked": 0, "failed": 0}}
    return json.loads(source.read_text(encoding="utf-8"))


def _load_latest_live_input_results_by_action() -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    input_dir = live_inputs.LIVE_INPUT_DIR
    if not input_dir.exists():
        return results
    for path in sorted(input_dir.glob("google_live_input_*.json"), key=lambda item: item.stat().st_mtime):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - 리포트 집계용 JSON 파일 파싱 실패 시 해당 파일만 건너뛰고 계속(continue) - 읽기전용 집계 스크립트, 손상된 파일 하나가 전체 리포트를 막지 않도록 하는 안전한 폴백
            continue
        action_key = item.get("action_key")
        if action_key:
            item["result_path"] = str(path)
            results[action_key] = item
    return results


LIVE_FILL_SAFE_NO_FINAL_STATUSES = {
    "filled_no_final_submit",
    "opened_no_final_submit",
    "opened_no_upload_input",
}


def _is_live_fill_safe_no_final(item: dict[str, Any]) -> bool:
    return item.get("status") in LIVE_FILL_SAFE_NO_FINAL_STATUSES and not item.get("state_change_final_button_clicked")


def build_google_precision_report() -> dict[str, Any]:
    live_logic = live_surface_explorer.build_google_surface_live_logic()
    subdomain_catalog = subdomain_logic.build_google_subdomain_logic_catalog()
    tab_catalog = tab_logic.build_all_tab_logic_catalog()
    action_catalog = workflows.build_action_catalog()
    _load_manifest()
    live_input_results = _load_latest_live_input_results_by_action()
    live_input_coverage = live_inputs.build_live_input_coverage()
    ai_labels = build_google_ai_usage_labels()
    live_fill_total = len(live_input_results)
    if live_fill_total == 0:
        live_fill_total = int(live_input_coverage.get("counts", {}).get("live_input_supported", 0))

    actions_by_surface: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for action in action_catalog["actions"]:
        actions_by_surface[action["surface_key"]].append(action)

    fill_by_action = {
        action_key: {
            "action_key": action_key,
            "status": item.get("status", ""),
            "result_path": item.get("result_path", ""),
            "filled_fields": item.get("filled_fields", []),
            "skipped_fields": item.get("skipped_fields", []),
            "warnings": item.get("warnings", []),
            "final_clicked": item.get("state_change_final_button_clicked", False),
        }
        for action_key, item in live_input_results.items()
    }
    surfaces = []
    for surface in live_logic["surfaces"]:
        surface_key = surface["surface_key"]
        actions = actions_by_surface.get(surface_key, [])
        fills = [fill_by_action[action["key"]] for action in actions if action["key"] in fill_by_action]
        status = "pass"
        findings: list[str] = []
        if not surface.get("live_verified_readonly"):
            status = "fail"
            findings.append("read-only live verification missing")
        if any(item.get("final_clicked") for item in fills):
            status = "fail"
            findings.append("final click was recorded")
        if fills and any(not _is_live_fill_safe_no_final(item) for item in fills):
            status = "warn" if status == "pass" else status
            findings.append("some live-fill items did not fully complete")
        if surface.get("approval_actions") and not surface.get("observed_risk_controls"):
            findings.append("approval actions exist; final controls may be hidden until deeper page state")

        surfaces.append(
            {
                "surface_key": surface_key,
                "tab_key": surface["tab_key"],
                "host": surface["host"],
                "label": surface["label"],
                "status": status,
                "live_status": surface["live_status"],
                "title": surface.get("title", ""),
                "observed_headings": surface.get("observed_headings", []),
                "observed_control_count": surface.get("observed_control_count", 0),
                "observed_input_count": surface.get("observed_input_count", 0),
                "observed_risk_control_count": len(surface.get("observed_risk_controls", [])),
                "read_actions": surface.get("read_actions", []),
                "approval_actions": surface.get("approval_actions", []),
                "live_fill_results": fills,
                "ai_usage_label": label_for_surface(surface_key) if surface["tab_key"] == "ai" else {},
                "findings": findings,
            }
        )

    hosts: dict[str, Any] = {}
    for item in subdomain_catalog["subdomains"]:
        host = item["host"]
        host_surfaces = [surface for surface in surfaces if surface["host"] == host]
        hosts[host] = {
            "host": host,
            "sso_service_key": item.get("sso_service_key", ""),
            "surface_count": len(host_surfaces),
            "visited_count": sum(1 for surface in host_surfaces if surface["live_status"] == "visited"),
            "risk_boundary": item.get("risk_boundary", ""),
            "read_action_count": len(item.get("read_actions", [])),
            "approval_action_count": len(item.get("approval_actions", [])),
            "status": "pass"
            if host_surfaces and all(surface["status"] in {"pass", "warn"} for surface in host_surfaces)
            else "warn",
            "surfaces": [surface["surface_key"] for surface in host_surfaces],
        }

    return {
        "site_id": "google",
        "generated_at": _utc(),
        "scope": {
            "surfaces": live_logic["surface_count"],
            "hosts": len(hosts),
            "tabs": tab_catalog["tab_count"],
            "actions": action_catalog["counts"]["actions"],
            "approval_actions": action_catalog["counts"]["approval_actions"],
        },
        "counts": {
            "live_verified_surfaces": live_logic["live_verified_count"],
            "surface_pass": sum(1 for surface in surfaces if surface["status"] == "pass"),
            "surface_warn": sum(1 for surface in surfaces if surface["status"] == "warn"),
            "surface_fail": sum(1 for surface in surfaces if surface["status"] == "fail"),
            "live_fill_total": live_fill_total,
            "live_fill_completed": sum(1 for item in live_input_results.values() if _is_live_fill_safe_no_final(item)),
            "live_fill_failed": sum(1 for item in live_input_results.values() if item.get("status") == "failed"),
            "final_clicked_count": sum(
                1 for item in live_input_results.values() if item.get("state_change_final_button_clicked")
            ),
        },
        "policy": {
            "read_only_surface_check": "direct_cdp_no_click_no_input",
            "live_fill": "no_final_submit",
            "state_change_final_click": "blocked",
            "secret_export": "blocked",
        },
        "ai_usage_labels": ai_labels,
        "hosts": hosts,
        "surfaces": surfaces,
        "source_artifacts": {
            "surface_live_latest": str(live_surface_explorer.LATEST_REPORT),
            "live_input_manifest_latest": str(live_inputs.LATEST_LIVE_INPUT_MANIFEST),
            "live_input_coverage_latest": str(live_inputs.LATEST_LIVE_INPUT_COVERAGE),
            "live_input_results_dir": str(live_inputs.LIVE_INPUT_DIR),
            "precision_report_latest": str(LATEST_REPORT),
        },
    }


def save_google_precision_report(report: dict[str, Any] | None = None) -> tuple[dict[str, Any], Path, Path]:
    report = report or build_google_precision_report()
    DATA_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    json_path = DATA_REPORT_DIR / f"google_precision_report_{timestamp}.json"
    md_path = REPORT_DIR / f"google_precision_report_{timestamp}.md"
    text = json.dumps(report, ensure_ascii=False, indent=2)
    json_path.write_text(text, encoding="utf-8")
    LATEST_REPORT.write_text(text, encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    return report, json_path, md_path


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Google Domain/Page Precision Verification Report",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Surfaces: {report['scope']['surfaces']}",
        f"- Hosts: {report['scope']['hosts']}",
        f"- Live verified surfaces: {report['counts']['live_verified_surfaces']}",
        f"- Surface status: pass={report['counts']['surface_pass']}, warn={report['counts']['surface_warn']}, fail={report['counts']['surface_fail']}",
        f"- Live-fill: total={report['counts']['live_fill_total']}, completed={report['counts']['live_fill_completed']}, failed={report['counts']['live_fill_failed']}",
        f"- Final clicked: {report['counts']['final_clicked_count']}",
        "",
        "## Google AI Usage Labels",
        "",
    ]
    for key, label in report["ai_usage_labels"]["labels"].items():
        lines.extend(
            [
                f"### {label['service']}",
                f"- Billing label: `{label['billing_label']}`",
                f"- Free: {label['free_summary']}",
                f"- Limits: {label['usage_limit_summary']}",
                f"- Paid: {label['paid_summary']}",
                f"- Approval required: {', '.join(label['approval_required_for'])}",
                "",
            ]
        )
    lines.extend(["## Host Summary", ""])
    for host, item in sorted(report["hosts"].items()):
        lines.append(
            f"- `{host}`: status={item['status']}, surfaces={item['surface_count']}, "
            f"visited={item['visited_count']}, read={item['read_action_count']}, approval={item['approval_action_count']}"
        )
    lines.extend(["", "## Surface Summary", ""])
    for surface in report["surfaces"]:
        lines.append(
            f"- `{surface['surface_key']}` ({surface['host']}): {surface['status']}, "
            f"live={surface['live_status']}, controls={surface['observed_control_count']}, "
            f"inputs={surface['observed_input_count']}, risk_controls={surface['observed_risk_control_count']}"
        )
        if surface["findings"]:
            lines.append(f"  - Findings: {'; '.join(surface['findings'])}")
    return "\n".join(lines) + "\n"


def print_google_precision_summary(report: dict[str, Any], json_path: Path, md_path: Path) -> None:
    print("=" * 60)
    print("Google precision verification report")
    print("=" * 60)
    print(f"surfaces: {report['scope']['surfaces']}")
    print(f"hosts: {report['scope']['hosts']}")
    print(f"live_verified: {report['counts']['live_verified_surfaces']}")
    print(f"surface_pass: {report['counts']['surface_pass']}")
    print(f"surface_warn: {report['counts']['surface_warn']}")
    print(f"surface_fail: {report['counts']['surface_fail']}")
    print(f"live_fill_completed: {report['counts']['live_fill_completed']}")
    print(f"final_clicked: {report['counts']['final_clicked_count']}")
    print(f"json: {json_path}")
    print(f"markdown: {md_path}")
    print(f"latest: {LATEST_REPORT}")


def main() -> int:
    report, json_path, md_path = save_google_precision_report()
    print_google_precision_summary(report, json_path, md_path)
    return 0 if report["counts"]["surface_fail"] == 0 and report["counts"]["final_clicked_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

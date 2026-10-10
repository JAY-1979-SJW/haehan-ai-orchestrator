"""Android app development verification report from Google evidence."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.google.android_app_dev_labels import build_android_app_dev_labels, label_for_surface
from scripts.google.precision_report import build_google_precision_report
from scripts.google.common.report_io import print_report_summary, save_json_md_report

ROOT = Path(__file__).resolve().parents[2]
DATA_REPORT_DIR = ROOT / "data" / "google_android_app_dev_reports"
LATEST_REPORT = ROOT / "data" / "google_android_app_dev_report_latest.json"
DOC_REPORT_DIR = ROOT / "docs" / "reports"

PRIMARY_SURFACES = {
    "android_developers",
    "play_console",
    "firebase_console",
    "cloud_console",
    "google_developers",
    "chrome_developers",
    "cloud_apis_credentials",
    "cloud_iam",
    "cloud_run",
    "cloud_storage",
    "cloud_logging",
    "cloud_monitoring",
    "vertex_ai",
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_android_app_dev_report() -> dict[str, Any]:
    precision = build_google_precision_report()
    labels = build_android_app_dev_labels()
    surfaces = [
        {
            **surface,
            "android_app_dev_label": label_for_surface(surface["surface_key"]),
        }
        for surface in precision["surfaces"]
        if surface["surface_key"] in PRIMARY_SURFACES
    ]
    return {
        "site_id": "google",
        "domain_group": "android_app_development",
        "generated_at": _utc(),
        "counts": {
            "surfaces": len(surfaces),
            "live_verified": sum(1 for surface in surfaces if surface.get("live_status") == "visited"),
            "pass": sum(1 for surface in surfaces if surface.get("status") == "pass"),
            "warn": sum(1 for surface in surfaces if surface.get("status") == "warn"),
            "fail": sum(1 for surface in surfaces if surface.get("status") == "fail"),
            "final_clicked": sum(
                1
                for surface in surfaces
                for item in surface.get("live_fill_results", [])
                if item.get("final_clicked")
            ),
        },
        "labels": labels,
        "surfaces": surfaces,
        "source_artifacts": {
            "precision_report_latest": str(ROOT / "data" / "google_precision_report_latest.json"),
            "android_app_dev_report_latest": str(LATEST_REPORT),
        },
    }


def save_android_app_dev_report(report: dict[str, Any] | None = None) -> tuple[dict[str, Any], Path, Path]:
    report = report or build_android_app_dev_report()
    json_path, md_path = save_json_md_report(
        report, DATA_REPORT_DIR, DOC_REPORT_DIR, LATEST_REPORT, "google_android_app_dev_report", _render_markdown
    )
    return report, json_path, md_path


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Google Android App Development Verification Report",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Surfaces: {report['counts']['surfaces']}",
        f"- Live verified: {report['counts']['live_verified']}",
        f"- Status: pass={report['counts']['pass']}, warn={report['counts']['warn']}, fail={report['counts']['fail']}",
        f"- Final clicked: {report['counts']['final_clicked']}",
        "",
        "## Stage Labels",
        "",
    ]
    for stage in report["labels"]["stages"]:
        lines.append(f"- `{stage['stage']}`: {stage['output']} ({', '.join(stage['surface_keys'])})")
    lines.extend(["", "## Cost And Usage Labels", ""])
    for key, label in report["labels"]["labels"].items():
        lines.extend(
            [
                f"### {label['service']}",
                f"- Stage: `{label['stage']}`",
                f"- Cost label: `{label['cost_label']}`",
                f"- Free: {label['free_summary']}",
                f"- Paid: {label.get('paid_summary', '')}",
                f"- Limits: {label.get('usage_limit_summary', '')}",
                f"- Approval required: {', '.join(label['approval_required_for'])}",
                "",
            ]
        )
    lines.extend(["## Surface Verification", ""])
    for surface in report["surfaces"]:
        lines.append(
            f"- `{surface['surface_key']}` ({surface['host']}): {surface['status']}, "
            f"live={surface['live_status']}, controls={surface['observed_control_count']}, "
            f"inputs={surface['observed_input_count']}, risk_controls={surface['observed_risk_control_count']}"
        )
    return "\n".join(lines) + "\n"


def print_android_app_dev_summary(report: dict[str, Any], json_path: Path, md_path: Path) -> None:
    fields = [(key, key) for key in ("surfaces", "live_verified", "pass", "warn", "fail", "final_clicked")]
    print_report_summary(
        "Google Android app development report", report["counts"], fields, json_path, md_path, LATEST_REPORT
    )


def main() -> int:
    report, json_path, md_path = save_android_app_dev_report()
    print_android_app_dev_summary(report, json_path, md_path)
    return 0 if report["counts"]["fail"] == 0 and report["counts"]["final_clicked"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

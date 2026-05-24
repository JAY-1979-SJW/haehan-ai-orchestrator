"""Read-only audit for the locked Google Cloud module baseline."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASELINE = ROOT / "docs" / "baseline" / "GOOGLE_CLOUD_MODULE_BASELINE.md"

CLOUD_SURFACES = (
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
)

CLOUD_APPROVAL_ACTIONS = (
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

CLOUD_LIVE_INPUT_ACTIONS = (
    "cloud_create_api_credential",
    "cloud_iam_change_role",
)

REQUIRED_PHRASES = (
    "Status: LOCKED",
    "Baseline ID: GOOGLE-CLOUD-MODULE-BASELINE-01",
    "Cloud surfaces: 15",
    "Cloud actions: 29",
    "Cloud read actions: 15",
    "Cloud approval actions: 14",
    "Cloud hosts: `console.cloud.google.com`",
    "Cloud live input supported actions: 2",
    "Cloud prepare/open-only approval actions: 12",
    "`vertex_ai` also uses `console.cloud.google.com`, but it belongs to the `ai`",
    "raw project id, service account, key material, billing account, secret value,",
    "actual `gcloud` execution",
    "actual Google Cloud API execution",
    "browser final click automation",
)


def _missing(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase not in text]


def audit() -> tuple[bool, list[str]]:
    failures: list[str] = []
    if not BASELINE.exists():
        return False, ["docs/baseline/GOOGLE_CLOUD_MODULE_BASELINE.md missing"]

    text = BASELINE.read_text(encoding="utf-8", errors="replace")
    missing = _missing(text, REQUIRED_PHRASES)
    if missing:
        failures.append("Google Cloud baseline missing phrase(s): " + ", ".join(missing))

    from scripts.google.live_inputs import build_live_input_coverage
    from scripts.google.tab_registry import build_google_tab_summary

    summary = build_google_tab_summary()
    cloud = next((tab for tab in summary["tabs"] if tab["key"] == "cloud"), None)
    if cloud is None:
        failures.append("Google cloud tab missing")
        return False, failures

    surfaces = tuple(surface["key"] for surface in cloud["surfaces"])
    if surfaces != CLOUD_SURFACES:
        failures.append("Cloud surfaces changed: " + ", ".join(surfaces))

    approval_actions = tuple(action["key"] for action in cloud["actions"] if action["requires_approval"])
    if approval_actions != CLOUD_APPROVAL_ACTIONS:
        failures.append("Cloud approval actions changed: " + ", ".join(approval_actions))

    expected_counts = {
        "surface_count": 15,
        "action_count": 29,
        "read_action_count": 15,
        "approval_action_count": 14,
    }
    for key, expected in expected_counts.items():
        if cloud.get(key) != expected:
            failures.append(f"Cloud count mismatch {key}: expected {expected}, got {cloud.get(key)}")

    if cloud.get("hosts") != ["console.cloud.google.com"]:
        failures.append(f"Cloud hosts changed: {cloud.get('hosts')!r}")

    if summary["host_warnings"]:
        failures.append(f"Google host warnings must stay zero, got {len(summary['host_warnings'])}")

    live_supported = {item["action_key"] for item in build_live_input_coverage()["supported"]}
    cloud_live = tuple(action["key"] for action in cloud["actions"] if action["key"] in live_supported)
    if cloud_live != CLOUD_LIVE_INPUT_ACTIONS:
        failures.append("Cloud live-input-supported actions changed: " + ", ".join(cloud_live))

    if len(set(CLOUD_APPROVAL_ACTIONS) - set(cloud_live)) != 12:
        failures.append("Cloud prepare/open-only approval action count must be 12")

    return not failures, failures or [
        "GOOGLE_CLOUD_MODULE_BASELINE exists and is locked",
        "Cloud owns 15 surfaces and 29 actions",
        "Cloud approval and live-input boundaries are preserved",
        "Cloud host boundary is console.cloud.google.com",
    ]


def main() -> int:
    ok, findings = audit()
    for finding in findings:
        print(f"[{'PASS' if ok else 'FAIL'}] {finding}")
    print(f"RESULT={'PASS_GOOGLE_CLOUD_MODULE_BASELINE_CONTRACT' if ok else 'FAIL_GOOGLE_CLOUD_MODULE_BASELINE_CONTRACT'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())


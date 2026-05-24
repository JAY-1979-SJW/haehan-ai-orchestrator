"""Audit Google Cloud router compatibility without live Cloud execution."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CLOUD_SERVICES = {
    "console": "cloud_console",
    "maps_platform": "maps_platform",
    "api_credentials": "cloud_apis_credentials",
    "iam": "cloud_iam",
    "billing": "cloud_billing",
    "run": "cloud_run",
    "compute": "compute_engine",
    "storage": "cloud_storage",
    "bigquery": "bigquery",
    "gke": "gke",
    "sql": "cloud_sql",
    "pubsub": "pubsub",
    "secret_manager": "secret_manager",
    "logging": "cloud_logging",
    "monitoring": "cloud_monitoring",
}

FORBIDDEN_EXECUTION_FLAGS = {
    "gcloud",
    "google_cloud_api",
    "browser_final_click",
    "iam_change",
    "billing_change",
    "secret_value_access",
    "deploy_or_resource_mutation",
}

FORBIDDEN_SOURCE_PATTERNS = (
    "subprocess.run([\"gcloud\"",
    "subprocess.run(['gcloud'",
    "subprocess.Popen",
    "googleapiclient.discovery.build",
    "from google.cloud",
    "import google.cloud",
    "sync_playwright",
    ".click(",
    "page.click(",
    "set_input_files",
    "keyboard.press",
)

SCAN_PATHS = (
    ROOT / "scripts" / "google" / "cloud",
)


def _audit_router_summary() -> list[str]:
    from scripts.google.cloud import router

    failures: list[str] = []
    summary = router.run_cloud("summary")
    expected = {
        "surface_count": 15,
        "action_count": 29,
        "read_action_count": 15,
        "approval_action_count": 14,
        "hosts": ["console.cloud.google.com"],
        "live_input_supported_actions": ["cloud_create_api_credential", "cloud_iam_change_role"],
    }
    for key, value in expected.items():
        if summary.get(key) != value:
            failures.append(f"Cloud summary {key} mismatch: expected {value!r}, got {summary.get(key)!r}")
    if len(summary.get("prepare_or_open_only_approval_actions", [])) != 12:
        failures.append("Cloud prepare/open-only approval action count must be 12")
    return failures


def _audit_unknown_service() -> list[str]:
    from scripts.google.cloud import router

    result = router.run_cloud("unknown", "open", [])
    expected = {"ok": False, "reason": "unknown_cloud_service", "service": "unknown"}
    return [] if result == expected else [f"unknown service result mismatch: {result!r}"]


def _audit_catalog_only_services() -> list[str]:
    from scripts.google.cloud import router

    failures: list[str] = []
    for service, surface_key in CLOUD_SERVICES.items():
        result = router.run_cloud(service, "dangerous-change", ["private-value"])
        if result.get("ok") is not False:
            failures.append(f"{service}: ok must be False")
        if result.get("mode") != "catalog_only":
            failures.append(f"{service}: mode must be catalog_only")
        if result.get("state_change") is not False:
            failures.append(f"{service}: state_change must be False")
        if result.get("execution_allowed") is not False:
            failures.append(f"{service}: execution_allowed must be False")
        if result.get("surface", {}).get("key") != surface_key:
            failures.append(f"{service}: surface mismatch {result.get('surface')!r}")
        flags = set(result.get("forbidden_execution", []))
        missing_flags = sorted(FORBIDDEN_EXECUTION_FLAGS - flags)
        if missing_flags:
            failures.append(f"{service}: missing forbidden execution flags {', '.join(missing_flags)}")
    return failures


def _audit_forbidden_source_patterns() -> list[str]:
    failures: list[str] = []
    for base in SCAN_PATHS:
        for path in base.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="replace")
            for pattern in FORBIDDEN_SOURCE_PATTERNS:
                if pattern in text:
                    rel = path.relative_to(ROOT).as_posix()
                    failures.append(f"forbidden Cloud source pattern {pattern!r} in {rel}")
    return failures


def audit() -> tuple[bool, list[str]]:
    failures: list[str] = []
    failures.extend(_audit_router_summary())
    failures.extend(_audit_unknown_service())
    failures.extend(_audit_catalog_only_services())
    failures.extend(_audit_forbidden_source_patterns())
    return not failures, failures or [
        "Google Cloud router summary preserves locked counts",
        "Google Cloud router safely rejects unknown services",
        "Google Cloud wrappers are catalog-only and non-executing",
        "Google Cloud source contains no gcloud/API/final-click execution patterns",
    ]


def main() -> int:
    ok, findings = audit()
    for finding in findings:
        print(f"[{'PASS' if ok else 'FAIL'}] {finding}")
    print(f"RESULT={'PASS_GOOGLE_CLOUD_ROUTER_COMPATIBILITY' if ok else 'FAIL_GOOGLE_CLOUD_ROUTER_COMPATIBILITY'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

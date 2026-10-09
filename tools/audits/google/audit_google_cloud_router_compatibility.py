"""Audit Google Cloud router compatibility without live Cloud execution."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
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
    'subprocess.run(["gcloud"',
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
CLOUD_APPROVAL_ACTIONS = [
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
]

SCAN_PATHS = (ROOT / "scripts" / "google" / "cloud",)


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
        "live_input_supported_actions": CLOUD_APPROVAL_ACTIONS,
    }
    for key, value in expected.items():
        if summary.get(key) != value:
            failures.append(f"Cloud summary {key} mismatch: expected {value!r}, got {summary.get(key)!r}")
    if summary.get("prepare_or_open_only_approval_actions", []) != []:
        failures.append("Cloud prepare/open-only approval action count must be 0")
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


def _audit_open_result(failures, service, surface_key, router):
    action_key = f"{surface_key}_open"
    result = router.run_cloud(service, "open", [])
    if result.get("ok") is not True:
        failures.append(f"{service}: read-only open must return ok=True")
    if result.get("mode") != "read_only_open":
        failures.append(f"{service}: mode must be read_only_open")
    if result.get("state_change") is not False:
        failures.append(f"{service}: read-only open state_change must be False")
    if result.get("execution_allowed") is not True:
        failures.append(f"{service}: read-only open must be execution_allowed")
    if result.get("requires_approval") is not False:
        failures.append(f"{service}: read-only open must not require approval")
    if result.get("surface", {}).get("key") != surface_key:
        failures.append(f"{service}: read-only surface mismatch {result.get('surface')!r}")
    if result.get("action_key") != action_key:
        failures.append(f"{service}: read-only action mismatch {result.get('action_key')!r}")
    navigation = result.get("browser_navigation", {})
    if navigation.get("live_open") is not False:
        failures.append(f"{service}: read-only contract must not open a live browser")
    if navigation.get("final_click_allowed") is not False:
        failures.append(f"{service}: final click must stay blocked")


def _audit_readonly_open_services() -> list[str]:
    from scripts.google.cloud import router

    failures: list[str] = []
    for service, surface_key in CLOUD_SERVICES.items():
        _audit_open_result(failures, service, surface_key, router)
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
    failures.extend(_audit_readonly_open_services())
    failures.extend(_audit_catalog_only_services())
    failures.extend(_audit_forbidden_source_patterns())
    return not failures, failures or [
        "Google Cloud router summary preserves locked counts",
        "Google Cloud router safely rejects unknown services",
        "Google Cloud wrappers expose read-only open contracts",
        "Google Cloud wrappers block non-read tasks as catalog-only",
        "Google Cloud source contains no gcloud/API/final-click execution patterns",
    ]


def main() -> int:
    from scripts.common.audit_cli import report_findings

    ok, findings = audit()
    return report_findings(ok, findings, "GOOGLE_CLOUD_ROUTER_COMPATIBILITY")


if __name__ == "__main__":
    raise SystemExit(main())

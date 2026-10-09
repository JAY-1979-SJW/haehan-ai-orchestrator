"""Dry-run audit for Google Cloud read-only local browser task conversion."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CLOUD_SERVICES = (
    "console",
    "maps_platform",
    "api_credentials",
    "iam",
    "billing",
    "run",
    "compute",
    "storage",
    "bigquery",
    "gke",
    "sql",
    "pubsub",
    "secret_manager",
    "logging",
    "monitoring",
)

BLOCKED_ACTIONS = {
    "maps_platform": "maps_platform_change_key_or_quota",
    "api_credentials": "cloud_create_api_credential",
    "iam": "cloud_iam_change_role",
    "billing": "cloud_billing_budget_or_link",
    "run": "cloud_run_deploy_service",
    "compute": "compute_engine_create_vm",
    "storage": "cloud_storage_create_bucket",
    "bigquery": "bigquery_run_query_or_export",
    "gke": "gke_apply_change",
    "sql": "cloud_sql_change_instance",
    "pubsub": "pubsub_create_or_publish",
    "secret_manager": "secret_manager_create_update",
    "logging": "cloud_logging_create_sink",
    "monitoring": "cloud_monitoring_create_alert",
}

FORBIDDEN_OUTPUT_KEYS = {
    "authorization",
    "auth_header",
    "api_key",
    "access_token",
    "refresh_token",
    "device_token",
    "token",
    "secret",
    "password",
    "otp",
    "cookie",
    "cookies",
    "session",
}


def _contains_forbidden_key(value: object) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).replace("-", "_").lower()
            if normalized in FORBIDDEN_OUTPUT_KEYS:
                return True
            if _contains_forbidden_key(child):
                return True
    if isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def _audit_open_service(failures, service, dry_run_cloud_readonly_browser_task):
    result = dry_run_cloud_readonly_browser_task(service, "open", [])
    task = result.get("local_agent_task") or {}
    dry_run = result.get("dry_run_result") or {}
    params = task.get("params") or {}
    metadata = task.get("metadata") or {}
    if result.get("ok") is not True:
        failures.append(f"{service}: conversion failed")
    if task.get("action") != "web_open_url_readonly":
        failures.append(f"{service}: wrong local agent action {task.get('action')!r}")
    if task.get("execution_location") != "local_agent":
        failures.append(f"{service}: execution location must be local_agent")
    if task.get("risk_level") != "read":
        failures.append(f"{service}: risk level must be read")
    if task.get("requires_approval") is not False:
        failures.append(f"{service}: read-only task must not require approval")
    _audit_open_service_target(failures, service, result, dry_run, params, metadata)


def _audit_open_service_target(failures, service, result, dry_run, params, metadata):
    if params.get("target_url_host") != "console.cloud.google.com":
        failures.append(f"{service}: target host mismatch {params.get('target_url_host')!r}")
    if not str(params.get("url", "")).startswith("https://console.cloud.google.com"):
        failures.append(f"{service}: target URL must be Google Cloud Console")
    if metadata.get("google_tab") != "cloud":
        failures.append(f"{service}: google_tab metadata missing")
    if dry_run.get("ok") is not True:
        failures.append(f"{service}: common runtime dry-run failed")
    if _contains_forbidden_key(result):
        failures.append(f"{service}: forbidden secret-shaped key present in conversion output")


def audit() -> tuple[bool, list[str]]:
    from scripts.google.cloud.local_browser import dry_run_cloud_readonly_browser_task

    failures: list[str] = []
    for service in CLOUD_SERVICES:
        _audit_open_service(failures, service, dry_run_cloud_readonly_browser_task)

    for service, action in BLOCKED_ACTIONS.items():
        blocked = dry_run_cloud_readonly_browser_task(service, action, [])
        if blocked.get("ok") is not False:
            failures.append(f"{service}/{action}: non-read task converted to local browser task")
        if blocked.get("local_agent_task") is not None:
            failures.append(f"{service}/{action}: blocked task must not include local_agent_task")
        if blocked.get("state_change") is not False:
            failures.append(f"{service}/{action}: blocked task state_change must be False")

    return not failures, failures or [
        "15 Google Cloud read-only contracts convert to local web_open_url_readonly tasks",
        "converted Cloud read-only tasks pass common runtime dry-run",
        "Cloud approval/prepare actions do not convert to local browser execution",
        "Cloud local browser conversion output contains no forbidden secret-shaped keys",
    ]


def main() -> int:
    from scripts.common.audit_cli import report_findings

    ok, findings = audit()
    return report_findings(ok, findings, "GOOGLE_CLOUD_READONLY_LOCAL_BROWSER_DRYRUN")


if __name__ == "__main__":
    raise SystemExit(main())

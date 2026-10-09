"""Read-only audit for the locked Google Cloud action policy baseline."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASELINE = ROOT / "docs" / "baseline" / "GOOGLE_CLOUD_ACTION_POLICY_BASELINE.md"

READ_ONLY_ACTIONS = (
    "cloud_console_open",
    "maps_platform_open",
    "cloud_apis_credentials_open",
    "cloud_iam_open",
    "cloud_billing_open",
    "cloud_run_open",
    "compute_engine_open",
    "cloud_storage_open",
    "bigquery_open",
    "gke_open",
    "cloud_sql_open",
    "pubsub_open",
    "secret_manager_open",
    "cloud_logging_open",
    "cloud_monitoring_open",
)

PREPARE_ONLY_ACTIONS = ()

APPROVAL_REQUIRED_ACTIONS = (
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

FORBIDDEN_EXECUTION_CLASSES = (
    "gcloud",
    "google_cloud_api",
    "browser_final_click",
    "iam_change",
    "billing_change",
    "secret_value_access",
    "deploy_or_resource_mutation",
)

REQUIRED_PHRASES = (
    "Status: LOCKED",
    "Baseline ID: GOOGLE-CLOUD-ACTION-POLICY-BASELINE-01",
    "Cloud registry actions: 29",
    "read_only actions: 15",
    "prepare_only actions: 0",
    "approval_required actions: 14",
    "forbidden execution classes: 7",
    "Cloud host: `console.cloud.google.com`",
    "This is a policy-only stage.",
    "final submit/save/apply/create is forbidden in this baseline",
    "raw key material, service account data, IAM member identifiers, project ids,",
    "Playwright final submit/click automation",
)


def _missing(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase not in text]


def _duplicates(values: tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    duplicated: list[str] = []
    for value in values:
        if value in seen:
            duplicated.append(value)
        seen.add(value)
    return duplicated


def _audit_baseline_text(failures):
    text = BASELINE.read_text(encoding="utf-8", errors="replace")
    missing = _missing(text, REQUIRED_PHRASES)
    if missing:
        failures.append("Google Cloud action policy baseline missing phrase(s): " + ", ".join(missing))

    for action in READ_ONLY_ACTIONS + PREPARE_ONLY_ACTIONS + APPROVAL_REQUIRED_ACTIONS:
        if f"`{action}`" not in text:
            failures.append(f"baseline missing action: {action}")
    for execution_class in FORBIDDEN_EXECUTION_CLASSES:
        if f"`{execution_class}`" not in text:
            failures.append(f"baseline missing forbidden execution class: {execution_class}")


def _audit_policy_keys(failures, registry_keys, policy_keys):
    duplicated = _duplicates(policy_keys)
    if duplicated:
        failures.append("duplicated policy action(s): " + ", ".join(duplicated))

    missing_policy = sorted(set(registry_keys) - set(policy_keys))
    stale_policy = sorted(set(policy_keys) - set(registry_keys))
    if missing_policy:
        failures.append("Cloud action(s) missing policy classification: " + ", ".join(missing_policy))
    if stale_policy:
        failures.append("policy references unknown Cloud action(s): " + ", ".join(stale_policy))

    if len(READ_ONLY_ACTIONS) != 15:
        failures.append(f"read_only action count changed: {len(READ_ONLY_ACTIONS)}")
    if len(PREPARE_ONLY_ACTIONS) != 0:
        failures.append(f"prepare_only action count changed: {len(PREPARE_ONLY_ACTIONS)}")
    if len(APPROVAL_REQUIRED_ACTIONS) != 14:
        failures.append(f"approval_required action count changed: {len(APPROVAL_REQUIRED_ACTIONS)}")
    if len(policy_keys) != 29:
        failures.append(f"Cloud policy action count changed: {len(policy_keys)}")


def _audit_action_ops(failures, actions):
    actions_by_key = {action["key"]: action for action in actions}
    for action_key in READ_ONLY_ACTIONS:
        action = actions_by_key.get(action_key, {})
        if action.get("requires_approval") is not False or action.get("operation") != "read":
            failures.append(f"read_only action must remain non-approval read: {action_key}")
    for action_key in PREPARE_ONLY_ACTIONS + APPROVAL_REQUIRED_ACTIONS:
        action = actions_by_key.get(action_key, {})
        if action.get("requires_approval") is not True:
            failures.append(f"non-read Cloud action must require approval: {action_key}")


def _audit_cloud_summary(failures, registry):
    summary = registry.cloud_summary()
    if summary.get("hosts") != ["console.cloud.google.com"]:
        failures.append(f"Cloud host changed: {summary.get('hosts')!r}")

    live_supported = tuple(summary.get("live_input_supported_actions", []))
    if live_supported != APPROVAL_REQUIRED_ACTIONS:
        failures.append("Cloud live-input approval actions changed: " + ", ".join(live_supported))

    prepare_open_only = tuple(summary.get("prepare_or_open_only_approval_actions", []))
    if prepare_open_only != PREPARE_ONLY_ACTIONS:
        failures.append("Cloud prepare-only approval actions changed: " + ", ".join(prepare_open_only))


def audit() -> tuple[bool, list[str]]:
    failures: list[str] = []
    if not BASELINE.exists():
        return False, ["docs/baseline/GOOGLE_CLOUD_ACTION_POLICY_BASELINE.md missing"]

    _audit_baseline_text(failures)

    from scripts.google.cloud import registry

    actions = registry.list_actions()
    registry_keys = tuple(action["key"] for action in actions)
    policy_keys = READ_ONLY_ACTIONS + PREPARE_ONLY_ACTIONS + APPROVAL_REQUIRED_ACTIONS

    _audit_policy_keys(failures, registry_keys, policy_keys)

    _audit_action_ops(failures, actions)

    _audit_cloud_summary(failures, registry)

    return not failures, failures or [
        "GOOGLE_CLOUD_ACTION_POLICY_BASELINE exists and is locked",
        "Cloud registry actions are fully classified",
        "read_only, prepare_only, and approval_required counts are preserved",
        "forbidden Cloud execution classes remain documented",
    ]


def main() -> int:
    from scripts.common.audit_cli import report_findings

    ok, findings = audit()
    return report_findings(ok, findings, "GOOGLE_CLOUD_ACTION_POLICY_BASELINE_CONTRACT")


if __name__ == "__main__":
    raise SystemExit(main())

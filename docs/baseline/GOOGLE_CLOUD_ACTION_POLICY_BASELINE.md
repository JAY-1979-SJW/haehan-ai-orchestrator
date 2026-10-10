# HAEHAN Google Cloud Action Policy Baseline

Status: LOCKED
Baseline ID: GOOGLE-CLOUD-ACTION-POLICY-BASELINE-01
Approved by: user approval in current Codex session
Baseline HEAD: 4c37ecb660f6cc842013503008547ee2e005d425
Last updated: 2026-05-24

## 1. Purpose

This baseline locks the action-level policy for the Google Cloud module before
any live Cloud automation is approved. It classifies every Cloud registry action
as `read_only`, `prepare_only`, or `approval_required`, and it keeps destructive
or secret-revealing execution classes under `forbidden`.

This is a policy-only stage. It does not run `gcloud`, does not call Google
Cloud APIs, does not open a live browser, and does not click final submit
buttons.

## 2. Locked Counts

- Cloud surfaces: 15
- Cloud registry actions: 29
- read_only actions: 15
- prepare_only actions: 0
- approval_required actions: 14
- forbidden execution classes: 7
- Cloud host: `console.cloud.google.com`

## 3. read_only Actions

These actions may only open or inspect the relevant Cloud surface. They must not
change state and must not output secret values.

- `cloud_console_open`
- `maps_platform_open`
- `cloud_apis_credentials_open`
- `cloud_iam_open`
- `cloud_billing_open`
- `cloud_run_open`
- `compute_engine_open`
- `cloud_storage_open`
- `bigquery_open`
- `gke_open`
- `cloud_sql_open`
- `pubsub_open`
- `secret_manager_open`
- `cloud_logging_open`
- `cloud_monitoring_open`

## 4. prepare_only Actions

No Cloud approval action remains prepare-only after the generic
no-final-submit handoff adapter was added. This does not approve final submit,
save, create, deploy, publish, export, or resource mutation.

## 5. approval_required Actions

These actions are the Cloud approval actions with live-input handoff support in
the current registry. They are still no-final-submit actions until a separate final
approval implementation is approved.

- `maps_platform_change_key_or_quota`
- `cloud_create_api_credential`
- `cloud_iam_change_role`
- `cloud_billing_budget_or_link`
- `cloud_run_deploy_service`
- `compute_engine_create_vm`
- `cloud_storage_create_bucket`
- `bigquery_run_query_or_export`
- `gke_apply_change`
- `cloud_sql_change_instance`
- `pubsub_create_or_publish`
- `secret_manager_create_update`
- `cloud_logging_create_sink`
- `cloud_monitoring_create_alert`

Required behavior:

- user approval is required before preparing the workflow
- final submit/save/apply/create is forbidden in this baseline
- raw key material, service account data, IAM member identifiers, project ids,
  billing data, tokens, cookies, and Authorization headers must not be printed
- evidence must be redacted

## 6. forbidden Execution Classes

The following classes are forbidden for all Cloud wrappers and routers in this
baseline:

- `gcloud`
- `google_cloud_api`
- `browser_final_click`
- `iam_change`
- `billing_change`
- `secret_value_access`
- `deploy_or_resource_mutation`

Concrete forbidden behavior includes:

- running `gcloud`
- calling Google Cloud APIs
- Playwright final submit/click automation
- IAM grant, revoke, or role mutation
- billing, quota, budget, payment, or project-link mutation
- secret value read or output
- deploy, create, update, delete, publish, query export, sink, alert, VM,
  bucket, database, cluster, or topic mutation

## 7. Surface Policy Matrix

| Surface | read_only | prepare_only | approval_required |
| --- | --- | --- | --- |
| `cloud_console` | `cloud_console_open` | - | - |
| `maps_platform` | `maps_platform_open` | - | `maps_platform_change_key_or_quota` |
| `cloud_apis_credentials` | `cloud_apis_credentials_open` | - | `cloud_create_api_credential` |
| `cloud_iam` | `cloud_iam_open` | - | `cloud_iam_change_role` |
| `cloud_billing` | `cloud_billing_open` | - | `cloud_billing_budget_or_link` |
| `cloud_run` | `cloud_run_open` | - | `cloud_run_deploy_service` |
| `compute_engine` | `compute_engine_open` | - | `compute_engine_create_vm` |
| `cloud_storage` | `cloud_storage_open` | - | `cloud_storage_create_bucket` |
| `bigquery` | `bigquery_open` | - | `bigquery_run_query_or_export` |
| `gke` | `gke_open` | - | `gke_apply_change` |
| `cloud_sql` | `cloud_sql_open` | - | `cloud_sql_change_instance` |
| `pubsub` | `pubsub_open` | - | `pubsub_create_or_publish` |
| `secret_manager` | `secret_manager_open` | - | `secret_manager_create_update` |
| `cloud_logging` | `cloud_logging_open` | - | `cloud_logging_create_sink` |
| `cloud_monitoring` | `cloud_monitoring_open` | - | `cloud_monitoring_create_alert` |

## 8. Required Verification

Minimum verification for Cloud action policy changes:

```text
python tools/audits/google/audit_google_cloud_action_policy_baseline_contract.py
python tools/audits/google/audit_google_cloud_router_compatibility.py
python tools/quality/module_quality_gate.py --module repo_guard
```

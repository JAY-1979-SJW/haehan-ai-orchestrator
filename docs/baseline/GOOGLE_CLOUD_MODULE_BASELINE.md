# HAEHAN Google Cloud Module Baseline

Status: LOCKED
Baseline ID: GOOGLE-CLOUD-MODULE-BASELINE-01
Approved by: user approval in current Codex session
Baseline HEAD: 39b597a6fca258a594f7103b30ae713cfe118e8b
Last updated: 2026-05-24

## 1. Purpose

This baseline locks the Google Cloud sub-module split target. Cloud automation
is high risk because it can affect infrastructure, IAM, billing, credentials,
deployment, data, logs, monitoring, and secrets.

This is a baseline-only stage. It does not create Cloud wrapper modules, does
not run `gcloud`, does not call Google Cloud APIs, and does not open a live
browser.

## 2. Locked Cloud Scope

Cloud owns exactly 15 surfaces:

- `cloud_console`
- `maps_platform`
- `cloud_apis_credentials`
- `cloud_iam`
- `cloud_billing`
- `cloud_run`
- `compute_engine`
- `cloud_storage`
- `bigquery`
- `gke`
- `cloud_sql`
- `pubsub`
- `secret_manager`
- `cloud_logging`
- `cloud_monitoring`

Locked counts:

- Cloud surfaces: 15
- Cloud actions: 29
- Cloud read actions: 15
- Cloud approval actions: 14
- Cloud hosts: `console.cloud.google.com`
- Cloud live input supported actions: 14
- Cloud prepare/open-only approval actions: 0

Important boundary:

- `vertex_ai` also uses `console.cloud.google.com`, but it belongs to the `ai`
  tab and is intentionally excluded from this Cloud baseline.

## 3. Required Cloud Actions

Read actions:

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

Approval actions:

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

Live input supported approval actions:

- `cloud_create_api_credential`
- `cloud_iam_change_role`

These live-input actions must remain safe handoff/no-final-submit paths. They
must not create credentials or change IAM without a separate final approval
implementation.

## 4. Security Boundaries

Cloud is a high-risk module. The following are forbidden in this baseline:

- unapproved IAM grant, revoke, or role change
- unapproved billing, budget, project-link, payment, or quota change
- unapproved API key, OAuth client, or service account credential creation
- unapproved Secret Manager read, create, update, delete, or value output
- unapproved deploy, VM, bucket, database, cluster, topic, sink, alert, or publish action
- unapproved BigQuery query or export
- raw project id, service account, key material, billing account, secret value,
  token, cookie, session, Authorization header, password, or OTP output
- actual `gcloud` execution
- actual Google Cloud API execution
- browser final click automation

Allowed in this baseline:

- read-only catalog/open contracts
- prepare or handoff artifact generation
- approval-required plans with `state_change` false
- redacted evidence only

## 5. Intended Module Shape

The approved future structure is:

```text
scripts/google/cloud/
  __init__.py
  registry.py
  router.py
  console.py
  iam.py
  billing.py
  run.py
  compute.py
  storage.py
  bigquery.py
  gke.py
  sql.py
  pubsub.py
  secret_manager.py
  logging.py
  monitoring.py
  maps_platform.py
```

The first implementation step must add registry and wrapper layers only. It
must not move Cloud behavior out of the locked Google catalogs until tests
prove the counts and approval boundaries remain unchanged.

## 6. Step Plan

Cloud split must proceed in this order:

1. Add `scripts/google/cloud/registry.py`.
2. Add catalog-only wrappers for all 15 Cloud surfaces.
3. Add `scripts/google/cloud/router.py`.
4. Keep `vertex_ai` under the `ai` tab.
5. Verify 15 Cloud surfaces and 29 Cloud actions remain unchanged.
6. Verify 14 approval actions remain approval-gated.
7. Verify live-input-supported Cloud actions remain exactly 2 and no-final-submit.
8. Verify no actual `gcloud`, API call, or browser final click is added.

## 7. Required Verification

Minimum verification for Cloud changes:

```text
python tools/audits/google/audit_google_cloud_module_baseline_contract.py
python tools/audits/google/audit_google_automation_baseline_contract.py
python tools/quality/module_quality_gate.py --module repo_guard
```

## 8. Known WARN

- Cloud wrapper modules are not implemented yet.
- Cloud live input exists for all 14 approval actions as safe
  handoff/no-final-submit actions.
- No production `gcloud` or Google Cloud API execution adapter is approved in
  this baseline.

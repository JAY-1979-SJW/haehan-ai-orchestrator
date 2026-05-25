# HAEHAN Connection Inventory

Status: ACTIVE
Owner baseline: `docs/baseline/APP_BASELINE.md`
Workflow rule: `docs/baseline/STANDARD_WORKFLOW.md`
Last updated: 2026-05-25

## Purpose

This document is the durable inventory for server, local-agent, desktop,
browser, external API, and operational helper connections.

Any task that creates, changes, removes, audits, or classifies a connection must
update this inventory or record why the connection is out of scope.

## Classification Fields

Every locked connection entry should define:

```text
connection name
source
target
authentication method
owner baseline
status: active | locked | legacy | deprecated | unknown
allowed direction
recovery policy
verification command
secret/redaction boundary
notes
```

## Current Connection Index

| Connection | Source | Target | Status | Auth boundary | Recovery policy | Verification |
|---|---|---|---|---|---|---|
| Server task queue | authenticated server API | backend task state | locked | server auth/approval | server-owned state transitions | `python scripts/ops/audit_backend_core_baseline_contract.py` |
| Local-agent WebSocket | local agent | server dispatch endpoint | locked | `agent_id + device_token` | bounded reconnect/backoff, no raw token output | `python scripts/ops/audit_local_agent_e2e_flow_contract.py` |
| Connection recovery probes | local agent diagnostics | server auth/heartbeat/dispatch probes | locked | redacted credentials only | safe recovery plan, no indefinite auth retry | `python scripts/ops/audit_local_agent_connection_recovery_baseline.py` |
| Desktop local server | desktop UI/runtime | `desktop/local_server.py` on local host | locked | subordinate to server contract | no persistent autostart without approval | `python scripts/ops/audit_desktop_auth_runtime_baseline_contract.py` |
| CDP/browser attach | local-agent/browser tools | local browser discovery endpoints | locked | loopback/read-only discovery unless approved | dedicated profile, redacted tab data | `python scripts/ops/dry_run_local_agent_cdp_attach.py` |
| Gmail functions | Google scripts/workflow | Gmail read/draft operations | locked | no final submit without approval | draft-only for send/reply, delete/star blocked | `python scripts/ops/audit_google_gmail_function_contract.py` |
| Site work functions | site modules | Google/Naver/SmartStore/Hiworks/Gabia/YouTube | locked | approval/user-direct gates | state-changing work approval-gated or user-direct | `python scripts/ops/audit_site_work_function_baseline.py` |
| Legacy scheduled autostart | old desktop/CDP scheduler helpers | Windows Task Scheduler/startup | deprecated | none | cleanup-only helpers | `python scripts/ops/audit_legacy_app_runtime_cleanup.py` |

## Lock Needed Queue

Use this section for connections found during inventory work that are not yet
classified.

| Connection | Current evidence | Required owner | Next lock action |
|---|---|---|---|
| TBD | TBD | TBD | TBD |

# HAEHAN Connection Inventory

Status: LOCKED
Owner baseline: `docs/baseline/APP_BASELINE.md`
Workflow rule: `docs/baseline/STANDARD_WORKFLOW.md`
Last updated: 2026-05-25

## Purpose

This document is the durable inventory for server, local-agent, desktop,
browser, external API, and operational helper connections.

Any task that creates, changes, removes, audits, or classifies a connection must
update this inventory or record why the connection is out of scope.

## Attachment Lock Rule

Only connections with status `active` or `locked` may be used by app UI routes,
server actions, background jobs, or local-agent dispatch.

Connections with status `legacy`, `deprecated`, `unknown`, `TBD`, or entries
in `Lock Needed Queue` may be shown as inventory evidence only. They must not
be used for executable commands until their source, target, auth boundary,
allowed direction, recovery policy, redaction boundary, and verification
command are documented and passing.

Unknown or unclassified connections must fail closed before command execution.

## Connection Logic Lock

The current connection structure is locked to the server-first runtime flow:

```text
authenticated user instruction
-> server task creation
-> auth/risk/approval policy check
-> local-agent queue
-> local-agent WebSocket authentication
-> task dispatch
-> local execution
-> result return
-> server state update
-> audit event
```

Locked execution rules:

- The server is the final operational source of truth for connection state,
  task state, approvals, results, and audit events.
- App UI routes may display connection status and submit server actions, but
  must not call local-agent, desktop, browser, Gmail, or site-work execution
  paths directly.
- Local-agent execution is allowed only through the authenticated WebSocket
  dispatch path using `agent_id + device_token`.
- Browser or CDP background execution is allowed only when the dispatched task
  carries an explicit `background_approved=True` marker from the approval path.
- Desktop and local-agent logs are diagnostic evidence only; they must not
  replace server task state or server audit events.
- AI agent work must leave the structured audit event and the user-verifiable
  AI Agent Work Record required by `docs/baseline/STANDARD_WORKFLOW.md`.
- Any connection outside `Current Connection Index`, or any connection with
  missing source, target, auth boundary, recovery policy, redaction boundary,
  or verification command, is locked out of executable routing until this
  inventory and its owner baseline are updated and verified.

Required lock verification:

```text
python tools/audits/app/audit_standard_workflow_contract.py
python tools/audits/agent/audit_local_agent_e2e_baseline_contract.py
python tools/audits/agent/audit_local_agent_e2e_flow_contract.py
python -m pytest tests/test_connection_inventory_lock.py -q
```

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
| Server task queue | authenticated server API | backend task state | locked | server auth/approval | server-owned state transitions | `python tools/audits/backend/audit_backend_core_baseline_contract.py` |
| Data contribution API | authenticated server API | server consent/export gate and JSONL consent store | active | server auth + explicit consent record | consent revoke blocks future export; JSONL replay restores consent state | `python -m pytest tests/test_user_data_contribution_consent.py -q` |
| Local-agent WebSocket | local agent | server dispatch endpoint | locked | `agent_id + device_token` | bounded reconnect/backoff, no raw token output | `python tools/audits/agent/audit_local_agent_e2e_flow_contract.py` |
| Connection recovery probes | local agent diagnostics | server auth/heartbeat/dispatch probes | locked | redacted credentials only | safe recovery plan, no indefinite auth retry | `python tools/audits/agent/audit_local_agent_connection_recovery_baseline.py` |
| Desktop local server | desktop UI/runtime | `desktop/local_server.py` on local host | locked | subordinate to server contract | no persistent autostart without approval | `python tools/audits/agent/audit_desktop_auth_runtime_baseline_contract.py` |
| CDP/browser attach | local-agent/browser tools | local browser discovery endpoints | locked | loopback/read-only discovery unless approved | dedicated profile, redacted tab data | `python tools/verify/dry_run_local_agent_cdp_attach.py` |
| Gmail functions | Google scripts/workflow | Gmail read/draft operations | locked | no final submit without approval | draft-only for send/reply, delete/star blocked | `python scripts/google/audit_gmail_function_contract.py` |
| Site work functions | site modules | Google/Naver/SmartStore/Hiworks/Gabia/YouTube | locked | approval/user-direct gates | state-changing work approval-gated or user-direct | `python tools/audits/app/audit_site_work_function_baseline.py` |
| Legacy scheduled autostart | old desktop/CDP scheduler helpers | Windows Task Scheduler/startup | deprecated | none | cleanup-only helpers | `python tools/audits/backend/audit_legacy_app_runtime_cleanup.py` |

## Lock Needed Queue

Use this section for connections found during inventory work that are not yet
classified.

| Connection | Current evidence | Required owner | Next lock action |
|---|---|---|---|
| TBD | TBD | TBD | TBD |

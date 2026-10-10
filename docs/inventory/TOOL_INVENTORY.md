# HAEHAN Tool Inventory

Status: ACTIVE
Owner baseline: `docs/baseline/APP_BASELINE.md`
Workflow rule: `docs/baseline/STANDARD_WORKFLOW.md`
Last updated: 2026-05-25

## Purpose

This document is the durable inventory for developed tools, runtime entrypoints,
automation scripts, site modules, and operational helpers.

Logs are not sufficient as final evidence. Any task that creates, changes,
removes, audits, or classifies a tool must update this inventory or record why
the tool is out of scope.

## Attachment Lock Rule

Only tools with status `active` or `locked` may be attached to app UI routes,
server actions, background jobs, or local-agent dispatch.

Tools with status `legacy`, `deprecated`, `unknown`, `TBD`, or entries in
`Lock Needed Queue` may be shown as inventory evidence only. They must not be
wired to executable commands until their owner baseline, connection, command
class, input/output contract, approval boundary, redaction boundary, failure
behavior, and verification command are documented and passing.

Unknown tool execution must fail closed as `unknown_tool_execute`.

## Classification Fields

Every locked tool entry should define:

```text
tool name
path
category: server | local-agent | desktop | site | ops | legacy
status: active | locked | legacy | deprecated | unknown
execution location: server | local-agent | desktop | user-direct | audit-only
approval requirement
input contract
output contract
risk level
verification command
owner baseline
notes
```

## Current Inventory Index

| Tool group | Primary paths | Category | Status | Execution location | Owner baseline | Verification |
|---|---|---|---|---|---|---|
| Backend core | `ai_orchestrator/server/`, backend audits/tests | server | locked | server | `BACKEND_CORE_BASELINE.md` | `python tools/audits/backend/audit_backend_core_baseline_contract.py` |
| Common tool runtime | `core/agent_runtime/runtime/common_tool_runtime.py` | local-agent | locked | local-agent | `COMMON_TOOL_RUNTIME_BASELINE.md` | `python tools/audits/agent/audit_common_tool_runtime.py` |
| Local-agent E2E | local-agent dispatch/auth tests and audits | local-agent | locked | local-agent | `LOCAL_AGENT_E2E_BASELINE.md` | `python tools/audits/agent/audit_local_agent_e2e_flow_contract.py` |
| Connection recovery | connection diagnostics, WebSocket probes, recovery audits | local-agent | locked | local-agent | `LOCAL_AGENT_CONNECTION_RECOVERY_BASELINE.md` | `python tools/audits/agent/audit_local_agent_connection_recovery_baseline.py` |
| Approval flow | approval API/policy/state audits and tests | server | locked | server | `APPROVAL_FLOW_BASELINE.md` | `python tools/audits/app/audit_approval_flow_baseline_contract.py` |
| User data contribution consent | `ai_orchestrator/user_data/user_data_contribution_store.py`, `ai_orchestrator/user_data/user_data_contribution_router.py`, `data/audit/user_data_contribution_consents.jsonl` | server | active | server | `APP_BASELINE.md` | `python -m pytest tests/test_user_data_contribution_consent.py -q` |
| Playwright AI | local Playwright/AI proxy contracts | local-agent | locked | local-agent | `PLAYWRIGHT_AI_BASELINE.md` | `python tools/audits/agent/audit_playwright_ai_baseline_contract.py` |
| Site work functions | `scripts/google/`, `scripts/naver/`, `scripts/smartstore/`, `scripts/hiworks/`, `scripts/gabia/`, `scripts/youtube/` | site | locked | server/local-agent/user-direct by profile | `SITE_WORK_FUNCTION_BASELINE` | `python tools/audits/app/audit_site_work_function_baseline.py` |
| Gmail functions | `scripts/google/common/gmail_analysis.py`, Gmail workflow coverage | site | locked | local-agent/user-direct for state-changing work | Google/Gmail function contract | `python scripts/google/audit_gmail_function_contract.py` |
| Desktop runtime | `desktop/main_launcher.py`, `desktop/local_server.py`, desktop audits | desktop | locked | desktop subordinate to server | `DESKTOP_AUTH_RUNTIME_BASELINE.md` | `python tools/audits/agent/audit_desktop_auth_runtime_baseline_contract.py` |
| Release preflight | release preflight audits/tests | ops | locked | audit-only | `RELEASE_PREFLIGHT_BASELINE.md` | `python scripts/ops/audit_release_preflight_baseline_contract.py` |
| Root legacy scripts | root-level script inventory | legacy | locked | audit-only unless separately approved | repo guard | `python tools/repo_gates/audit_root_legacy_scripts.py` |
| Legacy desktop UI runtime | removed legacy desktop UI entrypoints/archive | legacy | deprecated | none | server-first operating baseline | `python tools/audits/backend/audit_legacy_app_runtime_cleanup.py` |

## Lock Needed Queue

Use this section for tools found during inventory work that are not yet
classified.

| Tool/path | Current evidence | Required owner | Next lock action |
|---|---|---|---|
| TBD | TBD | TBD | TBD |

# HAEHAN App Structure

Status: LOCKED
Baseline ID: HAEHAN-APP-STRUCTURE-01
Owner baseline: `docs/baseline/APP_BASELINE.md`
Workflow rule: `docs/baseline/STANDARD_WORKFLOW.md`
Last updated: 2026-05-25

## Purpose

This document locks the app structure used for future app development.

The app must be developed as a server-first control surface. It must not become
an independent runtime, approval source, task state source, or policy engine.

## Final Operating Basis

The server is the final operational source of truth for HAEHAN.

The server owns:

- identity
- authorization
- approval
- policy
- task queue
- task state
- result intake
- audit records
- release and deploy decisions

Desktop, local-agent, browser automation, site modules, and app UI are
subordinate execution or presentation layers.

## App Role

The app is the control surface.

It may:

- show server-owned tasks, approvals, results, audits, and connection status
- request server APIs to create, approve, reject, cancel, or inspect tasks
- show local-agent and desktop readiness reported through server-approved
  contracts
- guide users through approval or user-direct work

It must not:

- execute browser/tool work directly from UI state
- become the source of truth for approval, policy, task state, or audit history
- store raw tokens, cookies, sessions, passwords, OTP values, or approval tokens
- bypass server task creation, approval gates, or execution-location gates
- register persistent local autostart, background recovery, or always-on
  monitoring

## Structural Layers

| Layer | Primary paths | Role | Must not do |
|---|---|---|---|
| Server app/API | `ai_orchestrator/` | Authentication, authorization, approval, task queue, state, audit, safe APIs | Run local browser/tool work directly |
| Common runtime | `ai_orchestrator/local_agent/common_tool_runtime.py` | Shared task/result/risk/approval contract | Execute tools directly or accept unsafe fields |
| Common engine/site policy | `scripts/site_engine/` | Profiles, gates, execution planning, validation | Duplicate policy in site routers |
| Site/tool adapters | `scripts/google/`, `scripts/naver/`, `scripts/smartstore/`, `scripts/hiworks/`, `scripts/gabia/`, `scripts/youtube/` | Thin site-specific workflows and adapters | Bypass approval or user-direct gates |
| Local agent | `local_agent/` | Authenticated PC-side execution for server-dispatched tasks | Accept raw user work outside server task contract |
| Desktop runtime | `desktop/main_launcher.py`, `desktop/local_server.py` | Local UI/runtime hub subordinate to server | Own server state, approval, policy, or audit history |
| Ops/audit | `scripts/ops/`, `tests/` | Verification, audits, reports, dry-runs | Deploy, restart, install, or mutate runtime without approval |
| Inventories/reports | `docs/inventory/`, `docs/reports/` | Durable tracking and task evidence | Replace executable audits or tests |

## Parallel Work Design

The structure is designed for parallel work only when ownership boundaries are explicit and write sets are disjoint.

Parallel work may run across these independent lanes:

```text
app UI shell and screens
server API contracts
local-agent dispatch and connection recovery
tool/site adapter contracts
standard UI package
inventories, reports, and audits
```

Parallel work must follow these rules:

- each workstream must declare its owner module before editing
- each workstream must use a disjoint write set
- shared baselines may be edited by one workstream at a time
- cross-module changes must run every affected module gate
- server-first contracts must not be weakened to unblock a parallel task
- executable app commands may attach only to inventoried `active` or `locked`
  tools and connections
- unresolved conflicts must stop at report, not be silently merged

The module boundary map remains the ownership source for parallel work:

```text
configs/module_boundaries.json
docs/architecture/module_boundary_map_20260523.md
tools/audits/app/audit_module_boundaries.py
```

Parallel work is not allowed for live deploy, server restart, process kill,
credential reset, persistent autostart, or always-on monitoring unless the user
approves that stage explicitly.

## Canonical Flow

```text
authenticated user instruction
-> server task creation
-> auth/risk/approval policy check
-> local-agent queue
-> local-agent WebSocket authentication
-> task dispatch
-> local execution or user-direct action
-> redacted result return
-> server state update
-> audit event
-> app displays server-owned state
```

## Forbidden Structure

These structures are forbidden unless a future baseline explicitly changes the
contract:

- app UI directly executing browser/CDP/Playwright/site/tool work
- app UI issuing approval and then executing work without a server task
- desktop/local-agent storing final task state or audit history independently
- local runtime registering persistent autostart or always-on monitoring
- server executing user-local browser automation
- site-specific modules duplicating common execution gates
- reports/logs replacing durable inventory updates

## Recovery Boundary

Recovery work is diagnostic-first and server-baseline controlled.

Allowed without separate runtime approval:

- read-only structure audits
- read-only inventory checks
- read-only connection diagnostics
- redacted recovery plan reports
- verification commands that do not change live runtime or persistent state

Forbidden without separate explicit approval:

- automatic server deploy/restart
- Docker build, pull, up, restart, or deploy
- local-agent token deletion or credential reset
- persistent local autostart registration
- background recovery registration
- always-on monitoring registration
- process termination outside the approved target app
- editing another workspace, app, server, browser, or test runner

Recovery scripts in this repository must be audit-first unless their task is separately approved as a live runtime recovery operation.

## Task History And Audit Log Boundary

User task requests, agent execution status, verification evidence, and task
results must leave a safe task history.
The server task state and server audit events are the final source of truth.

The app may display task history, approval status, execution status, safe
summaries, error codes, report paths, and verification references that come from
server-owned records.

The app, desktop runtime, and local agent must not become independent sources
of truth for task history, approval, policy, state, or audit.

Local-agent and desktop logs are diagnostic evidence only.

Task history, audit logs, reports, and local diagnostics must not contain raw
secrets, tokens, cookies, sessions, passwords, OTP values, approval tokens, raw
auth headers, sensitive personal data, full sensitive local file paths, full
page HTML, or automatic raw screenshot captures.

## User Data Contribution Consent Boundary

The app may offer a consent control for contributing safe task records to product
improvement, but the server owns the explicit user data contribution consent
record and enforcement.

Consent must be separate from normal service use, purpose-specific,
category-specific, revocable, and tied to retention and deletion rules.

Only redacted and minimized development material may leave the task history
boundary: safe intent summaries, safe result summaries, task categories,
tool/module identifiers, state transitions, error codes, verification
references, and user feedback.

The app, desktop runtime, local agent, reports, and diagnostics must not send or store raw user prompts, raw files, raw page content, raw screenshots, raw
emails, raw document bodies, raw browser traces, secrets, credentials, tokens,
cookies, sessions, passwords, OTP values, approval tokens, raw auth headers,
sensitive personal data, or unrelated third-party content as development
material.

## Development Order

Future app work should follow this order:

```text
app development standard
-> tool inventory
-> connection inventory
-> tool contract lock
-> connection/recovery lock
-> common engine integration
-> server API contract
-> app control surface
-> focused verification
-> report and inventory update
```

## Required Updates

When app structure, app shell, UI routing, navigation, task screens, approval
screens, connection screens, or control-surface behavior changes, update:

- `docs/architecture/APP_STRUCTURE.md`
- `docs/baseline/APP_DEVELOPMENT_STANDARD.md` when app shell, route, screen,
  API integration, or UI completion rules change
- `docs/inventory/TOOL_INVENTORY.md` when tools are created, removed, or
  reclassified
- `docs/inventory/CONNECTION_INVENTORY.md` when connections are created,
  removed, or reclassified
- `docs/reports/<task>_<yyyymmdd>.md`

## Verification

Minimum structure verification:

```text
python tools/audits/app/audit_app_development_standard.py
python tools/audits/app/audit_app_structure_contract.py
python tools/audits/app/audit_standard_workflow_contract.py
python -m pytest tests/test_app_development_standard.py -q
python -m pytest tests/test_app_structure_contract.py -q
python -m pytest tests/test_standard_workflow_contract.py -q
```

App implementation work may require additional module gates based on touched
paths.

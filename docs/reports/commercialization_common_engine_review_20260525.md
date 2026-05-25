# Commercialization Common Engine Review - 2026-05-25

## Scope

This note defines the practical order for commercialization work after the
Gmail/live-agent verification pass.

## Current Common Engine

The current common engine is not a single UI app. It is the shared execution
rail made of locked contracts and gates:

- `common_tool_runtime`: task/result contract, risk level, approval requirement,
  forbidden field rejection, and safe metadata.
- `backend_core`: authentication, authorization, approval, task creation,
  dispatch eligibility, task state, result intake, and audit events.
- `local_agent_e2e`: authenticated PC-side execution through WebSocket with
  redacted results.
- `approval_flow`: fail-closed approval path before high-risk execution.
- `repo_guard`: required local quality and boundary gates.

Current verified scope:

- Required quality gate passes.
- Local agent can authenticate to the live server.
- Authenticated live task dispatch can reach the local agent and complete.
- Gmail read/analyze and Gmail no-final-submit safety contracts are verified.

## Commercialization Order

Commercialization should not start with a broad app build. The correct order is:

1. Stabilize the common engine.
2. Harden live connectivity and recovery.
3. Lock site/tool-specific execution modules on top of the common engine.
4. Build the app UI around the locked engine and verified APIs.
5. Package, install, monitor, and operate.

## Why Engine First

The app is only commercially useful if it can reliably show and control real
work. That requires the engine to own these guarantees first:

- authenticated user instruction
- safe task normalization
- risk and approval classification
- queue and state transition
- local-agent authentication
- dispatch and execution
- redacted result return
- audit and recovery

If the app is built before these are stable, the UI will either show mock state,
hide failure, or encourage unsafe execution shortcuts.

## What Must Be Strengthened Before App Expansion

### Connection Layer

Required:

- local-agent re-registration and repair flow
- WebSocket reconnect and backoff policy
- stale token detection with user-safe recovery guidance
- server health, agent health, and task dispatch health checks
- clear split between auth failure, network failure, server failure, and local
  execution failure

### Common Engine

Required:

- one normalized task model for site, browser, AI, and local-tool work
- one result model with redaction and safe error summaries
- action registry for supported operations
- retry, timeout, cancellation, and recovery policy
- evidence package format per task
- module-specific baselines layered on top of common contracts

### Approval And Safety

Required:

- approval matrix by action class
- no-final-submit mode for draft/fill workflows
- final action confirmation boundary
- audit trail for approval request, approval decision, execution, and result
- no raw secret/session/cookie/token output

### App Surface

Required after the above:

- agent status and reconnect/repair screen
- task queue, task detail, approval queue, audit log, and evidence viewer
- domain workspaces for Gmail/Google, G2B, EUM, Hiworks, CAD/HWPX, Excel
- operator-facing failure and recovery messages
- admin-only registration code management

## Immediate Next Work

Recommended next work item:

```text
COMMON_ENGINE_COMMERCIALIZATION_BASELINE_01
```

Deliverables:

- common engine commercialization baseline
- connection/recovery checklist
- action registry ownership map
- app-before-engine blocking rule
- verification matrix for live server, local agent, task dispatch, approval, and
  one site-specific workflow

## Decision

Yes. For commercialization, the project must first strengthen the connection
and common engine, then develop the app on top of that stable execution layer.

The app should be treated as the control surface, not the core engine. The core
commercial product is the reliable, auditable, approval-safe execution system.

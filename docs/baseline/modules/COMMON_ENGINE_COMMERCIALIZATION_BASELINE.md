# HAEHAN Common Engine Commercialization Baseline

Status: LOCKED
Baseline ID: HAEHAN-COMMON-ENGINE-COMMERCIALIZATION-BASELINE-01
Approved by: user approval in current Codex session
Baseline HEAD: a7120cf17d1a45276c151b5938f904a295cf7b05
Last updated: 2026-05-25

## 1. Purpose

This document locks the commercialization readiness contract for the shared
execution engine. Commercial app work may proceed only after the engine can
prove authenticated instruction intake, safe task normalization, approval
gating, local-agent dispatch, redacted result return, auditability, and recovery
behavior.

The app is the control surface. The common engine is the commercial product
core.

## 2. Responsibility

`common_engine_commercialization` owns the cross-module readiness rule for:

- common task and result contract
- backend authentication and authorization boundary
- approval flow and fail-closed behavior
- local-agent registration, authentication, and dispatch
- live connection health and repair guidance
- action registry ownership
- task state transitions
- evidence package and audit trail
- app-before-engine blocking rule

It does not replace the lower-level module baselines. It composes them into the
minimum commercial readiness contract.

## 3. Required Engine Layers

The commercial engine must include these locked layers:

- `common_tool_runtime`
- `backend_core`
- `approval_flow`
- `local_agent_e2e`
- `local_agent_connection_recovery`
- `desktop_auth_runtime`
- `playwright_ai`
- `release_preflight`
- `release_runtime`

Each layer must keep its own baseline, audit, and tests. A commercial app
feature may not bypass these layers by calling local tools, browser automation,
or external sites directly.

## 4. Commercialization Order

Required order:

```text
common engine contract
-> connection and recovery hardening
-> site/tool-specific module baseline
-> app control surface
-> packaging and operations
```

Forbidden order:

```text
app UI first
-> mock state
-> hidden failure
-> engine retrofit
```

The app may be developed only around verified APIs and states. It must not
create a second task engine, second approval engine, or direct execution
shortcut.

## 5. Connection And Recovery Boundary

Commercial readiness requires:

- local-agent registration and re-registration path
- stale token detection
- WebSocket authentication check
- WebSocket reconnect and backoff policy
- server health check
- agent health check
- task dispatch health check
- user-safe recovery guidance for auth failure, network failure, server
  failure, and local execution failure

Connection failures must end as safe failure states, not mock success.

## 6. Task And Result Boundary

All executable work must use a normalized task/result contract:

- task id
- tool namespace
- action
- execution location
- risk level
- approval state
- task phase
- redacted params
- safe result summary
- evidence reference
- audit event reference

Forbidden fields remain forbidden in task and result payloads:

- Authorization
- bearer token
- access token
- refresh token
- device token
- cookie
- session
- password
- OTP
- API key
- secret

## 7. Approval And Safety Boundary

Approval is required before execution for:

- send
- submit
- upload
- delete
- payment
- transfer
- bid
- signature
- registration
- external state change
- local file or local app state change
- sensitive capture outside approved dry-run scope

Draft/fill workflows must use no-final-submit mode until the user explicitly
approves the final action.

Approval API failure, missing approval configuration, expired approval, or
denied approval must not transition a task to `queued`.

## 8. State And Evidence Boundary

Commercial task state must remain explicit:

```text
requested -> approval_checked -> queued -> delivered -> running -> completed
requested -> approval_checked -> waiting_approval -> queued -> delivered -> running -> completed
requested -> blocked
queued | delivered | running -> failed
queued | delivered | running -> cancel_requested -> cancelled
```

Every completed or failed task must be able to reference safe evidence:

- task request summary
- approval decision summary when applicable
- execution status
- result summary
- failure category when applicable
- redaction status
- audit event id or storage reference

Evidence must not contain raw secrets, cookies, sessions, tokens, passwords, or
OTP values.

## 9. App Control Surface Boundary

The commercial app may show and control:

- agent status
- reconnect or re-register guidance
- task queue
- task detail
- approval queue
- audit log
- evidence viewer
- domain workspace entry points
- admin-only registration code management

The commercial app must not:

- execute local tools directly
- run Playwright directly
- bypass backend auth or approval
- show mock success for live failure
- expose raw credentials or session state
- invent task states not supported by the engine

## 10. Required Verification

Baseline verification:

```text
python tools/audits/app/audit_common_engine_commercialization_baseline.py
python -m pytest tests/test_common_engine_commercialization_baseline.py -q
```

Required local gate:

```text
python tools/quality/required_quality_gate.py
python tools/quality/module_quality_gate.py --module repo_guard
```

Commercialization gate:

```text
python tools/quality/module_quality_gate.py --module common_engine_commercialization
```

Live readiness is separate and must be explicitly approved:

```text
python tools/quality/module_quality_gate.py --module live_agent --include-live
python tools/quality/module_quality_gate.py --module release_runtime --include-live
```

## 11. Known WARN

- Gmail-specific remote execution still requires a Gmail-specific remote task
  verifier on top of the verified generic dispatch path.
- Reconnect/backoff and recovery behavior are locked in
  `docs/baseline/modules/LOCAL_AGENT_CONNECTION_RECOVERY_BASELINE.md`.
- Site/tool-specific commercial baselines must be added before claiming
  commercial readiness for each domain.
- Packaging and operations remain separate release stages.

## 12. Baseline Change Rule

Any change that weakens engine-first order, auth, approval, dispatch,
connection recovery, task/result redaction, evidence, or app control-surface
boundaries must be handled as:

```text
common engine commercialization baseline proposal
-> user approval
-> baseline update
-> audit/test/gate update
-> verification
-> report
```

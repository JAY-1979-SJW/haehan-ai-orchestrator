# HAEHAN Approval Flow Baseline

Status: LOCKED
Baseline ID: HAEHAN-APPROVAL-FLOW-BASELINE-01
Approved by: user approval in current Codex session
Baseline HEAD: ded4c078fe675ba1ee2e1b8434502606e8d5677a
Last updated: 2026-05-24

## 1. Purpose

This document locks the `approval_flow` module contract. Approval flow protects
high-risk work before it can enter execution. It creates approval requests,
uses the API approval path by default, records approved/denied/failed outcomes,
and updates task state without treating errors as approval.

Approval failure must fail closed.

## 2. Responsibility

`approval_flow` owns:

- high-risk task approval request creation
- API approval default flow
- approval/denial/failure result handling
- task state update after approval decision
- local UI fallback restriction
- safe failure handling when approval API is missing or fails
- safe approval audit summary

## 3. Input Contract

Allowed inputs:

- authenticated user identity
- task id
- risk level
- approval payload
- configured approval API endpoint
- explicit local UI fallback flag when approved for that environment

Rejected inputs:

- unauthenticated approval request
- approval request without task id
- approval request without risk classification
- unconfigured API endpoint treated as success
- approval payload containing raw secret, token, cookie, session, password, OTP,
  or Authorization header
- mock approval success in production

## 4. Output Contract

Allowed outputs:

- approved
- denied
- failed
- safe error summary
- task state update
- redacted approval audit event

Forbidden outputs:

- raw secret, token, cookie, session, password, OTP, or Authorization header
- mock approval success
- API failure disguised as approval success
- local UI fallback approval unless explicitly enabled

## 5. Authentication Boundary

Required rules:

- Approval requests must be tied to an authenticated user identity.
- Elevated approval decisions must pass the backend role/authorization boundary.
- Local-agent, desktop, admin-web, and AI-originated claims must not bypass
  backend approval checks.
- Approval audit logs must not print raw tokens or secret values.

## 6. Approval Boundary

Approval is required before execution for:

- submit
- upload
- send
- delete
- payment
- transfer
- bid
- signature
- registration
- external site state change
- local file or local app state change
- sensitive capture outside an explicitly safe dry-run

API approval is the default. Local UI fallback is allowed only when
`HAEHAN_LOCAL_APPROVAL_UI_FALLBACK=1` or an equivalent explicit approved setting
is present.

API misconfiguration, timeout, network failure, or denied response must not
transition the task to `queued`.

## 7. State Changes

Allowed approval state transitions:

```text
waiting_approval -> queued
waiting_approval -> denied
waiting_approval -> failed
```

Forbidden approval state transitions:

```text
waiting_approval -> queued
api_missing -> queued
api_failed -> queued
unauthenticated -> queued
denied -> queued
```

Only approved work may enter the local-agent dispatch queue.

## 8. Forbidden Approval Behavior

Runtime approval code must not:

- treat missing approval API configuration as approved
- treat approval API failure as approved
- enable local UI fallback by default
- accept unauthenticated approval
- log tokens, secrets, sessions, cookies, passwords, OTP values, or auth headers
- allow high-risk task queue entry without approval
- use mock approval success in production
- hide approval failure behind mock data

## 9. Allowed Paths

Approval flow work may modify approval server, approval policy, approval route,
task state, and focused approval tests only when the task explicitly approves
those paths.

Baseline and gate work may modify:

```text
docs/baseline/modules/APPROVAL_FLOW_BASELINE.md
docs/baseline/MODULE_BASELINE.md
tools/audits/app/audit_approval_flow_baseline_contract.py
tools/quality/module_quality_gate.py
tools/quality/required_quality_gate.py
tests/test_approval_flow_baseline_contract.py
tests/test_module_quality_gate.py
tests/test_required_quality_gate.py
```

## 10. Required Verification

Baseline verification:

```text
python tools/audits/app/audit_approval_flow_baseline_contract.py
python -m pytest tests/test_approval_flow_baseline_contract.py -q
```

Runtime/backend verification:

```text
python tools/quality/module_quality_gate.py --module backend_core
python tools/quality/module_quality_gate.py --module repo_guard
python tools/quality/required_quality_gate.py
```

## 11. Known WARN

- Real external approval API live verification is a separate approved stage.
- Organization-specific approval role matrix can be expanded later.
- Approval expiration, re-approval, and long-wait timeout policy need a future
  criterion.
- UI fallback behavior must stay opt-in and environment-specific.

## 12. Baseline Change Rule

Any approval change that weakens authentication, API-default behavior, safe
failure, local UI fallback restrictions, task state transitions, or redaction
must be handled as:

```text
approval_flow baseline proposal
-> user approval
-> baseline update
-> audit/test/gate update
-> verification
-> report
```


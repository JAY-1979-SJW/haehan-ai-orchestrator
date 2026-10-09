# HAEHAN Backend Core Baseline

Status: LOCKED
Baseline ID: HAEHAN-BACKEND-CORE-BASELINE-01
Approved by: user approval in current Codex session
Baseline HEAD: 3292091a1935febb16802f02bbbd6fd7a4bcf5d4
Last updated: 2026-05-24

## 1. Purpose

This document locks the `backend_core` module contract. The backend is the
authority for authentication, authorization, approval, task creation, queue
state, local-agent dispatch eligibility, result intake, and audit events.

The backend must coordinate local execution, not perform local execution.

## 2. Responsibility

`backend_core` owns:

- authentication defaults and enforcement
- user authorization and role checks
- approval policy and approval state
- task creation and validation
- task queue eligibility
- local-agent registration and authentication contract
- local-agent dispatch contract
- task status and result intake
- audit event creation
- safe API response shaping and redaction

## 3. Input Contract

Allowed inputs:

- authenticated user request
- approval request
- local-agent registration request
- local-agent WebSocket authentication using `agent_id + device_token`
- task status update
- task result update
- configuration values from approved config/env flow

Rejected inputs:

- unauthenticated user request for protected operations
- unapproved high-risk execution request
- hardcoded bearer token
- raw cookie/session/token/password/OTP values in task payloads
- task payloads that bypass the common tool runtime contract

## 4. Output Contract

Allowed outputs:

- task id
- task state
- approval decision
- redacted response body
- safe error summary
- audit event
- local-agent dispatch payload after auth/approval checks

Forbidden outputs:

- raw secret, token, password, cookie, session, OTP, or Authorization header
- auth failure disguised as mock success
- approval API failure disguised as approval success
- local-agent device token except during the approved one-time registration
  response

## 5. Authorization Boundary

Required backend auth rules:

- `AUTH_ENABLED` default must be safe.
- Production and compose defaults must not disable auth.
- Protected APIs must require authenticated users.
- Role checks must apply where routes require elevated authority.
- Local-agent WebSocket must require `agent_id + device_token`.
- Device token hashes are stored; raw device tokens are not persisted.
- High-risk tasks remain blocked until approval succeeds.

The backend must not trust desktop, admin-web, local-agent, or AI-originated
claims unless they pass the backend auth/authorization boundary.

## 6. Approval Boundary

Approval is required before task execution when an action can:

- submit
- upload
- send
- delete
- pay
- transfer
- bid
- sign
- register
- change an external site or local file state
- capture sensitive screen/file content outside an explicitly safe dry-run

Approval failure or approval API misconfiguration must return a safe failure,
not a fallback approval.

## 7. State Changes

Normal task state:

```text
queued -> delivered -> running -> completed | failed
```

Approval-gated state:

```text
waiting_approval -> queued -> delivered -> running -> completed | failed
waiting_approval -> denied
```

Cancellation state:

```text
queued -> cancelled
delivered | running -> cancel_requested -> cancelled | failed | completed
```

Invalid transitions are backend defects and must be blocked by tests or audits.

## 8. Forbidden Backend Behavior

Runtime backend code must not:

- run Playwright directly
- control a user's local browser directly
- access local PC files/apps directly
- use production mock auth
- default production auth to `AUTH_ENABLED=false`
- use `Bearer admin-token`
- use any hardcoded admin bearer token
- hide auth failures behind mock data
- hide approval failures behind fallback approval
- log raw secrets, tokens, cookies, sessions, passwords, OTP values, or auth
  headers
- dispatch unapproved high-risk work to a local agent
- bypass `common_tool_runtime` for executable task payloads

## 9. Allowed Paths

Backend core work may modify backend-owned route, service, policy, queue,
approval, persistence, and audit files when the task explicitly approves those
paths.

Baseline and gate work may modify:

```text
docs/baseline/modules/BACKEND_CORE_BASELINE.md
docs/baseline/MODULE_BASELINE.md
tools/audits/backend/audit_backend_core_baseline_contract.py
tools/quality/module_quality_gate.py
tools/quality/required_quality_gate.py
tests/test_backend_core_baseline_contract.py
tests/test_module_quality_gate.py
tests/test_required_quality_gate.py
```

## 10. Required Verification

Baseline verification:

```text
python tools/audits/backend/audit_backend_core_baseline_contract.py
python -m pytest tests/test_backend_core_baseline_contract.py -q
```

Runtime/backend verification:

```text
python tools/audits/backend/audit_backend_runtime_contract.py
python tools/quality/module_quality_gate.py --module backend_core
python tools/quality/module_quality_gate.py --module repo_guard
python tools/quality/required_quality_gate.py
```

## 11. Known WARN

- Full live server verification is a separate approved `release_runtime` stage.
- Database/persistence migration rules can be split into a later persistence
  module baseline.
- Organization-specific role/approval matrix can be expanded later.
- Long-running retry and recovery policy needs a future recovery baseline.

## 12. Baseline Change Rule

Any backend change that weakens auth, approval, dispatch, state transition,
redaction, or audit guarantees must be handled as:

```text
backend_core baseline proposal
-> user approval
-> baseline update
-> audit/test/gate update
-> verification
-> report
```


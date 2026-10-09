# HAEHAN Local Agent E2E Baseline

Status: LOCKED
Baseline ID: HAEHAN-LOCAL-AGENT-E2E-BASELINE-01
Approved by: user approval in current Codex session
Baseline HEAD: 6dfdc5d11636ea3ac0d902fc65e7ac8e090b4480
Last updated: 2026-05-25

## 1. Purpose

This document locks the `local_agent_e2e` module contract. The local agent may
execute work only when the server has authenticated the device, dispatched a
task through the approved queue contract, and the task has passed approval and
risk gates.

The local agent executes local work; it must not become a second policy engine
or a shortcut around the backend.

## 2. Responsibility

`local_agent_e2e` owns:

- authenticated local-agent WebSocket connection
- `agent_id + device_token` validation flow
- receiving only server-dispatched tasks
- task delivery acknowledgement
- running/completed/failed task status updates
- redacted result return
- unapproved high-risk task exclusion from dispatch
- safe failure reporting for rejected or malformed tasks

## 3. Input Contract

Allowed inputs:

- authenticated local-agent WebSocket
- server-dispatched task
- approved readonly browser task
- approved high-risk task after backend approval
- cancellation or status request from the server contract

Rejected inputs:

- unauthenticated WebSocket connection
- user-direct command that did not come from the server task queue
- unapproved high-risk task
- task payload containing raw secret, token, cookie, session, password, OTP, or
  Authorization header
- task payload that bypasses `common_tool_runtime`

## 4. Output Contract

Allowed outputs:

- delivered state update
- running state update
- completed state update
- failed state update
- cancelled state update
- redacted execution result
- safe error summary

Forbidden outputs:

- raw secret, token, cookie, session, password, OTP, or Authorization header
- browser credential material
- unrelated app runtime state
- unredacted prompt, page content, or file content outside an approved result
  contract

## 5. Authentication Boundary

Required rules:

- Local-agent WebSocket must require `agent_id + device_token`.
- Raw device token must not be logged.
- Raw device token may not be returned after the approved registration flow.
- A local agent must not receive tasks for another agent id.
- Authentication failure must fail closed and must not return mock data.

## 6. Approval Boundary

The local agent must not execute:

- unapproved browser write actions
- unapproved file upload/download/write/delete actions
- unapproved send, submit, payment, transfer, bid, signature, or registration
  actions
- any task that backend policy marks `waiting_approval`

Unapproved high-risk tasks must not appear in the local-agent dispatch queue.

## 7. State Changes

Dispatch concurrency rule:

- A single local-agent WebSocket session must receive at most one active task at
  a time.
- Concurrent server submissions must remain queued and drain one by one through
  `queued -> delivered -> running -> completed | failed` for that agent.
- True simultaneous local execution requires multiple registered agents or an
  explicitly approved multi-worker local-agent design.

Normal state:

```text
queued -> delivered -> running -> completed
queued -> delivered -> running -> failed
```

Approval-gated state:

```text
waiting_approval -> queued -> delivered -> running -> completed | failed
```

Cancellation state:

```text
queued -> cancelled
delivered | running -> cancel_requested -> cancelled | failed | completed
```

Invalid or out-of-order state transitions are defects.

## 8. Forbidden Local-Agent Behavior

Runtime local-agent code must not:

- execute server-contract-bypassing user-direct commands
- execute unapproved high-risk work
- accept unauthenticated WebSocket tasks
- return raw secrets, tokens, cookies, sessions, passwords, OTP values, or auth
  headers
- mix unrelated app UI/runtime state with this app
- start browser or AI work that was not dispatched by the server
- treat mock data as successful authenticated dispatch
- mutate external site, local file, or local app state during dry-run gates

## 9. Allowed Paths

Local-agent E2E work may modify local-agent dispatch, WebSocket, task status,
and focused E2E test files only when the task explicitly approves those paths.

Baseline and gate work may modify:

```text
docs/baseline/modules/LOCAL_AGENT_E2E_BASELINE.md
docs/baseline/MODULE_BASELINE.md
tools/audits/agent/audit_local_agent_e2e_baseline_contract.py
tools/quality/module_quality_gate.py
tools/quality/required_quality_gate.py
tests/test_local_agent_e2e_baseline_contract.py
tests/test_module_quality_gate.py
tests/test_required_quality_gate.py
```

## 10. Required Verification

Baseline verification:

```text
python tools/audits/agent/audit_local_agent_e2e_baseline_contract.py
python -m pytest tests/test_local_agent_e2e_baseline_contract.py -q
```

Runtime/local-agent verification:

```text
python tools/audits/agent/audit_local_agent_e2e_flow_contract.py
python tools/smoke/live_parallel_task_dispatch_smoke.py --temp-admin --count 5 --concurrency 5 --timeout 90
python tools/quality/module_quality_gate.py --module local_agent_e2e
python tools/quality/module_quality_gate.py --module repo_guard
python tools/quality/required_quality_gate.py
```

## 11. Known WARN

- Real local browser launch is a separate approved live/runtime stage.
- Network disconnect and reconnect recovery are locked separately in
  `docs/baseline/modules/LOCAL_AGENT_CONNECTION_RECOVERY_BASELINE.md`.
- Long-running task timeout and retry policy need a future module-specific
  criterion.
- Site-specific automation must be layered on top of the common tool runtime
  and approval boundaries.

## 12. Baseline Change Rule

Any local-agent change that weakens authentication, approval filtering, dispatch
source, state transitions, result redaction, or dry-run safety must be handled
as:

```text
local_agent_e2e baseline proposal
-> user approval
-> baseline update
-> audit/test/gate update
-> verification
-> report
```

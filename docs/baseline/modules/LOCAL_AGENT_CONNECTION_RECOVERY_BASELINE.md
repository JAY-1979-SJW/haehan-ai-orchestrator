# HAEHAN Local Agent Connection Recovery Baseline

Status: LOCKED
Baseline ID: HAEHAN-LOCAL-AGENT-CONNECTION-RECOVERY-BASELINE-01
Approved by: user approval in current Codex session
Baseline HEAD: 6a3d1d86d168ff3c70c8cf5b53e5b15cf75fe189
Last updated: 2026-05-25

## 1. Purpose

This document locks the connection readiness contract for the local agent. A
commercial app may rely on the local-agent connection only when registration,
token storage, WebSocket authentication, heartbeat, reconnect/backoff, task
dispatch, and user-safe recovery guidance are all covered by tests and audits.

## 2. Responsibility

`local_agent_connection_recovery` owns:

- local-agent registration and re-registration guidance
- stored credential presence checks without exposing raw values
- WebSocket authentication probe
- `AUTH_FAILED_4401` stale credential recovery
- heartbeat loss recovery
- reconnect/backoff policy
- server/network/proxy failure classification
- task dispatch readiness probe
- redacted user diagnostics

It does not own task execution policy or approval decisions. Those remain owned
by `backend_core`, `approval_flow`, and `local_agent_e2e`.

## 3. Required Connection States

The connection layer must classify these states:

- `NOT_REGISTERED`
- `CONNECTING`
- `AUTHENTICATING`
- `CONNECTED`
- `IDLE`
- `BUSY`
- `DISCONNECTED`
- `AUTH_FAILED`
- `SERVER_UNREACHABLE`
- `NETWORK_BLOCKED`

Unknown connection failure must be reported as a safe failure or warning. It
must not be reported as a successful live connection.

## 4. Recovery Contract

Required recovery behavior:

- Missing local credential -> `REGISTER_REQUIRED`
- Stale/rejected credential or WebSocket close `4401` -> `RE_REGISTER_REQUIRED`
- `AUTH_FAILED_4401` must not auto-retry indefinitely.
- `AUTH_FAILED_4401` must not automatically delete the saved token.
- Token reset must require explicit user confirmation.
- Server unreachable -> `CHECK_NETWORK_OR_SERVER`, auto retry allowed.
- Proxy/firewall blocked -> `CHECK_PROXY_OR_FIREWALL`, auto retry disabled.
- Heartbeat lost -> `AUTO_RECONNECT`, auto retry allowed.

Recovery guidance must never print raw registration codes, device tokens,
Authorization headers, cookies, sessions, passwords, OTPs, API keys, or
secrets.

## 5. Backoff Contract

The WebSocket client must use bounded reconnect backoff:

```text
initial backoff: 1 second
growth: exponential
maximum backoff: 60 seconds
jitter: up to 10 percent
reset: backoff resets after a normal session
```

The reconnect loop may retry transient network, server restart, and heartbeat
loss cases. It must not treat a permanent credential rejection as successful
connection.

## 6. Verification Contract

Static verification must confirm:

- connection diagnostic recovery plans exist
- `AUTH_FAILED_4401` maps to `RE_REGISTER_REQUIRED`
- heartbeat loss maps to `AUTO_RECONNECT`
- recovery rendering redacts credential-shaped values
- WebSocket probe reports close code `4401` as `AUTH_FAILED_4401`
- live task dispatch verifier supports authenticated task creation
- reconnect/backoff values are bounded

Live verification remains separate and must be explicitly approved:

```text
python verify_agent_ws_auth.py --server https://haehan-ai.kr/orchestrator --timeout 15
python verify_live_agent_smoke.py --server https://haehan-ai.kr/orchestrator --timeout 15
python verify_live_task_dispatch.py --server https://haehan-ai.kr/orchestrator --timeout 70 --temp-admin
```

## 7. Required Verification

Baseline verification:

```text
python tools/audits/agent/audit_local_agent_connection_recovery_baseline.py
python -m pytest tests/test_local_agent_connection_recovery_baseline.py -q
```

Module verification:

```text
python tools/quality/module_quality_gate.py --module local_agent_connection_recovery
python tools/quality/required_quality_gate.py
```

## 8. Known WARN

- Live connection checks depend on the current server and local credential and
  remain separate from the default local gate.
- Gmail-specific remote execution still requires a Gmail-specific task verifier.
- Organization-specific operator messaging can be refined in the app UI after
  this connection contract remains stable.

## 9. Baseline Change Rule

Any change that weakens registration recovery, stale token handling,
WebSocket auth failure mapping, reconnect/backoff bounds, failure
classification, task dispatch readiness, or redaction must be handled as:

```text
local agent connection recovery baseline proposal
-> user approval
-> baseline update
-> audit/test/gate update
-> verification
-> report
```

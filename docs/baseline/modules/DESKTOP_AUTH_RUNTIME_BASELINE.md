# HAEHAN Desktop Auth Runtime Baseline

Status: LOCKED
Baseline ID: HAEHAN-DESKTOP-AUTH-RUNTIME-BASELINE-01
Approved by: user approval in current Codex session
Baseline HEAD: 8ee20f1ba723e168f9449838f452a2775b050468
Last updated: 2026-05-24

## 1. Purpose

This document locks the `desktop_auth_runtime` module contract. The desktop
runtime may call protected server APIs only through configured auth/session
flows. It must fail safely when auth context is missing, and it must never use
hardcoded admin credentials or mock-auth shortcuts.

Desktop runtime authentication must be isolated from unrelated app UI, state,
and credentials.

## 2. Responsibility

`desktop_auth_runtime` owns:

- desktop server API call auth boundary
- configured session/auth context usage
- safe failure when token or session is unavailable
- task receiver auth header handling
- token masking and redaction
- desktop runtime state isolation
- static desktop auth/security checks
- safe diagnostics result without raw secrets

## 3. Input Contract

Allowed inputs:

- configured auth/session context
- server base URL
- task receiver request
- desktop runtime config
- local diagnostics request
- explicit user-approved live runtime check

Rejected inputs:

- hardcoded bearer token
- global `SESSION_ID` shortcut
- production mock auth
- raw secret, token, cookie, session, password, OTP, or Authorization header in
  diagnostics/log payload
- unrelated app UI or runtime state
- missing token/session when protected API call is required

## 4. Output Contract

Allowed outputs:

- authenticated outbound request
- safe failure when token/session unavailable
- redacted log message
- safe diagnostics result
- static runtime readiness result

Forbidden outputs:

- raw token
- raw session id
- raw cookie
- raw password
- raw OTP
- raw Authorization header
- mock success after auth failure
- unrelated app state

## 5. Authentication Boundary

Required rules:

- Token must come from configured settings, session, or approved environment
  flow only.
- If token/session is missing, protected requests must not be sent.
- Authorization header values must never be printed.
- Token values must be masked in logs and diagnostics.
- `Bearer admin-token` is forbidden.
- hardcoded admin bearer is forbidden.
- production mock auth is forbidden.

## 6. Runtime Isolation Boundary

Desktop runtime must not:

- mix unrelated app UI state with this app
- reuse global session shortcuts
- read unrelated app credential stores
- write unrelated app runtime files
- treat diagnostics as an authenticated request source
- bypass backend auth, approval, task, or local-agent dispatch rules

## 7. Forbidden Desktop Behavior

Runtime desktop code must not:

- use `Bearer admin-token`
- use hardcoded admin bearer
- use global `SESSION_ID`
- use production mock auth
- log raw token, secret, session, cookie, password, OTP, or auth header
- send protected API requests without token/session
- hide auth failure behind mock success
- mix unrelated app UI/runtime state with this app

## 8. Allowed Paths

Desktop auth runtime work may modify desktop runtime auth, diagnostics, task
receiver, and focused desktop auth tests only when the task explicitly approves
those paths.

Baseline and gate work may modify:

```text
docs/baseline/modules/DESKTOP_AUTH_RUNTIME_BASELINE.md
docs/baseline/MODULE_BASELINE.md
tools/audits/agent/audit_desktop_auth_runtime_baseline_contract.py
tools/quality/module_quality_gate.py
tools/quality/required_quality_gate.py
tests/test_desktop_auth_runtime_baseline_contract.py
tests/test_module_quality_gate.py
tests/test_required_quality_gate.py
```

## 9. Required Verification

Baseline verification:

```text
python tools/audits/agent/audit_desktop_auth_runtime_baseline_contract.py
python -m pytest tests/test_desktop_auth_runtime_baseline_contract.py -q
```

Runtime/desktop verification:

```text
python tools/quality/module_quality_gate.py --module desktop_auth_runtime
python tools/quality/module_quality_gate.py --module repo_guard
python tools/quality/required_quality_gate.py
```

Live desktop app execution is separate and requires explicit approval.

## 10. Known WARN

- Actual desktop app launch is a separate approved runtime stage.
- Actual server connectivity is a separate approved live check.
- Installer and portable packaging are separate approved stages.
- OS credential storage policy may need a future platform-specific baseline.

## 11. Learning Notes

Hardcoded bearer is dangerous because anyone with the code has the credential
shape and may bypass the normal auth flow.

Not sending a request when token is missing prevents accidental unauthenticated
or mock-auth success paths.

Global `SESSION_ID` shortcut is dangerous because it can cross users, devices,
or unrelated runtime contexts.

Redacted logs are required because diagnostics and error reports are often
shared during troubleshooting.

Desktop runtime state isolation prevents this app from reading, mutating, or
trusting unrelated app UI and credential state.

## 12. Baseline Change Rule

Any desktop change that weakens auth context usage, token masking, safe failure,
runtime isolation, or hardcoded credential prohibitions must be handled as:

```text
desktop_auth_runtime baseline proposal
-> user approval
-> baseline update
-> audit/test/gate update
-> verification
-> report
```


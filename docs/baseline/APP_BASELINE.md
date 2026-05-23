# HAEHAN App Baseline

Status: LOCKED
Baseline ID: HAEHAN-APP-BASELINE-01
Approved by: user approval in current Codex session
Baseline HEAD: df0c21f0fb68f8f69adb81760a071042d636d1ed
Last updated: 2026-05-24

## 1. Purpose

HAEHAN AI Orchestrator receives authenticated user instructions on the server,
checks authorization, approval, execution location, and safety policy, then
dispatches safe work to a local PC agent when local browser or local tool
execution is required.

The app must preserve these roles:

- Server: authentication, authorization, approval, task creation, policy
  decisions, queue/status management, result intake, and audit events.
- Local agent: authenticated PC-side execution for tasks dispatched by the
  server.
- Browser automation: local-only execution through the local agent.
- AI: instruction interpretation and task assistance. AI must not bypass auth,
  approval, execution-location, or secret-redaction gates.

## 2. Canonical Runtime Flow

The canonical flow is:

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

The currently locked dry-run/in-memory flow is:

```text
approved user
-> readonly browser instruction
-> queued
-> WebSocket auth
-> delivered
-> running
-> completed
```

This flow is enforced by:

```text
python scripts/ops/audit_local_agent_e2e_flow_contract.py
python scripts/module_quality_gate.py --module local_agent_e2e
```

## 3. Execution Boundaries

Server must not:

- Run Playwright directly.
- Control a user's local browser directly.
- Access local files or local apps directly.
- Use hardcoded admin bearer headers.
- Use production mock-auth fallback.
- Hide auth/approval failures behind mock data.
- Print raw secrets, tokens, passwords, cookies, sessions, or OTP values.

Local agent must:

- Authenticate to the server with `agent_id + device_token`.
- Execute only tasks dispatched by the server.
- Return safe, redacted results.
- Refuse high-risk tasks that did not pass approval.

Local agent must not:

- Execute unapproved high-risk work.
- Execute user-supplied work that did not come through the server task contract.
- Return raw tokens, cookies, sessions, passwords, OTP values, or raw auth
  headers.
- Mix this app's runtime with unrelated app UI/state.

## 4. Auth And Approval Rules

Required rules:

- `AUTH_ENABLED` default must be safe: `true`.
- Production and compose defaults must not disable auth.
- User-facing APIs must pass role checks where applicable.
- Local agent WebSocket must require `agent_id + device_token`.
- Device token may be returned only once during registration.
- Server stores token hashes, not raw device tokens.
- High-risk tasks remain `waiting_approval` until approved.
- Unapproved high-risk tasks must not appear in the local-agent dispatch queue.

Approval is required for:

- Browser write actions.
- File upload, submit, send, delete, payment, transfer, bid, signature, or
  registration actions.
- Screenshot/capture actions unless explicitly classified as safe dry-run.
- Any action that changes external state.

## 5. State Transition Rules

Normal local-agent task state:

```text
queued -> delivered -> running -> completed | failed
```

Approval-gated task state:

```text
waiting_approval -> queued -> delivered -> running -> completed | failed
```

Cancellation state:

```text
queued -> cancelled
delivered | running -> cancel_requested -> cancelled | failed | completed
```

Invalid state transitions are defects and must be blocked by tests or gates.

## 6. Security Prohibitions

These patterns are forbidden in runtime code:

- `Bearer admin-token`
- `Authorization ... admin-token`
- unsafe `AUTH_ENABLED=false` production defaults
- production mock auth
- auth failure masked as mock success
- raw secret/token/password/session/cookie/OTP logging
- `/tmp` boundary checks using plain `startswith('/tmp')`
- server-side Playwright execution
- unapproved browser write execution
- installer/build/deploy commands inside dry-run gates

## 7. Out-Of-Scope Files

These files must not be modified, staged, or committed unless a future approved
task explicitly changes their scope:

```text
scripts/archive/data/chrome_ui_monitor_state.json
scripts/ops/check_naver_mail.py
scripts/ops/check_remote_browser.py
scripts/ops/naver_login_and_mail.py
scripts/ops/verify_remote_browser.py
```

## 8. Module Baseline

The current operational modules are:

```text
repo_guard
common_tool_runtime
backend_core
local_agent_e2e
desktop_auth_runtime
portable_install
playwright_ai
live_agent
release_preflight
release_runtime
```

Module responsibilities:

- `common_tool_runtime`: common execution task/result contract, risk level,
  approval requirements, and forbidden field checks.
- `backend_core`: backend route inventory, auth/security defaults, and server
  execution boundaries.
- `local_agent_e2e`: server queue to authenticated local-agent WebSocket to
  result contract.
- `desktop_auth_runtime`: desktop runtime auth and static runtime checks.
- `playwright_ai`: local Playwright and AI proxy no-secret contract.
- `live_agent`: live server connectivity and task dispatch smoke checks.
- `release_preflight`: release-time static checks.
- `release_runtime`: live runtime readiness checks.

The detailed module contract is locked in:

```text
docs/baseline/MODULE_BASELINE.md
```

## 9. Required Gates

The required local gate is:

```text
python scripts/required_quality_gate.py
```

Required module gates include:

```text
python scripts/module_quality_gate.py --module repo_guard
python scripts/module_quality_gate.py --module backend_core
python scripts/module_quality_gate.py --module local_agent_e2e
```

Required audits include:

```text
python scripts/ops/audit_common_tool_runtime.py
python scripts/ops/audit_backend_runtime_contract.py
python scripts/ops/audit_local_agent_e2e_flow_contract.py
python scripts/ops/audit_module_boundaries.py
python scripts/ops/audit_root_legacy_scripts.py
```

Any code change that affects server/local-agent/browser/approval behavior must
state how it satisfies this baseline:

```text
input/output contract
authorization boundary
state changes
regression gate
```

All work must also follow the locked standard workflow and reporting template:

```text
docs/baseline/STANDARD_WORKFLOW.md
docs/templates/STANDARD_REPORT_TEMPLATE.md
```

The standard workflow controls task scoping, user approval, forbidden actions,
verification, recovery, function-level explanation, and final reporting.

## 10. Release And Install Rules

Before release or installer/portable work:

- Worktree must be clean except explicitly approved files.
- OUT_OF_SCOPE files must not be staged.
- Required local quality gate must pass.
- `backend_core` and `local_agent_e2e` module gates must pass.
- Secret scan must not show live secrets.
- Live server/local browser checks must be separate from build/installer work.
- Installer build, Docker deploy, server deploy, and push require explicit
  approval for that stage.

## 11. Failure And Recovery Rules

Failures must not be hidden behind mock success.

Failure cases must end as one of:

- `blocked`
- `failed`
- `cancelled`
- `waiting_approval`

Recovery rules:

- Record a safe error summary without raw secrets.
- Preserve task state for diagnosis.
- Separate server failure, local-agent failure, browser failure, and site
  failure in reports.
- Retry only when an explicit retry policy exists.
- Keep dry-run checks side-effect free.

## 12. Current PASS Scope

Currently locked as PASS:

- Common tool runtime contract.
- Backend runtime route/security contract.
- Local-agent E2E dispatch flow contract.
- Required local quality gate.
- Repo guard.
- OUT_OF_SCOPE preservation.

The current operationally verified dry-run scope is:

- Authenticated user can queue readonly browser work.
- Authenticated local agent can receive dispatched work.
- Task transitions `queued -> delivered -> running -> completed`.
- Dispatch/final response contain no forbidden secret fields.
- Unapproved high-risk work is excluded from dispatch.

## 13. Known WARN

These remain WARN, not PASS:

- Full live server -> local agent -> real browser -> real site E2E needs a
  separate live verification stage.
- Naver/mail/site-specific tools are not yet locked by module-specific
  baselines on top of the common rail.
- Long-running recovery, network disconnect recovery, browser-not-installed
  recovery, site blocking, and login expiry recovery need module-specific
  criteria.
- Module-specific baseline documents are still pending.

## 14. Baseline Change Rule

This baseline is the top-level source of truth for app development.

Any change that weakens this document must be handled as a governance/security
change:

```text
baseline change proposal
-> user approval
-> code/test/gate update
-> verification
-> commit
```

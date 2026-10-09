# HAEHAN App Baseline

Status: LOCKED
Baseline ID: HAEHAN-APP-BASELINE-01
Approved by: user approval in current Codex session
Baseline HEAD: df0c21f0fb68f8f69adb81760a071042d636d1ed
Last updated: 2026-05-24

## 1. Purpose

The server is the final operational source of truth for HAEHAN.

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

## 1.1 Final Server Baseline

The final runtime baseline is server-first:

- The server owns identity, authorization, approval, policy, task queue, task
  state, result intake, audit records, and release/deploy decisions.
- Desktop and local-agent code are subordinate execution layers. They may run
  local UI, local tools, browser automation, and recovery probes only after the
  server contract allows or dispatches that work.
- Desktop and local-agent code must not become an independent source of truth
  for task state, approval, user identity, policy, or audit history.
- Desktop and local-agent code must not register persistent autostart,
  background recovery, or always-on monitoring unless a server-baseline task
  explicitly approves that runtime behavior.
- A local cleanup or desktop build may remove legacy execution paths only when
  the result keeps the server as the final operational baseline.

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
python tools/audits/agent/audit_local_agent_e2e_flow_contract.py
python tools/quality/module_quality_gate.py --module local_agent_e2e
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

## 5.1 Task History And Audit Log Rule

Task history and audit logs must be recorded. The server task state and server
audit events are the final source of truth.

Required task/audit records should include:

```text
task_id
masked agent_id
user or organization reference
requested action
tool_id or module
execution location
approval requirement
approval status
state transition
started_at
ended_at
result status
safe summary
error code
verification reference
report path
```

Local-agent and desktop logs are diagnostic evidence only. They must not become
the final source of truth for task history, approval, policy, state, or audit.

Task history and audit logs must not contain raw secrets, tokens, cookies,
sessions, passwords, OTP values, approval tokens, raw auth headers, sensitive
personal data, full sensitive local file paths, full page HTML, or automatic
raw screenshot captures.

Invalid state transitions are defects and must be blocked by tests or gates.

## 5.2 User Data Contribution Consent Rule

Task history, safe summaries, tool outcomes, verification evidence, and user
feedback may be used as product improvement or development material only after
an explicit user data contribution consent is recorded by the server.

The server must store the consent record as the final source of truth. Consent
must be separate from normal service use, specific to the allowed data
categories and purposes, revocable, and linked to retention and deletion rules.

Allowed development material is limited to redacted, minimized, purpose-bound
records such as:

```text
task category
tool_id or module
safe user intent summary
safe result summary
error code
state transition
verification reference
user feedback
masked organization or user reference
```

Development datasets must not contain raw user prompts, raw files, raw page
content, raw screenshots, raw emails, raw document bodies, raw browser traces,
secrets, credentials, tokens, cookies, sessions, passwords, OTP values,
approval tokens, raw auth headers, sensitive personal data, or unrelated
third-party content.

No task record may be used for product improvement, model training, benchmark
creation, quality analysis, or feature planning when consent is missing,
expired, revoked, or outside the recorded purpose.

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
common_engine_commercialization
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
- `common_engine_commercialization`: engine-first commercial readiness contract
  that composes common runtime, backend, approval, local-agent, connection,
  evidence, and app control-surface boundaries.

The detailed module contract is locked in:

```text
docs/baseline/MODULE_BASELINE.md
```

Commercial app development must also satisfy:

```text
docs/baseline/modules/COMMON_ENGINE_COMMERCIALIZATION_BASELINE.md
docs/baseline/APP_DEVELOPMENT_STANDARD.md
```

## 9. Required Gates

The required local gate is:

```text
python tools/quality/required_quality_gate.py
```

Required module gates include:

```text
python tools/quality/module_quality_gate.py --module repo_guard
python tools/quality/module_quality_gate.py --module backend_core
python tools/quality/module_quality_gate.py --module local_agent_e2e
```

Required audits include:

```text
python tools/audits/agent/audit_common_tool_runtime.py
python tools/audits/backend/audit_backend_runtime_contract.py
python tools/audits/agent/audit_local_agent_e2e_flow_contract.py
python tools/audits/app/audit_module_boundaries.py
python tools/repo_gates/audit_root_legacy_scripts.py
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
docs/baseline/APP_DEVELOPMENT_STANDARD.md
docs/templates/STANDARD_REPORT_TEMPLATE.md
```

The standard workflow controls task scoping, user approval, forbidden actions,
verification, recovery, function-level explanation, and final reporting.
The app development standard controls app shell, route, screen, API integration,
privacy, and UI completion requirements.
The app connection and command system is locked by
`docs/baseline/APP_DEVELOPMENT_STANDARD.md` sections 9.1 and 9.2: only inventoried `active` or `locked` tools may be attached to executable UI, routes, server actions, or local-agent dispatch.
The executable connection structure is locked by
`docs/inventory/CONNECTION_INVENTORY.md`: app UI may submit server actions and
display server-owned connection status, but it must not bypass the server-first
task queue, approval gate, local-agent WebSocket authentication, server state
update, or audit event path.

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

For server deployment, local verification is not the final verdict. The final
deployment verdict requires:

- the server repository HEAD matches the intended release HEAD
- server-local uncommitted changes are preserved or explicitly reported before
  pull/build/replacement
- server-only secret override files remain uncommitted unless separately
  approved
- server smoke checks pass through the public route or server-side nginx route
- server stress checks pass through the public route or server-side nginx route
- post-deploy logs are checked for new runtime errors

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
- Common engine commercialization baseline.
- Required local quality gate.
- Repo guard.
- OUT_OF_SCOPE preservation.

The current operationally verified dry-run scope is:

- Authenticated user can queue readonly browser work.
- Authenticated local agent can receive dispatched work.
- Task transitions `queued -> delivered -> running -> completed`.
- Concurrent server task submissions are accepted and completed without loss;
  a single local agent drains them sequentially, while true simultaneous local
  execution requires multiple agents or an approved multi-worker design.
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

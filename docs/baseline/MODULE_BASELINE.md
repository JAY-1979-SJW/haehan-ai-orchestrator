# HAEHAN Module Baseline

Status: LOCKED
Baseline ID: HAEHAN-MODULE-BASELINE-01
Approved by: user approval in current Codex session
Baseline HEAD: 4d16cfe25e6f456ccb73f499de8f9ffc577f310b
Last updated: 2026-05-24

## 1. Purpose

This document locks the current module boundaries for HAEHAN AI Orchestrator.
It explains what each module owns, what it may receive, what it may return,
which paths are allowed, which behavior is forbidden, and which gates prove the
contract.

Every module change must satisfy:

```text
responsibility
input
output
allowed paths
forbidden behavior
security boundary
state changes
required verification
known WARN
```

## 2. Global Module Rules

All modules must follow:

- `docs/baseline/APP_BASELINE.md`
- `docs/baseline/STANDARD_WORKFLOW.md`
- `docs/templates/STANDARD_REPORT_TEMPLATE.md`

Global prohibitions:

- no raw secret, token, cookie, session, password, or OTP output
- no hardcoded admin bearer header
- no production mock-auth fallback
- no build, installer, Docker, deploy, or push inside dry-run gates
- no OUT_OF_SCOPE file modification, staging, or commit
- no server-side local browser execution
- no unapproved high-risk browser write execution

## 3. Module Contracts

### repo_guard

- Responsibility: repository-level guardrails, OUT_OF_SCOPE staging checks,
  forbidden command matrix, gate wiring, baseline presence, module boundaries,
  and root legacy script inventory.
- Input: repository files, git status, configured gate command lists.
- Output: PASS/FAIL guardrail result and safe diagnostic messages.
- Allowed paths: `tools/quality/module_quality_gate.py`, `tools/quality/required_quality_gate.py`,
  `.githooks/`, `docs/baseline/`, `docs/architecture/`, `tests/test_*gate*.py`,
  and read-only audit scripts under `scripts/ops/`.
- Forbidden behavior: build, deploy, Docker, installer, push, dependency install,
  broad cleanup, or raw secret output.
- Security boundary: must prevent forbidden commands and staged OUT_OF_SCOPE
  files from entering commits.
- State changes: none during audits except normal test/cache files outside git
  scope.
- Required verification: `python tools/quality/module_quality_gate.py --module repo_guard`
  and `python tools/quality/required_quality_gate.py`.
- Known WARN: does not replace live runtime verification.

### backend_core

Detailed baseline:

```text
docs/baseline/modules/BACKEND_CORE_BASELINE.md
```

- Responsibility: server routes, authentication defaults, authorization,
  approval policy, task queue, state transitions, result intake, and audit
  events.
- Input: authenticated user requests, approved task commands, local-agent status
  updates, and safe result payloads.
- Output: task ids, task state, redacted results, approval decisions, and audit
  records.
- Allowed paths: backend API, service, persistence, security, approval, task,
  and backend contract audit/test files.
- Forbidden behavior: `AUTH_ENABLED=false` production default, mock-auth
  production fallback, hardcoded admin bearer, server-side Playwright execution,
  auth failure masked as mock success, or raw secret logging.
- Security boundary: user auth, role checks, approval gating, local-agent device
  auth, and result redaction are owned here.
- State changes: task lifecycle, approval status, audit events, and persisted
  server state only through approved services.
- Required verification: backend contract audit, backend auth/security tests,
  and `python tools/quality/module_quality_gate.py --module backend_core`.
- Known WARN: full live server integration remains a separately approved stage.

### common_tool_runtime

Detailed baseline:

```text
docs/baseline/modules/COMMON_TOOL_RUNTIME_BASELINE.md
```

- Responsibility: shared task/result contract, tool risk classification,
  approval requirement checks, safe execution metadata, and forbidden field
  rejection.
- Input: normalized tool task requests and execution context.
- Output: accepted/rejected task contract, risk level, approval requirement,
  and redacted result metadata.
- Allowed paths: `ai_orchestrator/local_agent/common_tool_runtime.py`,
  related common runtime tests, and common runtime audit scripts.
- Forbidden behavior: direct browser execution, raw auth header forwarding,
  sensitive field acceptance, or bypassing approval-required risk flags.
- Security boundary: blocks unsafe task fields before any module executes work.
- State changes: none except explicit task/result values returned to caller.
- Required verification: `python tools/audits/agent/audit_common_tool_runtime.py` and
  `tests/test_common_tool_runtime.py`.
- Known WARN: site-specific tools still need individual profiles on top of this
  shared contract.

### common_engine_commercialization

Detailed baseline:

```text
docs/baseline/modules/COMMON_ENGINE_COMMERCIALIZATION_BASELINE.md
```

- Responsibility: engine-first commercial readiness across common runtime,
  backend auth, approval, local-agent dispatch, connection recovery, task
  evidence, and app control surface boundaries.
- Input: locked lower-level module baselines, verified live/local-agent
  connection evidence, normalized task/result contracts, and app development
  proposals.
- Output: PASS/FAIL readiness result, safe commercialization order, required
  verification matrix, and blocked status when app work would bypass the engine.
- Allowed paths: common engine commercialization baseline, its audit/test files,
  APP_BASELINE, MODULE_BASELINE, and gate wiring.
- Forbidden behavior: app UI first execution shortcuts, mock success for live
  failure, direct local tool/browser execution from app UI, approval bypass, or
  raw secret/session/token/cookie output.
- Security boundary: app work may only operate as an app control surface over
  authenticated, approval-safe, auditable engine APIs.
- State changes: none during the baseline audit; runtime task state remains
  owned by backend_core and local_agent_e2e.
- Required verification:
  `python tools/audits/app/audit_common_engine_commercialization_baseline.py`,
  `python -m pytest tests/test_common_engine_commercialization_baseline.py -q`,
  and `python tools/quality/module_quality_gate.py --module common_engine_commercialization`.
- Known WARN: Gmail-specific remote execution, reconnect/backoff implementation,
  and domain-specific commercial baselines still require follow-up work.

### local_agent_e2e

Detailed baseline:

```text
docs/baseline/modules/LOCAL_AGENT_E2E_BASELINE.md
```

- Responsibility: server queue to authenticated local-agent WebSocket dispatch,
  task delivery, task running/completion transitions, and safe result return.
- Input: queued server tasks and authenticated `agent_id + device_token`
  connection.
- Output: delivered task payloads, state updates, redacted completion/failure
  results.
- Allowed paths: local-agent dispatch tests, server queue tests, WebSocket auth
  contract tests, and local-agent E2E audit scripts.
- Forbidden behavior: delivering unapproved high-risk tasks, accepting raw user
  work outside the server contract, returning raw secrets, or mixing unrelated
  app runtime state.
- Security boundary: device-token authentication and dispatch filtering.
- State changes: `queued -> delivered -> running -> completed | failed` and
  approved `waiting_approval -> queued` transitions.
- Required verification: `python tools/audits/agent/audit_local_agent_e2e_flow_contract.py`
  and `python tools/quality/module_quality_gate.py --module local_agent_e2e`.
- Known WARN: disconnect/retry recovery requires a future module-specific
  recovery baseline.

### local_agent_connection_recovery

Detailed baseline:

```text
docs/baseline/modules/LOCAL_AGENT_CONNECTION_RECOVERY_BASELINE.md
```

- Responsibility: local-agent registration repair, stale credential recovery,
  WebSocket authentication probing, heartbeat loss handling, reconnect/backoff,
  server/network/proxy failure classification, and redacted diagnostics.
- Input: configured server URL, masked local agent identity, stored credential
  presence, WebSocket close/error status, heartbeat state, and dispatch probe
  result.
- Output: PASS/FAIL connection readiness, safe recovery plan, redacted user
  diagnostics, and live-check commands that do not reveal raw credentials.
- Allowed paths: local-agent connection diagnostics, WebSocket client,
  connection/live verification scripts, connection recovery baseline, and
  focused tests/audits.
- Forbidden behavior: raw token/code/cookie/session/password output,
  indefinite retry on `AUTH_FAILED_4401`, automatic token deletion without user
  confirmation, mock success for auth/network failure, or app UI direct
  reconnect shortcuts outside the engine contract.
- Security boundary: connection repair may guide registration/reset but may not
  bypass backend auth, approval, task dispatch, or credential redaction.
- State changes: no state changes during static audits; live checks may only
  perform approved auth/heartbeat/readonly dispatch probes.
- Required verification:
  `python tools/audits/agent/audit_local_agent_connection_recovery_baseline.py`,
  `python -m pytest tests/test_local_agent_connection_recovery_baseline.py -q`,
  and `python tools/quality/module_quality_gate.py --module local_agent_connection_recovery`.
- Known WARN: live checks depend on current server and local credential, and
  Gmail-specific remote execution is separate.

### approval_flow

Detailed baseline:

```text
docs/baseline/modules/APPROVAL_FLOW_BASELINE.md
```

- Responsibility: approval decision routing, API approval default flow, local
  UI fallback only when explicitly enabled, and high-risk action blocking.
- Input: user identity, task risk, approval request payload, and configured
  approval API endpoint.
- Output: approved/denied decision and safe error summary.
- Allowed paths: approval server, approval policy tests, approval audit scripts,
  and approval-related backend service files.
- Forbidden behavior: default local UI fallback, approval success on API failure,
  unauthenticated approval, or token/secret logging.
- Security boundary: high-risk browser/file/external state changes cannot enter
  execution without an authenticated approval decision.
- State changes: `waiting_approval`, approved, denied, and safe failure states.
- Required verification: approval pytest, approval API default audit, and
  backend/module gates that include approval behavior.
- Known WARN: organization-specific approval roles can be expanded later.

### playwright_ai

Detailed baseline:

```text
docs/baseline/modules/PLAYWRIGHT_AI_BASELINE.md
```

- Responsibility: local-only browser automation and AI-assisted task planning
  through approved local-agent execution paths.
- Input: approved browser task contract, safe URL/action parameters, AI prompt
  context that excludes raw secrets.
- Output: redacted browser observations, screenshots only when approved, and
  safe task result summaries.
- Allowed paths: local browser adapter, CDP/Playwright dry-run scripts, AI proxy
  tests, and browser runtime operating rules.
- Forbidden behavior: server-side Playwright execution, credential extraction,
  cookie/session export, unapproved write actions, or raw prompt/secret output.
- Security boundary: browser automation must stay local and must respect
  approval and redaction gates.
- State changes: browser state only during explicitly approved live checks;
  dry-runs remain side-effect free.
- Required verification: local browser runtime rules, CDP attach dry-run, and
  Playwright/AI no-secret tests.
- Known WARN: real site behavior depends on a separately approved live stage.

### desktop_auth_runtime

Detailed baseline:

```text
docs/baseline/modules/DESKTOP_AUTH_RUNTIME_BASELINE.md
```

- Responsibility: desktop runtime authentication, task receiver auth headers,
  desktop security boundary checks, and prevention of cross-app shortcuts.
- Input: configured session/auth context and server task receiver requests.
- Output: authenticated outbound requests or safe failure when token/session is
  unavailable.
- Allowed paths: `desktop/`, desktop auth tests, desktop security audit checks,
  and task receiver tests.
- Forbidden behavior: hardcoded `Bearer admin-token`, global session shortcuts,
  production mock auth, or logging token values.
- Security boundary: desktop may call protected APIs only through configured
  auth/session flows.
- State changes: local runtime state only inside approved desktop app paths.
- Required verification: desktop security boundary gate and focused desktop
  auth tests.
- Known WARN: full packaged desktop runtime is still separate from installer
  build work.

### portable_install

Detailed baseline:

```text
docs/baseline/modules/PORTABLE_INSTALL_BASELINE.md
```

- Responsibility: portable ZIP install/start/diagnostics/uninstall scripts and
  user-facing no-admin installation flow.
- Input: extracted app folder and user execution of `.bat` files.
- Output: desktop shortcut, logs/config folders, diagnostics log, and safe start
  guidance.
- Allowed paths: portable `.bat` files, README execution guide, portable install
  verifier, and portable install tests.
- Forbidden behavior: installer exe build, Program Files copy, registry edit,
  PATH edit, app/log/config deletion during uninstall, Docker/server deploy, or
  secret output.
- Security boundary: diagnostics must mask secrets and avoid system-wide changes.
- State changes: shortcut creation/removal and logs/config directory creation.
- Required verification: portable ZIP install verifier and static `.bat` checks.
- Known WARN: actual user-machine runtime needs a separate manual/live check.

### release_preflight

Detailed baseline:

```text
docs/baseline/modules/RELEASE_PREFLIGHT_BASELINE.md
```

- Responsibility: static release readiness checks, admin-web checks, secret
  scan classification, UI residue audit, and no-build preflight verification.
- Input: source tree, package scripts, static audit rules, and test fixtures.
- Output: PASS/WARN/FAIL release readiness summary.
- Allowed paths: release preflight scripts, UI residue audit/cleanup helpers,
  admin-web static test files, and release preflight reports.
- Forbidden behavior: actual build, installer creation, deploy, Docker, push,
  dependency install, or hiding secret findings.
- Security boundary: blocks release progression when active-source risks remain.
- State changes: none beyond safe reports/logs when approved.
- Required verification: release preflight module gate and secret scan audit.
- Known WARN: Docker CLI absence is environment WARN, not app code failure.

### release_runtime

- Responsibility: live runtime readiness checks after explicit approval,
  including server/local-agent/browser connectivity and recovery reporting.
- Input: approved live environment, configured server URL, local agent token,
  and allowed smoke scenario.
- Output: redacted live smoke result, connection status, and recovery findings.
- Allowed paths: live smoke scripts, runtime verification reports, and
  explicitly approved local runtime logs.
- Forbidden behavior: live checks without approval, secret output, broad browser
  automation outside scenario, deploy/build/install side effects, or unrelated
  app state cleanup.
- Security boundary: live runtime must prove connectivity without weakening
  auth, approval, or local execution boundaries.
- State changes: only the explicitly approved live smoke task and its audit
  state.
- Required verification: live smoke checks only with `--include-live` or a
  specific approved command.
- Known WARN: not part of default required local gate.

## 4. Baseline Change Rule

Any change that moves responsibility, expands allowed paths, weakens forbidden
behavior, or changes required verification must be treated as a module baseline
change:

```text
module baseline proposal
-> user approval
-> document update
-> audit/test/gate update
-> verification
-> report
```

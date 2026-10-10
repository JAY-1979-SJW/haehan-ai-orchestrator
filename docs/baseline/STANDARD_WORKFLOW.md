# HAEHAN Standard Workflow

Status: LOCKED
Baseline ID: HAEHAN-STANDARD-WORKFLOW-01
Approved by: user approval in current Codex session
Baseline HEAD: 796ebc2e22b0c7f536fa606ddec83c582aee6448
Last updated: 2026-05-26

## 1. Purpose

This document defines the standard working contract for every HAEHAN code,
documentation, gate, test, release, and verification task.

No task should move directly into code edits unless the task scope, allowed
files, forbidden actions, verification plan, and reporting format are clear.

## 2. Standard Task Flow

Every non-trivial task follows this flow:

```text
task request
-> baseline and scope check
-> work overview and approval mode summary
-> working standard confirmation
-> user approval when the scope changes governance, deploy, build, push, or live runtime
-> implementation inside the approved scope
-> focused verification
-> gate verification
-> standard report
-> commit only when requested or when the approved task includes commit
```

## 2.1 Work Overview And Final-Approval-Only Rule

For non-trivial tasks, the worker should start by giving the user a concise
work overview before implementation. The overview must cover:

```text
goal
target app or repository
server-first baseline impact
major work steps
expected verification
state-changing or final-approval-only actions
commit, push, deploy, or live-runtime boundary
```

Once the user approves that overview, the worker proceeds inside the approved
scope without repeatedly asking "how should I proceed?" for intermediate
implementation choices. The default operating mode is:

```text
one overview approval
-> autonomous preparation, implementation, validation, and reporting
-> stop only for blockers, scope changes, secrets, live runtime, deploy, push,
   or final state-changing approval
-> user performs the final approval action only
```

This rule does not authorize hidden state changes. Create, Save, Submit,
Consent, Publish, Delete, payment, permission grant, deploy, restart, secret
entry, and other state-changing actions remain final user approval points unless
the user has separately approved that exact execution stage.

## 3. Required Pre-Work Check

Before editing code, the worker must identify:

```text
goal
scope
allowed files
forbidden actions
input/output contract
authorization boundary
state changes
regression gate
verification commands
rollback or recovery plan
```

When any of these are unknown and cannot be inferred from the repository, stop
and ask the user before editing runtime code.

## 3.1 Target App Scope Rule

For baseline work, cleanup, runtime inspection, and recovery work, the worker
must act only on the approved target app or repository.

If another app, workspace, server, browser, test runner, or background process
is discovered while inspecting the target app:

- identify it as external to the approved scope
- report the finding and likely impact
- do not stop, modify, delete, stage, or commit anything for that external app
- ask for separate approval before taking any action on that external app

External-app findings may be used as diagnostic context, but they must not
change the target app baseline or cleanup scope.

## 3.2 Server-First Operating Rule

The server is the final operational source of truth for HAEHAN. For any work
that touches runtime behavior, connectivity, recovery, monitoring, desktop,
local-agent, browser automation, approval, task state, release, or deploy:

- check `docs/baseline/APP_BASELINE.md` before implementation
- preserve the server as the owner of identity, authorization, approval,
  policy, task queue, task state, result intake, audit records, and deploy
  decisions
- treat desktop and local-agent code as subordinate execution layers
- do not add persistent local autostart, background recovery, or always-on
  monitoring unless the approved server-baseline task explicitly allows it
- report any local-only behavior that would bypass the server contract before
  editing runtime code

Local smoke, local stress, and local build results are preliminary evidence
only. A runtime change is not complete until the approved server deployment
target is at the intended HEAD and server smoke plus server stress checks pass
against the public server route or the server-side nginx route.

Before server pull, build, or service replacement, the worker must inspect
server `git status --short --branch`. If the server worktree is dirty, preserve
the server-local changes with an explicit stash or report-only decision before
pulling. Server-only secret override files such as `docker-compose.override.yml`
must be reported and left uncommitted unless a separate approved secret
configuration task says otherwise.

## 3.3 Auto-Run Rule

Automation is allowed only for safe, bounded work inside the approved scope.

The worker may automatically run:

- baseline and contract audits
- focused unit tests and targeted pytest
- `python -m py_compile` for targeted Python files
- `git diff --check` and staged diff checks
- residue/legacy cleanup audits
- standard report generation
- approved-scope file status checks

The worker must stop and report before continuing when:

- any verification command fails
- a command exceeds the expected task runtime
- an external app, workspace, server, browser, test runner, or background
  process appears relevant to the failure
- the next action would change live runtime, persistent state, deployment,
  installation, credentials, permissions, or another app

The worker may commit only when the user explicitly requests commit or the
approved task includes commit.
The worker may push only when the user explicitly requests push.

Auto-run must never perform server deploy/restart, Docker build/up/restart,
installer or portable build, live external browser automation, dependency
install, permission change, process termination, broad cleanup, persistent
local autostart, background recovery registration, or always-on monitoring
registration without separate explicit approval.

## 3.4 Tool Inventory And Report Rule

When a task creates, changes, removes, audits, or classifies a tool, runtime
entrypoint, connector, automation script, site module, or operational helper,
the worker must update or create:

- `docs/inventory/TOOL_INVENTORY.md` for the durable tool list
- `docs/inventory/CONNECTION_INVENTORY.md` for durable connection tracking
- `docs/reports/<task>_<yyyymmdd>.md` for the human-readable task report
- `data/inspection/<task>/...` when machine-readable audit output exists

The report must include:

- scope
- changed or inspected tool paths
- classification: active, locked, legacy, deprecated, unknown
- execution location: server, local-agent, desktop, user-direct, audit-only
- approval requirement
- input/output contract
- verification commands and results
- remaining unknowns or lock-needed items

Logs alone are not sufficient as final work evidence.

## 3.5 App Structure Rule

When app structure, app shell, UI routing, navigation, task screens, approval
screens, connection screens, or control-surface behavior changes, the worker
must update:

- `docs/architecture/APP_STRUCTURE.md`
- the relevant inventory document under `docs/inventory/`
- `docs/reports/<task>_<yyyymmdd>.md`

The app must remain a server-first control surface. App UI, desktop runtime,
and local-agent code must not become independent sources of truth for identity,
approval, policy, task state, audit history, release, or deploy decisions.

## 3.6 Task History And Audit Log Rule

User task requests, agent execution status, verification evidence, and task
results must leave a safe task history.
The server task state and server audit events are the final source of truth.
Every runtime task path must attempt structured audit logging by default. If a
local or desktop audit sink is unavailable, the runtime must record the audit
write failure and the original safe event to a fallback audit sink, or fail the
task before performing state-changing work.

Work reports and inspection artifacts must reference the relevant task or
verification evidence when available:

- server task or audit identifier
- masked agent or user reference
- execution location
- approval requirement and approval status
- state transition
- safe result summary or error code
- report path and verification command

Local-agent and desktop logs are diagnostic evidence only. They must not become
the final source of truth for task history, approval, policy, state, or audit.

Logs and reports must not contain raw secrets, tokens, cookies, sessions,
passwords, OTP values, approval tokens, raw auth headers, sensitive personal
data, full sensitive local file paths, full page HTML, or automatic raw
screenshot captures.

## 3.6.1 AI Agent Work Record Rule

Every AI agent task, in every operating mode, must leave a user-verifiable
work record in addition to structured audit logs.

The work record must be safe for the user to inspect and must include:

- user request summary
- agent role or execution mode
- approved scope and approval status
- ordered work steps performed
- files, tools, commands, or runtime targets touched
- decisions made and the reason for each material decision
- verification evidence and result
- generated reports, commits, pushes, or deployment references when applicable
- remaining risks, blocked work, and next approval needed

The work record must be linked from the final task report when a report is
required. For trivial tasks, the final assistant response may serve as the work
record if it contains the safe summary, verification, and residual risk.

For non-trivial operational work, the durable work record is:

```text
data/runtime/ai_work_record_latest.json
data/runtime/ai_work_record_history.jsonl
```

The standard helper is:

```text
python scripts/ops/ai_work_record.py start ...
python scripts/ops/ai_work_record.py append ...
python scripts/ops/ai_work_record.py complete ...
python scripts/ops/work_approval_watch.py --require-work-record ...
```

For lane-separated work that must be closed and resumed from a designated
path, use:

```text
python scripts/ops/ai_work_session.py --lane <lane> start ...
python scripts/ops/ai_work_session.py --lane <lane> checkpoint ...
python scripts/ops/ai_work_session.py --lane <lane> close ...
python scripts/ops/ai_work_session.py --lane <lane> resume-check --json
```

The default lane-separated record path is:

```text
data/runtime/ai_work_records/<lane>/latest.json
data/runtime/ai_work_records/<lane>/history.jsonl
data/runtime/ai_work_records/latest_lane.json
```

Google domain/module management uses the fixed `google` lane. Its latest state
and visible history can be reviewed with:

```text
python scripts/browser/cdp/cdp_client.py google records --limit=10
```

Before a new AI session continues operational work, it must inspect the latest
work record and use `resume_next_step` as the starting point unless a newer
user instruction changes the scope.

Parallel work in the same repository must use a named lane. Each lane records:

```text
lane
approved_scopes
forbidden_scopes
resume_next_step
```

Lane-specific commits may use:

```text
python scripts/ops/work_approval_watch.py --once --changed-source staged --lane <lane> ...
```

Full worktree checking remains mandatory before deploy, runtime replacement,
server pull, container build, service restart, or operational closeout.

The work record must not contain raw secrets, raw credentials, raw cookies,
raw tokens, approval tokens, raw auth headers, raw user files, raw page
content, full screenshots, full browser traces, or unrelated third-party
content.

## 3.7 User Data Contribution Consent Rule

Agent user task history may be used for product improvement or development
material only when the server has recorded explicit user data contribution consent.

Consent must be separate from normal service use, purpose-specific,
category-specific, revocable, and tied to retention and deletion rules.

Development material must be redacted, minimized, and purpose-bound. It may use
safe intent summaries, safe result summaries, task categories, tool/module
identifiers, state transitions, error codes, verification references, and user
feedback.

Development material must not contain raw user prompts, raw files, raw page
content, raw screenshots, raw emails, raw document bodies, raw browser traces,
secrets, credentials, tokens, cookies, sessions, passwords, OTP values,
approval tokens, raw auth headers, sensitive personal data, or unrelated
third-party content.

If consent is missing, expired, revoked, or outside the recorded purpose, the
record must not be used for product improvement, model training, benchmark
creation, quality analysis, or feature planning.

## 4. Forbidden By Default

These actions require explicit task-level approval:

- installer build
- portable package creation
- Docker build, pull, up, restart, or deploy
- server deploy or restart
- push
- dependency install
- browser or GUI launch
- live external site automation
- secret value output
- OUT_OF_SCOPE file modification, staging, or commit
- broad cleanup outside the approved scope
- stopping or modifying another app, workspace, server, browser, test runner, or
  background process discovered during target-app work
- making desktop or local-agent runtime the source of truth for identity,
  approval, policy, task state, audit, release, or deploy decisions
- adding persistent local autostart, background recovery, or always-on
  monitoring outside an explicitly approved server-baseline task
- automated commit unless the approved task includes commit or the user
  explicitly requests commit
- automated push unless the user explicitly requests push
- storing raw secrets, tokens, cookies, sessions, passwords, OTP values,
  approval tokens, raw auth headers, sensitive personal data, full sensitive
  local file paths, full page HTML, or automatic raw screenshot captures in task
  history, audit logs, reports, or local diagnostic logs
- using task history, audit logs, reports, prompts, files, screenshots, emails,
  document bodies, browser traces, or local diagnostics as development material
  without explicit server-recorded user data contribution consent

## 5. Standard Verification Levels

Use the narrowest verification that proves the change, then run the required
gate when the change affects shared contracts.

```text
syntax: python -m py_compile targeted files
unit: python -m pytest targeted tests -q
contract: module-specific audit script
module gate: python tools/quality/module_quality_gate.py --module <module>
required gate: python tools/quality/required_quality_gate.py
live smoke: only when explicitly approved
```

Build, deploy, Docker, installer, and live browser checks are separate stages.
They must not be hidden inside dry-run gates.

## 6. Standard Commit Rule

Commit only when the approved task includes commit or the user explicitly
requests it.

Before commit:

- `git status --short` must be reviewed.
- Staged files must match the approved scope.
- OUT_OF_SCOPE files must not be staged.
- Relevant verification must pass.
- The commit message must describe one purpose.

## 7. Standard Function Explanation Rule

For user learning, implementation reports should explain changed functions in
plain language:

```text
function name
why it exists
input
output
failure behavior
security or state boundary
how to think when writing it manually
```

The explanation should be practical and tied to the actual code, not generic
textbook material.

## 8. Failure And Recovery Rule

When a verification step fails:

- Stop broad implementation work.
- Report the failing command and safe summary.
- Do not hide the failure with mock success.
- Fix only inside the approved scope.
- Re-run the smallest failing check first.
- Run the relevant module or required gate after the fix.

When runtime work fails:

- Separate server, local-agent, browser, site, auth, approval, and environment
  causes in the report.
- Preserve logs and state needed for diagnosis.
- Do not print raw secrets.
- Retry only when a retry rule exists.

## 9. Required Report Template

Every completed task should use the standard report template:

```text
docs/templates/STANDARD_REPORT_TEMPLATE.md
```

Any task that changes runtime behavior must include the four baseline answers:

```text
input/output contract
authorization boundary
state changes
regression gate
```

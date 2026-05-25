# HAEHAN Standard Workflow

Status: LOCKED
Baseline ID: HAEHAN-STANDARD-WORKFLOW-01
Approved by: user approval in current Codex session
Baseline HEAD: 796ebc2e22b0c7f536fa606ddec83c582aee6448
Last updated: 2026-05-24

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
-> working standard confirmation
-> user approval when the scope changes governance, deploy, build, push, or live runtime
-> implementation inside the approved scope
-> focused verification
-> gate verification
-> standard report
-> commit only when requested or when the approved task includes commit
```

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

## 5. Standard Verification Levels

Use the narrowest verification that proves the change, then run the required
gate when the change affects shared contracts.

```text
syntax: python -m py_compile targeted files
unit: python -m pytest targeted tests -q
contract: module-specific audit script
module gate: python scripts/module_quality_gate.py --module <module>
required gate: python scripts/required_quality_gate.py
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

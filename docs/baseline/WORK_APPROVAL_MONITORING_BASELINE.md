# Work Approval Monitoring Baseline

Status: LOCKED
Baseline ID: HAEHAN-WORK-APPROVAL-MONITORING-01
Approved by: user approval in current Codex session
Last updated: 2026-05-26

## 1. Purpose

All operational work must start from an approved baseline and remain inside the
approved work scope until completion.

The monitoring script is the execution guard for this rule. It does not approve
work by itself. It verifies that:

- an approved baseline document exists;
- changed files stay inside the approved scope;
- a resumable AI work record exists when the gate requires it;
- runtime reports are present and healthy where required;
- no secret values are emitted in monitoring reports.

## 2. Required Flow

```text
write baseline
-> user approval
-> start safe AI work record
-> run work monitor
-> implement only approved scope
-> append work record after material steps
-> run quality/deploy/runtime gates
-> complete or block work record with next resume step
-> record report
```

## 3. Approval Document Rules

An approved baseline must contain:

- `Status: LOCKED`
- `Approved by:`
- a `Baseline ID:`

Draft or missing baseline documents must block monitored work.

## 4. Scope Rules

The work monitor receives explicit approved path prefixes.
Parallel work must identify its lane and use staged-only checking before a
lane-specific commit when another approved lane has dirty work in the same
repository.

Allowed examples:

- `admin-web/`
- `ai_orchestrator/`
- `browser_worker/`
- `scripts/ops/`
- `tests/`
- `docs/baseline/`
- `docs/ops/`
- `docker-compose.yml`
- `Dockerfile`
- `.dockerignore`

Changed files outside the approved prefixes must fail the monitor.

Two changed-source modes are allowed:

- `worktree`: checks every dirty path and is required before deploy, runtime
  replacement, or operational closeout.
- `staged`: checks only staged files and is allowed only for lane-specific
  commits during approved parallel work.

Each parallel lane must have explicit scopes. A lane must not stage, commit,
or modify another lane's files.

## 5. Runtime Guard Rules

When runtime checking is enabled, the monitor must verify the latest reports:

- deployment integrity gate
- runtime event watch
- orchestrator boundary stress

If a report is missing or has `ok: false`, monitored work fails.

## 5.1 AI Work Record Guard Rules

When work-record checking is enabled, the monitor must verify:

- `data/runtime/ai_work_record_latest.json` exists;
- the record lane matches the requested monitor lane when both are present;
- the record contains `task_id`, `request_summary`, `approval_status`,
  `status`, `approved_scopes`, and `resume_next_step`;
- `secret_values_output` is `false`;
- the latest record is sufficient for the next AI session to resume or close
  the work without relying on chat history alone.

The durable history is appended to:

```text
data/runtime/ai_work_record_history.jsonl
```

Domain-specific operational lanes must use lane-separated work records when
parallel work is active. Google management work is locked to the `google` lane:

```text
data/runtime/ai_work_records/google/latest.json
data/runtime/ai_work_records/google/history.jsonl
python scripts/browser/cdp/cdp_client.py google records --limit=10
```

Google module checks and Google domain boundary audits must append a checkpoint
to that lane after each material run. A new AI session must inspect the Google
lane latest record before changing Google modules, gates, login policy, final
approval policy, or secret-handling policy.

## 6. Forbidden Behavior

The monitor must not:

- deploy;
- restart containers;
- mutate unrelated app containers;
- print raw secrets, tokens, passwords, cookies, sessions, or OTP values;
- silently ignore out-of-scope modified files.
- start new non-trivial work while the required work record is missing or not
  resumable.
- use staged-only checking for deploy, server pull, container build, runtime
  restart, or final operational closeout.

## 7. Report Location

The latest report is written to:

```text
data/runtime/work_approval_watch_latest.json
```

History is appended to:

```text
data/runtime/work_approval_watch_history.jsonl
```

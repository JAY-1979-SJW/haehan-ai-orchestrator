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
- runtime reports are present and healthy where required;
- no secret values are emitted in monitoring reports.

## 2. Required Flow

```text
write baseline
-> user approval
-> run work monitor
-> implement only approved scope
-> run quality/deploy/runtime gates
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

## 5. Runtime Guard Rules

When runtime checking is enabled, the monitor must verify the latest reports:

- deployment integrity gate
- runtime event watch
- orchestrator boundary stress

If a report is missing or has `ok: false`, monitored work fails.

## 6. Forbidden Behavior

The monitor must not:

- deploy;
- restart containers;
- mutate unrelated app containers;
- print raw secrets, tokens, passwords, cookies, sessions, or OTP values;
- silently ignore out-of-scope modified files.

## 7. Report Location

The latest report is written to:

```text
data/runtime/work_approval_watch_latest.json
```

History is appended to:

```text
data/runtime/work_approval_watch_history.jsonl
```

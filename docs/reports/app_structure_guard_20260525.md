# App Structure Guard - 2026-05-25

## Scope

Added a read-only app structure contract audit and recovery boundary checks.

## Decision

The app remains a server-first control surface. Recovery behavior is
diagnostic-first and server-baseline controlled.

## Recovery Boundary

No live recovery script was added.

The guard documents and audits that the following require separate explicit
approval:

- automatic server deploy/restart
- Docker build, pull, up, restart, or deploy
- local-agent token deletion or credential reset
- persistent local autostart registration
- background recovery registration
- always-on monitoring registration
- process termination outside the approved target app
- editing another workspace, app, server, browser, or test runner

## Task History And Audit Log Boundary

Task history and audit logs must be recorded through server-owned task state
and server audit events as the final source of truth.

Local-agent and desktop logs are diagnostic evidence only. They must not become
the final source of truth for task history, approval, policy, state, or audit.

Raw secrets, tokens, cookies, sessions, passwords, OTP values, approval tokens,
raw auth headers, sensitive personal data, full sensitive local file paths, full
page HTML, and automatic raw screenshot captures are forbidden in logs, reports,
task history, and audit events.

## User Data Contribution Consent Boundary

Product improvement and development material may use agent user task history
only after explicit server-recorded user data contribution consent.

Consent must be separate from normal service use, purpose-specific,
category-specific, revocable, and tied to retention and deletion rules.

Development material is limited to redacted and minimized safe summaries,
categories, tool/module identifiers, state transitions, error codes,
verification references, and user feedback.

Raw prompts, files, page content, screenshots, emails, document bodies, browser
traces, secrets, credentials, tokens, cookies, sessions, passwords, OTP values,
approval tokens, raw auth headers, sensitive personal data, and unrelated
third-party content remain forbidden as development material.

## Added Verification

```text
python scripts/ops/audit_app_structure_contract.py
python -m pytest tests/test_app_structure_contract.py -q
```

## Verification

```text
python scripts/ops/audit_app_structure_contract.py
python scripts/ops/audit_standard_workflow_contract.py
python -m pytest tests/test_app_structure_contract.py tests/test_standard_workflow_contract.py -q
python -m py_compile scripts/ops/audit_app_structure_contract.py scripts/ops/audit_standard_workflow_contract.py
git diff --check
```

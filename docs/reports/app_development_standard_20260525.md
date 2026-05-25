# App Development Standard - 2026-05-25

## Scope

Created the first locked app development standard before app UI implementation.

## Decision

The app will be developed as a server-first operational control surface, not as
an independent execution runtime or marketing landing page.

## Locked First App Areas

```text
Dashboard
Tasks
Approvals
Agents
Tools
Connections
Audit
Consent
Reports
Settings
```

## User Convenience Standard

The standard now requires the app to be comfortable for a non-developer
operator. A user must be able to understand server status, agent connection,
approval waiting items, current work, failures, next safe action, action
recording, and consent revocation without reading raw logs or code.

The standard defines target users:

- Owner
- Operator
- Reviewer
- Support
- Non-developer user

## UX Requirements

- First screen is the operator dashboard.
- First-time flow checks server, account/role, local agent, safe sample status,
  approval explanation, and data contribution consent choice.
- Tasks support filtering, sorting, copyable task IDs, and report links.
- Task Detail separates server, local-agent, browser, site, auth, approval, and
  environment failures.
- Approvals must be hard to misuse and must not accidentally approve by default.
- Agent states use user-readable labels.
- Audit and Reports are searchable and filterable.
- Consent is explicit, reversible, and does not pressure the user.
- Disabled buttons explain why they are disabled.
- Error messages are user-actionable and never show raw stack traces.
- Accessibility, responsive layout, and user acceptance criteria are required.

## Boundaries

- The server remains the final source of truth for identity, authorization,
  approval, policy, task state, consent, audit, release, and deploy decisions.
- App UI may request server APIs and display safe server-owned state.
- App UI must not execute browser/tool work directly.
- App UI must not store raw prompts, files, emails, document bodies, page HTML,
  screenshots, browser traces, credentials, tokens, cookies, sessions,
  passwords, OTP values, approval tokens, raw auth headers, or sensitive
  personal data.

## Verification

```text
python scripts/ops/audit_app_development_standard.py
python -m pytest tests/test_app_development_standard.py -q
```

Latest result:

```text
RESULT=PASS_APP_DEVELOPMENT_STANDARD
12 passed
```

## Next Work

Build the app shell and route skeleton according to
`docs/baseline/APP_DEVELOPMENT_STANDARD.md`.

## App Shell Start

Implemented the first standard UI dashboard shell at:

```text
admin-web/src/app/page.tsx
```

The first screen uses the standard UI package components:

```text
AppShell
Sidebar
Header
StatusBadge
MetricCard
DataTable
ReportList
Alert
Button
```

The screen is intentionally static/dry-run until server API wiring is added.
Approval and consent actions are disabled and explain that server API wiring is
required before activation.

## App Shell Verification

```text
python -m pytest tests/test_app_standard_ui_dashboard.py tests/test_app_development_standard.py -q
npm run typecheck
npm run build
python scripts/ops/audit_standard_ui_package.py
```

Results:

```text
18 passed
typecheck passed
build passed
Standard UI Package Audit: PASS
```

Local development server:

```text
http://localhost:3000
```

Known warning:

```text
Next.js reports a lockfile SWC dependency patch warning, but build and dev
server both completed successfully.
```

# HAEHAN App Development Standard

Status: LOCKED
Baseline ID: HAEHAN-APP-DEVELOPMENT-STANDARD-01
Owner baseline: `docs/baseline/APP_BASELINE.md`
Structure reference: `docs/architecture/APP_STRUCTURE.md`
Last updated: 2026-05-25

## 1. Purpose

This document defines the working standard for developing the HAEHAN app.

The app is a server-first control surface. It displays and controls
server-owned state, but it must not become an independent execution engine,
approval source, task state source, audit source, policy engine, deployment
tool, or local recovery daemon.

## 2. Product Role

The first commercial app must help an operator understand and control:

```text
server health
agent connection state
task queue
task detail
approval requests
audit and task history
tool and connection inventory
user data contribution consent
reports and verification evidence
```

The app must make the current system status clear without exposing raw secrets,
raw user content, raw browser data, or unrelated app state.

## 2.1 User Convenience Standard

The app must be comfortable for a non-developer operator.

The user should be able to answer these questions within one screen or one
click:

```text
Is the server working?
Is my agent connected?
What is waiting for my approval?
What is running now?
What failed and why?
What can I safely do next?
Was my action recorded?
Can I revoke data contribution consent?
```

The app must not require the user to understand internal code paths, Python
scripts, JSON payloads, raw logs, Git, ports, process IDs, or browser debugging
terms to complete normal work.

Primary actions must use plain business language. Technical identifiers may be
shown as secondary copy for auditability, but they must not be the only label
the user sees.

## 2.2 Target Users

The first app must support these user types:

| User type | Main need | UI requirement |
|---|---|---|
| Owner | Overall system status and final decisions | dashboard, approvals, reports, settings |
| Operator | Daily task control | tasks, approvals, agents, warnings |
| Reviewer | Check evidence before approval | task detail, safe summary, approval risk, reports |
| Support | Diagnose connection or failure | agents, connections, audit, safe error codes |
| Non-developer user | Understand what happened | plain Korean labels, clear next action, no raw logs |

If a screen is useful only to developers, it must be placed behind an advanced
or diagnostic area and must not be the default path for normal users.

## 3. Required Navigation

The first app shell must provide these primary areas:

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

Every route must be server-backed or explicitly marked as static/dry-run. UI
state must never be treated as final task, approval, audit, or consent state.

Navigation must be consistent:

- the left navigation keeps the same order on every screen
- the active screen is visually obvious
- the top area shows server and agent status
- global search or filtering is available once task volume grows
- destructive or high-risk actions are never hidden in menus without labels

## 4. First Screen Standard

The first screen is the operator dashboard, not a marketing landing page.

The dashboard must show:

- server status
- local-agent connection summary
- active task count
- approval waiting count
- recent safe task summaries
- recent safe audit events
- connection warning count
- user data contribution consent status
- last verification or report reference

The dashboard must prioritize what the user should do next:

- show approval waiting items before informational logs
- show failed or blocked tasks before completed tasks
- show disconnected agents before healthy agents
- show stale verification before old success messages
- show a clear next action for every warning

The dashboard must not show raw prompts, raw files, raw emails, raw document
bodies, raw page HTML, raw screenshots, raw browser traces, credentials,
tokens, cookies, sessions, passwords, OTP values, approval tokens, raw auth
headers, or sensitive personal data.

## 4.1 First-Time User Flow

On first use, the app must guide the user through:

```text
server status check
-> account and role confirmation
-> local-agent connection check
-> safe sample task or read-only status check
-> approval explanation
-> data contribution consent choice
```

The first-time flow must be skippable by an owner or admin, but skipped setup
items must remain visible as warnings until completed or intentionally ignored.

## 5. Screen Contracts

### 5.1 Tasks

The Tasks screen shows server-owned task records.

Required fields:

```text
task_id
requested action
tool_id or module
state
approval requirement
approval status
execution location
safe summary
error code
created_at
updated_at
report path or verification reference
```

Allowed actions:

- create task through a server API
- open task detail
- request cancel through a server API
- refresh server state
- filter by state, risk, tool, agent, and date
- sort by newest, risk, approval waiting, and failed state
- copy task_id with one click
- open report or verification reference when present

Forbidden actions:

- execute browser/tool work directly from UI state
- mutate local-agent state directly
- infer completion from local UI state

### 5.2 Task Detail

The Task Detail screen shows one server-owned task, its state transitions,
approval relationship, safe result summary, error details, and evidence
references.

It must not display raw result payloads or local diagnostic logs unless they
are already redacted and server-approved for display.

Task Detail must provide:

- a timeline of state transitions
- a clear current state badge
- approval relationship if approval exists
- safe result summary
- safe error explanation
- recommended next action
- verification/report links
- copyable task_id and report path

For failures, the screen must separate:

```text
server failure
local-agent failure
browser failure
site failure
auth failure
approval failure
environment failure
```

### 5.3 Approvals

The Approvals screen shows approval requests and allows approve/reject only
through server APIs.

Approval UI must show:

```text
approval_id
task_id
requested action
risk level
state change summary
approval status
requested_by
expires_at
safe summary
```

Approval UI must not display or store raw approval tokens.

Approval UI must be hard to misuse:

- approve and reject actions must be visually distinct
- high-risk approvals must show the state change in plain language
- the default focus must not accidentally approve
- approval dialogs must show the exact safe action summary
- expired approvals must be disabled
- already-used approvals must be read-only
- rejected approvals must preserve safe reason text
- the user must be able to return to the related task detail

### 5.4 Agents

The Agents screen shows server-approved agent registration, heartbeat, current
task, and readiness state.

It must not reset credentials, delete tokens, register autostart, start
background recovery, or terminate processes without a separately approved
runtime task.

Agent status must use user-readable states:

```text
Connected
Disconnected
Connecting
Busy
Waiting
Needs attention
Blocked
Unknown
```

Each unhealthy state must show a safe explanation and next action. The app must
not ask the user to inspect process IDs or raw WebSocket messages for normal
diagnosis.

### 5.5 Tools And Connections

The Tools and Connections screens display durable inventories from:

```text
docs/inventory/TOOL_INVENTORY.md
docs/inventory/CONNECTION_INVENTORY.md
```

They may show classification, status, approval requirement, risk, and
verification references. They must not execute tool scripts directly.

Inventory screens must make lock status easy to understand:

- Active: available for normal use
- Locked: contract is verified and protected
- Legacy: preserved for reference only
- Deprecated: not a normal runtime path
- Unknown: must be reviewed before use

Unknown tools or connections must be visually separated from active ones.

### 5.6 Audit And Reports

The Audit screen shows server-owned audit events and task history.

The Reports screen shows human-readable report references and verification
results. Logs alone are not sufficient as final evidence.

Audit and Reports must be searchable and filterable by:

```text
task_id
date
actor or masked user reference
tool_id or module
state
error code
approval status
report path
```

Audit rows must show safe summaries first and technical identifiers second.

### 5.7 Consent

The Consent screen manages user data contribution consent through server APIs.

It must show:

```text
current consent status
allowed purposes
allowed data categories
retention period
created_at
expires_at
revoked_at
```

It must allow:

- grant consent through a server API
- revoke consent through a server API
- inspect consent metadata

It must not export development material directly. Development material export
is an admin/server operation and remains consent-gated.

Consent UX must be explicit and reversible:

- show what is collected
- show what is never collected
- show why the data is used
- show retention period
- provide a simple revoke action
- confirm revocation result
- keep service usage separate from contribution consent

The consent screen must not pressure the user. Refusing consent must not block
normal app use unless a specific optional feature truly requires it.

## 6. API Integration Standard

Every app feature must define:

```text
server endpoint
request schema
response schema
auth role
approval requirement
state changes
redaction boundary
error behavior
verification command
```

If a server endpoint does not exist, app work must stop at static UI or mock
contract documentation. Mock UI must be labeled as static/dry-run in code,
tests, or reports and must not hide missing backend behavior.

API failures must be translated into user-actionable messages:

| Failure | User message requirement |
|---|---|
| 401/403 | Explain sign-in or permission issue without exposing auth headers |
| 404 | Explain that the record was not found or may be stale |
| 409 | Explain conflicting state, such as already approved or already used |
| 410 | Explain expiration and offer a safe retry/request path |
| 422 | Explain invalid input in field-level language |
| 429 | Explain rate limit and retry timing if provided |
| 5xx | Explain server failure and preserve report/audit reference |
| network error | Explain connection problem and offer refresh/retry |

The app must never show raw stack traces to normal users.

## 7. Design Standard

The app should feel like an operational control surface:

- dense but readable information
- restrained styling
- predictable navigation
- clear state badges
- fast scanning of tasks, approvals, agents, and warnings
- no decorative landing page
- no marketing hero as the first screen
- no nested cards for primary operational layouts

The UI must use stable responsive dimensions so tables, badges, counters,
buttons, and panels do not resize unpredictably.

## 7.1 Usability Standard

The app must optimize for repeated daily work:

- important counts are visible without scrolling
- common filters are one click away
- the user can return from detail screens without losing filters
- long lists have search, filter, sort, and pagination or virtual scrolling
- bulk selection is allowed only for safe read-only operations unless approval
  rules explicitly support bulk state changes
- buttons use clear verbs such as Approve, Reject, Cancel, Refresh, Open Report
- disabled buttons explain why they are disabled
- dangerous actions require a confirmation dialog with the safe action summary
- successful actions confirm what changed and where to see the record
- loading states must not look like failures
- empty states must explain what will appear there

## 7.2 Accessibility And Readability

The app must be readable and controllable:

- keyboard navigation for primary workflows
- visible focus state
- sufficient color contrast
- status is not communicated by color alone
- table headers remain understandable when horizontally scrolled
- timestamps use a consistent format
- long identifiers are copyable and truncated visually
- Korean labels should be plain and business-oriented
- technical English may be secondary when needed for audit terms

## 7.3 Responsive Standard

Desktop is the primary layout, but tablet and narrow browser widths must remain
usable.

Responsive requirements:

- navigation collapses without hiding current state
- tables convert to compact rows or keep safe horizontal scroll
- action buttons remain reachable
- text must not overlap badges, buttons, or panels
- no viewport-width font scaling
- critical dashboard counts remain visible near the top

Mobile execution of high-risk approval is allowed only if the confirmation and
safe summary remain fully readable.

## 8. Security And Privacy Standard

The app must never render or store:

```text
raw prompts
raw files
raw emails
raw document bodies
raw page HTML
raw screenshots
raw browser traces
credentials
tokens
cookies
sessions
passwords
OTP values
approval tokens
raw auth headers
sensitive personal data
unrelated third-party content
```

All user-visible content must come from safe server fields or approved static
metadata.

## 8.1 User Trust Standard

The app must explain sensitive decisions in plain language:

- why approval is required
- why an action is blocked
- why consent is optional
- why a connection is unhealthy
- why a task cannot be cancelled
- what changed after approval, rejection, cancellation, or consent revocation

The app must not imply that a task succeeded until server state confirms it.

## 9. Development Order

App development must proceed in this order:

```text
app development standard
-> app shell and route skeleton
-> read-only server status dashboard
-> task list and task detail
-> approval list and approval action wiring
-> agent connection status
-> tool and connection inventory views
-> audit and report views
-> user data contribution consent view
-> focused verification
-> report and inventory update
```

Do not build live browser automation, server deploy/restart, installer,
background recovery, always-on monitoring, or process termination into the app
without separate explicit approval.

## 9.1 Connection And Command Lock

The current app connection and command system is locked to documented,
server-first contracts only.

Allowed app connection sources:

```text
server read-only status APIs
server task state APIs
server approval APIs
server audit/report APIs
server consent APIs
local-agent connection status reported by the server
static or dry-run contracts documented in this baseline
```

Allowed command classes:

```text
read
list
status
preview
dry_run
approval_request
approve
reject
cancel
consent_grant
consent_revoke
report_export
```

Forbidden command classes:

```text
server_restart
server_deploy
docker_up
docker_restart
process_kill
local_autostart
browser_final_submit
credential_extract
cookie_export
session_export
raw_file_export
cross_app_control
unknown_tool_execute
```

The app may show a disabled or blocked state for forbidden commands, but it
must not wire them to an executable handler.

## 9.2 Developed Tool Attachment Lock

Only developed and inventoried tools may be attached to the app.

A tool is attachable only when all of these are true:

- it exists in `docs/inventory/TOOL_INVENTORY.md`
- its status is `active` or `locked`
- its connection exists in `docs/inventory/CONNECTION_INVENTORY.md`
- its command class is listed in the allowed command classes above
- its auth, approval, input, output, redaction, and failure behavior are
  documented
- its verification command passes

Tools in `legacy`, `deprecated`, `unknown`, `TBD`, or `Lock Needed Queue` may
be displayed as inventory evidence only. They must not be attached to buttons,
routes, background jobs, scheduled jobs, server actions, or local-agent
dispatch until they are promoted by a baseline update and audit.

## 10. Verification Standard

Minimum verification for app work:

```text
python tools/audits/app/audit_app_development_standard.py
python tools/audits/app/audit_app_structure_contract.py
python tools/audits/app/audit_standard_workflow_contract.py
python -m pytest tests/test_app_development_standard.py -q
```

When implementation touches frontend code, add route/component tests or a
browser smoke check appropriate to the app stack.

When implementation touches server APIs, add server API tests for auth,
redaction, state changes, and error behavior.

## 11. Completion Rule

An app screen is not complete until:

- its server endpoint or static/dry-run contract is documented
- forbidden raw fields are excluded
- auth and approval boundaries are clear
- empty, loading, error, and blocked states are handled
- first-time, empty, loading, success, warning, blocked, and failed states are
  understandable to a non-developer user
- common filters, sorting, and return navigation are implemented where lists
  are present
- destructive or high-risk actions require clear confirmation
- focused tests or audits pass
- a report records changed files, verification, and remaining risks

## 12. User Acceptance Checklist

Before a screen is treated as ready, a non-developer user should be able to:

```text
understand the screen purpose within 5 seconds
identify the most urgent item
know which action is safe to click
understand why an action is disabled
recover from an error without reading raw logs
find the related task/report/audit evidence
leave the screen and come back without losing context
```

If any item fails, the screen is incomplete even when the code works.

Status: LOCKED
Baseline ID: AI-AGENT-UI-STRUCTURE-BLUEPRINT-01

# AI Agent UI Structure Blueprint

This blueprint defines the detailed UI structure for the unified AI agent app.
It expands the app structure baseline into concrete screen regions, tool
templates, and result-first interaction rules.

## Primary Layout

The app uses a persistent operations shell:

```text
left navigation
  -> tool groups and active route
top header
  -> current workspace, gate state, runtime state
main work area
  -> selected tool, presets, tables, forms
right-side result area or inline result panel
  -> latest result, report path, approval request, next action
bottom/secondary activity area when needed
  -> work records, logs, verification, history
```

The UI must keep the current work context visible. A user should not need to
search logs or terminal output to know what happened.

## Home Dashboard

The home dashboard is the operator start screen. It must show:

- quick actions and immediate results;
- chat and result workspace;
- runtime integration flow;
- current app tool surfaces;
- MCP Gateway readiness;
- latest report and baseline artifacts;
- next development focus.

Home is not a marketing page. It is the first operational dashboard.

## Tool Surface Template

Every major tool screen should follow this order:

```text
tool header
  -> title, status badge, source policy, last updated
quick presets
  -> button-first actions with safe defaults
filters or small bounded inputs
  -> only fields that materially change the result
primary result panel
  -> latest report, table, summary, artifact path
approval panel
  -> only when final or risky action is pending
work record panel
  -> lane, latest record, resume_next_step
advanced details
  -> logs, raw-safe metadata, verification output
```

Blank natural-language prompts are not the default. Chat is available for
exceptions and must resolve into a tool action, result artifact, or approval
request.

## Result Panel

The result panel is persistent for execution-capable tools. It must display:

- current status;
- latest safe summary;
- report or artifact path;
- source and quota/limit;
- approval state;
- next recommended action;
- verification result when available.

The result panel must never show raw secrets, cookies, tokens, passwords, OTP
values, full sensitive local paths, raw page HTML, or unrelated third-party
content.

## Approval Panel

Approval UI must be precise and conservative:

- show the exact action that will happen after approval;
- show target service, account context when safe, risk, and expiry;
- show source inputs and generated result summary;
- expose approve/reject buttons only when the request is valid;
- never combine multiple unrelated final actions under one approval button.

## Work Record Panel

Every non-trivial tool screen must be able to show the current work lane:

```text
data/runtime/ai_work_records/<lane>/latest.json
```

The panel should show `task_id`, `status`, touched files/tools, verification,
remaining risk, and `resume_next_step`. This lets a new AI session resume
without reconstructing context from chat.

## MCP And External Tool Catalog

MCP tools and owned app adapters appear as catalog entries before execution.
Each catalog row must show:

- server or adapter name;
- enabled/disabled state;
- allowed tools;
- blocked tools;
- risk level;
- approval requirement;
- result target.

Real MCP calls must stay disabled until the MCP Gateway audit passes and the
entry is explicitly enabled.

## Navigation Model

Navigation is grouped by work mode:

- Operate: dashboard, market research, local agents, approvals;
- Tools: CAD, file map, task list, external tasks, future domain tools;
- Govern: ops, logs, deployment, baselines, MCP gateway readiness;
- Settings: accounts, sessions, OAuth/API keys, quotas, policies.

The current route must be visible. New tool routes are added only after the
data source, result policy, and approval policy exist.

## Responsive Behavior

Desktop:

- left nav remains persistent;
- result panel can sit beside the main work area;
- tables use stable columns and horizontal scroll only when needed.

Mobile:

- navigation collapses before content does;
- result panel moves below the command area;
- approval buttons remain visible near approval details;
- long paths wrap without breaking layout.

## Required States

Every execution-capable screen must represent these states:

- ready;
- running;
- completed;
- needs approval;
- blocked;
- failed;
- stale result;
- no data yet.

Disabled controls must explain why they are disabled with a title or adjacent
status. A disabled final action without reason is not acceptable.

## Development Order

The UI should be built in this order:

1. Home dashboard shell and result workspace.
2. Tool catalog and MCP readiness.
3. Market Research result-first screen.
4. SmartStore-specific presets and result panels.
5. Approval console refinement.
6. Work record/resume panel.
7. Runtime health and drift dashboard.
8. Google/Naver/YouTube/CAD detail surfaces.

Each step must keep the low-input, result-first, approval-gated contract.

Status: LOCKED
Baseline ID: AI-AGENT-APP-STRUCTURE-DESIGN-BASELINE-01

# AI Agent App Structure And Design Baseline

This baseline defines the target structure and UI design rules for the unified
AI agent app. The app is the primary operating surface for all internal tools.
Individual external domains or standalone products must not be created by
default; tools are added as modules inside this app unless productization is
explicitly approved.

## Product Shape

The target product is a single AI agent app with modular tool surfaces:

```text
AI Agent App
  Home
  Market Research
    YouTube Research
    SmartStore / Naver Shopping Research
    Keyword / Trend Analysis
  Google Tools
    Gmail / Drive / Calendar / Docs / Sheets
    YouTube / YouTube Studio
    Ads / Search Console / Analytics / Merchant / AdSense
    Cloud / OAuth / API Key / AI Studio / Gemini / Vision
  Naver Tools
    Naver Mail / Cafe / Blog / Calendar / MYBOX / Talk / Place
    Naver Keyword / Shopping / Company SEO
    SmartStore handoff
  SmartStore Tools
    Dashboard / Product / Orders / Inventory / Analytics
    Product Register / Save Approval
    SEO / Review Reply / Competitor / CSV Import
  Work Automation
    Browser Agent
    Approval Queue
    Task Queue
    Task History
    Work Records
  External MCP / Tool Gateway
    MCP Server Registry
    Owned App Adapters
    Tool Catalog
    MCP Gateway readiness   (retired 2026-10-05: not shown on home, see External MCP Gateway Rule)
  Ops
    Container / Deploy / Drift Check
    Runtime Event Watch
    Logs / Monitoring
    Gate Status
  CAD
  File Map
  Settings
    Accounts / Sessions
    OAuth / API Keys
    Policies / Quotas
```

## AI Integration Contract

The app is not a standalone screen collection. It is the operating surface for
one AI-connected runtime:

```text
User instruction
  -> AI orchestration
  -> app UI command/status surface
  -> bounded server API or backend task
  -> local agent when browser/file/desktop/session access is required
  -> approval gate before final state-changing action
  -> work record and report artifact
```

Required runtime layers:

| Layer | Responsibility | Required Boundary |
| --- | --- | --- |
| App UI | command entry, status, approval, report review | registered route and documented gate |
| Server/API | route requests, enforce policy, create tasks | allowlisted endpoint and bounded inputs |
| Local Agent | browser, file, desktop, and user-session execution | loopback/user-present/runtime isolation |
| AI Orchestration | plan, prepare, verify, summarize, resume work | no hidden final action; write work records |
| Approval Gate | stop risky or state-changing work | user final approval or user-direct handoff |

The home dashboard must show this contract as a first-viewport operating
summary. If the home page no longer exposes the server/local/app/AI flow, the
structure baseline audit must fail.

## Low-Input Immediate-Result UX Contract

The app must minimize user typing. Natural language remains available, but the
primary workflow is preset/button first:

```text
Open app
  -> choose a tool or recommended action
  -> click a bounded preset
  -> see the latest result, report, or approval request immediately
  -> edit only the small fields that are truly variable
  -> approve only final state-changing work
```

Required interaction rules:

- Every major tool surface must expose at least one default view with existing
  results, recent reports, pending approvals, or runtime state before asking
  for input.
- Repeated work must be represented as preset buttons or segmented choices,
  not blank natural-language prompts.
- Natural-language input is an override path for unusual tasks, not the default
  happy path.
- Forms must have safe defaults, small bounded fields, and visible source,
  limit, and gate policy.
- A command button must lead to one of three immediate outcomes: result shown,
  report artifact opened, or approval request created.
- The home dashboard must include quick actions and a latest-results area so a
  user can start from buttons and inspect output without navigating through
  implementation details.
- The app must provide a compact chat/input panel for exceptional instructions
  and a persistent result panel for the latest output, report path, approval
  state, and next action.
- Chat must not be the only way to operate a tool. It supplements buttons and
  presets, and its output must resolve into a visible result artifact or
  approval request.

## Current Implemented App Surfaces

The current `admin-web` implementation already exposes these app surfaces:

| Surface | Route | Purpose | Current Status |
| --- | --- | --- | --- |
| Home | `/` | App entry dashboard | implemented |
| Assistant | `/assistant` | AI assistant dashboard and task views | implemented |
| Local Agents | `/local-agents` | local agent registration/status | implemented |
| Market Research | `/market-research` | YouTube market research reports and bounded run action | implemented |
| Browser Approvals | `/browser-approvals` | browser approval review | implemented |
| File Map | `/file-map` | file-map report and cleanup workflow | implemented |
| CAD | `/cad` | AI CAD surface | implemented |
| External Tasks | `/external-tasks` | external provider work listing | implemented |
| Ops Center | `/ops` | operations, approvals, agents, integrations, audit | implemented |

The current navigation source is `admin-web/src/lib/nav.ts`. New major tool
surfaces must be added there only after the route, data source, and gate policy
are present.

## Current Developed Tool Inventory

Tool modules currently discovered in the repo:

| Tool Area | Main Entrypoints | UI Target | Boundary |
| --- | --- | --- | --- |
| Market Research / YouTube Research | `scripts/browser/cdp/cdp_client.py google youtube research-run`, `scripts/google/youtube/search.py` | `/market-research` | read/prepare; bounded UI execution; no hidden transcript scraping |
| YouTube Owner/Research Tools | `scripts/browser/cdp/cdp_client.py youtube research ...`, `scripts/youtube/research.py` | Market Research / YouTube Tools | public metadata/comments via official API; uploads/recording approval-gated |
| Google Tools | `scripts/browser/cdp/cdp_client.py google ...`, `scripts/google/*` | Google Tools | Google Home entry, work-mode gate, writes/keys/billing approval-gated |
| Naver Tools | `scripts/browser/cdp/cdp_client.py naver ...`, `scripts/naver/*`, `scripts/naver_mail/*` | Naver Tools | user-present login; send/publish/upload/save approval-gated |
| SmartStore Tools | `scripts/browser/cdp/cdp_client.py smartstore ...`, `scripts/smartstore/*`, `scripts/naver/smartstore/*` | SmartStore Tools | product save approval-gated; live gaps remain explicit |
| Hiworks Tools | `scripts/browser/cdp/cdp_client.py hiworks ...`, `scripts/hiworks/*` | Work/External Tools | send/submit approval-gated |
| Gabia Tools | `scripts/browser/cdp/cdp_client.py gabia ...`, `scripts/gabia/*` | Domain/Ops Tools | DNS/domain/hosting changes approval-gated; login/payment user-direct |
| CAD Tools | `scripts/cad/*`, `admin-web/src/app/cad` | `/cad` | local/desktop workflow boundary |
| File Map Tools | `admin-web/src/app/file-map`, `admin-web/src/app/api/file-map/*` | `/file-map` | cleanup execution approval-gated |
| Ops / Runtime Tools | `scripts/ops/*`, `admin-web/src/app/ops` | `/ops` | deploy/drift/runtime actions gated by ops policy |
| Local Agent Runtime | `local_agent/*`, `ai_orchestrator/local_agent/*` | `/local-agents`, Work Automation | loopback/local-agent security boundaries |
| External MCP / Tool Gateway | `configs/external_mcp_registry.template.json`, `docs/baseline/MCP_GATEWAY_BASELINE.md` | Tool Catalog (home surface retired 2026-10-05) | disabled-by-default registry; secrets by env refs only; writes approval-gated |

## External MCP Gateway Rule

Multiple external MCP servers or owned app adapters may be connected to this
app only through the MCP Gateway registry:

```text
configs/external_mcp_registry.template.json
```

The registry is disabled by default and contains no raw secrets. Each entry must
declare allowed tools, blocked tools, owner app, risk level, UI surface, result
target, and approval policy.

### Current status (2026-10-05, user-confirmed)

The MCP Gateway surface is retired and is not exposed on the home screen. After
the home rewrite (commit 855d595a, "single AI console") the home is a single AI
console, not a dashboard; the registry and its disabled-by-default rules above
remain as backend/config policy only. MCP Gateway readiness is not shown on home.
`tools/audits/agent/audit_mcp_gateway_baseline.py` enforces this: the home page must not
contain the retired MCP Gateway strings.

### Previous baseline (retired, kept for history)

~~MCP Gateway readiness must be visible in the app before real MCP calls are
enabled.~~ (Retired 2026-10-05; superseded by the current status above.)

## UI Design Rules

- The app uses a restrained operations dashboard style: dense, scannable, and
  work-focused.
- Detailed UI structure is locked in
  `docs/baseline/AI_AGENT_UI_STRUCTURE_BLUEPRINT.md`. Tool screens must follow
  its Tool Surface Template, Result Panel, Approval Panel, Work Record Panel,
  navigation, responsive, and required-state rules.
- Do not create landing pages for internal tools. The first screen must be the
  usable tool surface or dashboard.
- Main navigation stays as app modules, not external domains.
- Use compact tables, metric strips, filters, segmented controls, toggles, and
  bounded forms for operational work.
- Do not place cards inside cards. Use cards only for repeated items, modals,
  or framed tools.
- Keep page sections unframed or as full-width operational panels with clear
  table/list content.
- Buttons must represent clear commands. Risky commands must show their gate
  and bounded inputs before execution.
- Every execution-capable UI must show status, limits, source policy, and
  output artifacts.
- Text must fit on mobile and desktop. Use stable dimensions for tables,
  counters, command panels, and toolbars.
- Avoid one-note palettes. The current app uses white/gray operational surfaces
  with orange action accents; new pages should follow that rather than inventing
  a new theme.

## Execution And Gate Rules

- UI actions must call a bounded API route or backend task endpoint, not raw
  shell text.
- When a route executes a local script, it must use array arguments, fixed
  executable paths, allowlisted operation names, and numeric limits.
- State-changing actions require explicit approval or must stop before final
  submit.
- User-direct actions include login, OTP, payment, credential issuance, final
  secret display, billing, publish, upload live execution, destructive changes,
  and account permission changes.
- Read-only and prepare actions may run automatically only when their policy is
  documented and covered by tests/audits.
- Logs and UI output must not expose raw cookies, sessions, passwords, OTPs,
  API keys, bearer tokens, Authorization headers, or raw secrets.
- Full transcript storage is allowed only for user-provided, owned, licensed,
  or officially authorized caption files after rights confirmation.

## Domain Split Rule

Do not create a separate domain for a tool by default.

A separate domain may be proposed only when all conditions are met:

- external users must access the tool independently;
- project/user-level storage, permissions, retention, and support workflows are
  required;
- usage limits, billing, or quota controls are required;
- the tool needs an independent release/deploy lifecycle;
- the user explicitly approves productization.

Until that approval, the tool belongs inside `admin-web` and the shared backend
or local-agent execution model.

## Adding A New Tool

A new tool is accepted only when all items are complete:

- The tool appears in this baseline or a referenced module baseline.
- The owner module and command/API entrypoint are documented.
- The UI route is added to navigation only after the data source and gate are
  available.
- Execution inputs are allowlisted and bounded.
- State-changing work is approval-gated or user-direct.
- Reports are stored under `data/` or `docs/reports/` with secrets masked.
- Tests or audit assertions cover the route, gate, and output policy.
- `python tools/quality/required_quality_gate.py` passes.

## Required Verification

Before claiming the AI agent app structure is ready:

```powershell
npm run typecheck
npm run build
python tools/audits/app/audit_app_structure_contract.py
python tools/audits/app/audit_site_work_function_baseline.py
python tools/quality/required_quality_gate.py
```

`npm` commands run from `admin-web/`. Python commands run from the repo root.

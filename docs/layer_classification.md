# Codebase Layer Classification

Updated: 2026-05-13

This repository currently contains platform code, local PC automation, site-specific business automation, admin UI, tests, generated data, and archived probes. New code must be placed by responsibility, not by convenience.

## Layer Map

| Layer | Purpose | Primary Paths | Rule |
| --- | --- | --- | --- |
| L0 Runtime/Data | Generated state, downloads, logs, screenshots, temporary probes | `data/`, `logs/`, `runs/`, `tmp/`, `storage/`, root `screenshot_*.png` | Do not import from here. Runtime output only. |
| L1 Shared Contracts | DTOs, schemas, risk enums, gate results, common security/redaction helpers | `scripts/common/schemas.py`, `scripts/common/security.py`, `ai_orchestrator/**/schemas.py`, `agent/**/models.py` | Pure definitions. No browser, DB, or network side effects. |
| L2 Policy/Gate/Security | Risk gates, approval rules, allowlists, redaction, permission checks | `scripts/common/gate.py`, `ai_orchestrator/browser_tool/*policy*.py`, `ai_orchestrator/local_agent/*policy*.py`, `agent/*policy*.py` | Centralize decisions here. Business modules should call gates, not duplicate rules. |
| L3 Connectors/Adapters | External system clients and low-level IO wrappers | `scripts/web_connector.py`, `ai_orchestrator/connectors/`, `agent/connectors/`, `browser_worker/backends/`, `mcp_server/` | Encapsulate API, CDP, COM, filesystem, or MCP access. No business decisions. |
| L4 Browser/Automation Engine | Generic browser actions, page scanning, popup handling, session handling | `scripts/cdp_*.py`, `scripts/browser/navigator/navigator.py`, `scripts/explorer/`, `scripts/form/`, `scripts/browser/agent/`, `local_agent/browser_*.py` | Reusable browser behavior only. Site-specific selectors belong in L5. |
| L5 Site Modules | Site-specific routers, workflows, selectors, page capability maps | `scripts/eum/`, `scripts/hiworks/`, `scripts/naver/`, `scripts/google/`, `scripts/g2b/`, `scripts/kakao/`, `scripts/smartstore/` | Each site owns its router, schema/catalog, explorer, workflows, and tests. |
| L6 Business Workflows | Company task flows combining site data and business rules | `scripts/eum/sales_mail.py`, `scripts/eum/workspace.py`, `scripts/hiworks/workflows.py`, `scripts/hiworks/mail_batch.py` | Prepare work, queues, drafts, and evidence. Sending/submitting remains approval-gated. |
| L7 Persistence/Audit | DB tables, run logs, queue persistence, audit records | `scripts/browser/cdp/cdp_db.py`, `scripts/common/op_log.py`, `audit_logger.py`, `ai_orchestrator/**audit*.py`, migrations | Store metadata, hashes, previews, and status. Do not store plaintext secrets or full sensitive bodies unless explicitly required. |
| L8 Server API | FastAPI/Flask routers and task APIs | `ai_orchestrator/*router.py`, `ai_orchestrator/server/`, `browser_api/`, root `dashboard.py`, `app.py` | Thin routing only. Delegate to L2-L6. |
| L9 Admin UI | Next.js/Flask UI components and API routes | `admin-web/`, `ui/templates/`, `desktop/` | UI state and presentation. No direct browser or OS automation. |
| L10 Local PC App Automation | Excel, HWP/HWPX, CAD, inventory, file-map, software install automation | `agent/excel/`, `agent/hancom/`, `agent/local_inventory/`, `agent/local_software_manager/`, `local_agent/cad/` | Local machine capabilities. Must keep approval, backup, and path policy boundaries. |
| L11 Tests/Fixtures | Unit, policy, integration, and smoke tests | `tests/`, `ai_orchestrator/tests/`, `agent/tests/`, `mcp_server/tests/`, `admin-web/**/__tests__/` | Tests mirror the layer they validate. Avoid live-site side effects by default. |
| L12 Docs/Reports/Archive | Historical plans, reports, deprecated probes, design notes | `docs/`, `docs/reports/`, `scripts/archive/`, root handover reports | Reference only. Do not add active runtime code here. |

## Site Module Standard

Every new site module should follow this structure:

```text
scripts/<site>/
  __init__.py
  router.py        # CLI dispatch only
  schemas.py       # app/page/workflow DTOs and constants
  gates.py         # site operation names and risk mapping helpers
  explorer.py      # read-only page/app discovery
  workflows.py     # business workflow orchestration
  <feature>.py     # focused implementation modules
```

Required rules:

| Concern | Target Layer | Rule |
| --- | --- | --- |
| CLI command parsing | L5 `router.py` | Keep thin. Do not put long browser/business logic here. |
| Page/app catalog | L5 `schemas.py` | Static URLs, labels, and capability definitions. |
| Risk decision | L2 or L5 `gates.py` | Use `scripts.common.gate.check()`; never bypass send/submit gates. |
| Browser selection | L3/L4 | Use `get_page_by_url()` for multi-tab CDP sessions. |
| Read-only exploration | L5 `explorer.py` | Navigate and inspect only. Do not click mutating buttons. |
| Draft/queue preparation | L6 | Allowed with `type_into` or `notify` gates; no send click. |
| Actual send/submit/delete/approval | L2 gate + explicit workflow | Must require approval gate and audit record. |
| DB/audit writes | L7 | Save hashes/previews/status, not passwords/tokens/raw secrets. |

## Current Active Site Classification

| Site | Current Status | Keep Building In |
| --- | --- | --- |
| EUM | Most complete site module: auth/navigation/explorer/install-target Excel/sales-mail queue/workspace | `scripts/eum/` |
| Hiworks | Baseline complete: dashboard/app scan, mail open, compose fill-only, sales-mail dry-run plan | `scripts/hiworks/` |
| Naver | Broad but mixed module: mail/blog/cafe/pay/mybox/smartstore/automation | `scripts/naver/` |
| Google/Gmail | API and browser modules separated better than others | `scripts/google/` |
| G2B | Read-only public notice/download discovery module | `scripts/g2b/` |
| Kakao/Smartstore | Smaller or legacy-oriented site modules | `scripts/kakao/`, `scripts/smartstore/` |

## Known Structural Problems

| Problem | Impact | Fix Direction |
| --- | --- | --- |
| Root has many one-off scripts | Hard to know active vs legacy | Move active scripts into site/module folders; archive old probes. |
| Worktree has many concurrent changes | Hard to stage and review by intent | Use `tools/devflow/worktree_change_index.py` and handle one owner/category at a time. |
| Encoding corruption in some Korean docstrings/comments | Hard to read and maintain | Avoid editing corrupted comments unless rewriting full file as UTF-8. |
| Multiple browser stacks coexist | Confusing execution path | Use `scripts/cdp_client.py` + `scripts/site_engine/command_router.py` for current site CLI; platform APIs stay under `ai_orchestrator/`. |
| Archive/debug files are mixed in scans | False positives in architecture review | Exclude `scripts/archive/`, `docs/reports/`, `data/`, `tmp/`, `logs/` from active-code decisions. |
| DB and audit are partially centralized | Risk of duplicate persistence paths | New site workflows should write via `scripts/browser/cdp/cdp_db.py` and `scripts/common/op_log.py` unless platform API requires another store. |

## Hiworks Placement Decision

For the current Hiworks build-out:

| Feature | Destination |
| --- | --- |
| Hiworks app catalog and URL map | `scripts/hiworks/schemas.py` |
| Full read-only app/page exploration | `scripts/hiworks/explorer.py` |
| Mail compose form detection/fill | `scripts/hiworks/mail.py` |
| Sales-mail queue handoff and send plan | `scripts/hiworks/workflows.py` and existing `scripts/hiworks/mail_batch.py` |
| CLI commands | `scripts/hiworks/router.py` only as dispatcher |
| Risk operation constants | `scripts/hiworks/gates.py` |
| Queue/run persistence | `scripts/browser/cdp/cdp_db.py` |
| Tests | `tests/test_hiworks_*.py` |

The previous `FAT_SITE_ROUTER` residual for `scripts/hiworks/router.py` is resolved: the router is now a dispatcher and Hiworks logic lives in focused modules.

## Active-Code Scan Boundaries

Use this command pattern for active code review:

```powershell
rg --files -g "*.py" -g "!scripts/archive/**" -g "!data/**" -g "!tmp/**" -g "!logs/**"
```

Use this pattern for site-specific review:

```powershell
rg --files scripts/eum scripts/hiworks scripts/naver scripts/google scripts/g2b scripts/kakao scripts/smartstore -g "*.py"
```

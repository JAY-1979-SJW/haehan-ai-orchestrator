# Google Developed Tools Index

Updated: 2026-05-27

This document records only the Google and YouTube tools that have been
developed, gated, or verified in this repo. Check this index and
`docs/google_domain_function_index.md` before adding more Google automation.

## Operating Rules

- Enter Google through Google Home first: `https://www.google.com/`.
- Select `google_work_mode=main` or `google_work_mode=background` before Google
  browser work.
- Background work requires explicit task-scoped `background_approved=True`.
- Login, MFA, CAPTCHA, recovery, and final approval controls stay user-present.
- Read/search work may run after session and work-mode checks.
- Draft, upload, share, save, create, update, OAuth/API key issue, ad signup,
  publish, billing, IAM, and release actions require explicit approval or stop
  before the final control.
- Raw secrets, saved passwords, Google Account permission changes, billing
  submission, campaign launch, and destructive actions are blocked or
  user-only.

## Core Gates

| Gate | Applies To | Policy |
| --- | --- | --- |
| `google_home_login_gate` | Google login/session entry | Must start from Google Home, not direct `accounts.google.com` login. |
| `google_work_mode_gate` | All Google browser tasks | Requires `main` or approved `background`; blocks missing mode. |
| `google_workspace_basic` | Common consumer/Workspace tasks | Separates `read_only`, `draft_only_no_final_submit`, `approval_required`, and `user_only`. |
| `google_ads_signup` | Google Ads signup / Keyword Planner access | No paid action; billing, budget, campaign publish, and asset consent are blocked without exact approval. |
| `google_secret_action_gate` | OAuth/API key/client secret issuance | Final approval only by default; raw secret output is blocked. |
| `google_vision_usage_gate` | Google Vision API usage | Monthly free-unit gate: 1,000 units; warning at 800; paid overage requires approval. |
| `google_live_input_no_final_submit` | Live form fill | Allows prefill only with `--no-final-submit`. |

## Tool Catalog

| Area | Command | Risk | Status | Main Files | Output |
| --- | --- | --- | --- | --- | --- |
| Session check | `python scripts\entry\cdp_cli.py google session-check` | read | implemented | `scripts/google/common/base.py`, `scripts/google/router.py` | console status |
| User-present login | `python scripts\entry\cdp_cli.py google login` | user-present | implemented | `scripts/google/auth.py`, `scripts/google/router.py` | console status |
| Basic feature catalog | `python scripts\entry\cdp_cli.py google basic catalog` | read | implemented | `scripts/google/workspace_basic.py` | console JSON |
| Basic feature plan | `python scripts\entry\cdp_cli.py google basic plan <surface> <operation> ... --google-work-mode=main` | read/prepare/approval/user-only | implemented | `scripts/google/workspace_basic.py`, `scripts/common/gates/work_mode_gate.py` | console JSON |
| Gmail list/analyze/compose | `python scripts\entry\cdp_cli.py google mail <list|analyze|compose>` | read/prepare | implemented | `scripts/google/workspace/gmail.py`, `scripts/google/common/gmail_analysis.py` | console/data |
| Gmail send gate | `python scripts\entry\cdp_cli.py google mail send ...` | approval/user-only | gated | `scripts/google/workspace/gmail.py`, `scripts/common/gate.py` | approval-gated action |
| Drive wrapper | `python scripts\entry\cdp_cli.py google drive <list|search|file_info>` | read/partial | implemented partial | `scripts/google/workspace/drive.py`, `scripts/google/common/drive.py` | console/data |
| Calendar wrapper | `python scripts\entry\cdp_cli.py google calendar <today|search>` | read/partial | implemented partial | `scripts/google/workspace/calendar_tasks.py`, `scripts/google/common/calendar_tasks.py` | console/data |
| Docs wrapper | `python scripts\entry\cdp_cli.py google docs <recent|create_prepare>` | read/prepare partial | implemented partial | `scripts/google/workspace/docs.py`, `scripts/google/common/docs.py` | console/data |
| Sheets wrapper | `python scripts\entry\cdp_cli.py google sheets <recent|update_prepare>` | read/prepare partial | implemented partial | `scripts/google/workspace/sheets.py`, `scripts/google/common/sheets.py` | console/data |
| Workspace wrappers | Workspace router for Slides, Forms, Meet, Chat, Contacts, Keep, Tasks | read/prepare | implemented | `scripts/google/workspace/*`, `scripts/google/workspace/router.py` | console/data |
| Surface catalog | `python scripts\entry\cdp_cli.py google surfaces catalog` | read | implemented | `scripts/google/common/surfaces.py`, `scripts/google/common/surface_explorer.py` | `data/google_surface_catalog_latest.json` |
| Surface live read | `python scripts\entry\cdp_cli.py google surfaces live-read --limit=...` | read | verified read-only | `scripts/google/live_surface_explorer.py` | `data/google_surface_live_latest.json` |
| Subdomain catalog/classify | `python scripts\entry\cdp_cli.py google subdomains catalog`, `classify <host> <operation>` | read/policy | implemented | `scripts/google/common/subdomain_logic.py` | console JSON |
| Tab catalog/classify | `python scripts\entry\cdp_cli.py google tabs catalog`, `classify <tab> <host> <operation>` | read/policy | implemented | `scripts/google/common/tab_logic.py` | console JSON |
| Cloud Console read | `python scripts\entry\cdp_cli.py google cloud live-read --limit=...` | read | verified read-only | `scripts/google/cloud/live_console_explorer.py` | `data/google_cloud_console_live_latest.json` |
| Managed Console OAuth plan | `python scripts\entry\cdp_cli.py google console youtube-oauth-plan` | prepare | implemented | `scripts/google/managed_console.py`, `scripts/youtube/oauth.py` | console JSON |
| Managed Console OAuth open/fill | `python scripts\entry\cdp_cli.py google console youtube-oauth-open --dry-run`, `youtube-oauth-fill --dry-run` | prepare/no-final-submit | gated | `scripts/google/managed_console.py`, `scripts/google/oauth_console_fill.py` | `data/google_console_oauth_fill_latest.json` |
| YouTube OAuth preapproval | `python scripts\entry\cdp_cli.py youtube oauth preapproval` | prepare | implemented | `scripts/youtube/oauth.py`, `scripts/youtube/router.py` | callback/preapproval plan |
| YouTube catalog/tabs/classify | `python scripts\entry\cdp_cli.py google youtube catalog`, `tabs`, `classify` | read/policy | implemented | `scripts/google/youtube/`, `scripts/google/router.py` | console JSON |
| YouTube video search | `python scripts\entry\cdp_cli.py google youtube search --query=... [--source=auto|official|browser] [--limit=10]` | read | implemented | `scripts/google/youtube/search.py`, `scripts/google/router.py` | `data/google_youtube_search_latest.json` |
| YouTube rank/transcript analysis | `python scripts\entry\cdp_cli.py google youtube rank --query=... [--limit=5] [--collect-transcripts=true]` | read | implemented | `scripts/google/youtube/search.py`, `scripts/google/router.py` | `data/google_youtube_rank_analysis_latest.json` |
| YouTube keyword topic market analysis | `python scripts\entry\cdp_cli.py google youtube topic --keywords=...,... [--per-keyword-limit=10] [--collect-transcripts=false]` | read | implemented | `scripts/google/youtube/search.py`, `scripts/google/router.py` | `data/google_youtube_topic_analysis_latest.json` |
| YouTube upload prepare | `python scripts\entry\cdp_cli.py google youtube upload-prepare ...` | prepare | implemented | `scripts/google/common/youtube_upload.py`, `scripts/google/common/workflows.py` | `data/google_youtube_upload_plan_latest.json` |
| YouTube upload live fill | `python scripts\entry\cdp_cli.py google youtube upload-live-fill <plan_path> --no-final-submit` | prepare/no-final-submit | gated | `scripts/google/common/live_inputs.py`, `scripts/google/common/youtube_upload.py` | live-fill report |
| Google Ads signup plan | `python scripts\entry\cdp_cli.py google ads signup-plan --google-work-mode=main --ads-signup-approved` | approval/no-paid-action | implemented gate | `scripts/google/ads_signup.py` | console JSON |
| Google Ads screen classify | `python scripts\entry\cdp_cli.py google ads classify <screen text>` | policy | implemented | `scripts/google/ads_signup.py` | console JSON |
| Google AI labels | `python scripts\entry\cdp_cli.py google ai catalog` | read | implemented | `scripts/google/ai_usage_labels.py` | console JSON |
| Google Vision free gate | `python scripts\entry\cdp_cli.py google vision gate --images=... --features=...` | read/cost-gated | implemented | `scripts/google/vision_usage_gate.py` | `data/google_vision_usage_gate_latest.json` |
| Android app dev report | `python scripts\entry\cdp_cli.py google android report` | read/report | implemented | `scripts/google/android_app_dev_report.py`, `scripts/google/android_app_dev_labels.py` | `docs/reports/google_android_app_dev_report_*.md` |
| Domain taxonomy | `python scripts\entry\cdp_cli.py google domains report` | read/report | implemented | `scripts/google/common/domain_taxonomy.py` | `data/google_domain_taxonomy_latest.json` |
| Precision report | `python scripts\entry\cdp_cli.py google precision build` | read/report | implemented | `scripts/google/precision_report.py` | `data/google_precision_report_latest.json` |
| Work action catalog | `python scripts\entry\cdp_cli.py google work catalog` | read | implemented | `scripts/google/common/workflows.py` | `data/google_work_action_catalog_latest.json` |
| Work adapter catalog | `python scripts\entry\cdp_cli.py google work ai_orchestrator.connectors.g2b` | read | implemented | `scripts/google/common/workflows.py` | `data/google_execution_adapter_catalog_latest.json` |
| Work prepare | `python scripts\entry\cdp_cli.py google work prepare <action_key> key=value ...` | prepare | implemented | `scripts/google/common/workflows.py` | `data/google_prepare_latest.json` |
| Work execute | `python scripts\entry\cdp_cli.py google work execute <plan_path> --approved --confirm=GOOGLE_APPROVED_EXECUTE` | approval | gated | `scripts/google/common/workflows.py` | execution result JSON |
| Work verify | `python scripts\entry\cdp_cli.py google work verify <result_path>` | read | implemented | `scripts/google/common/workflows.py` | verification JSON |
| Work live fill | `python scripts\entry\cdp_cli.py google work live-fill <plan_path> --no-final-submit` | prepare/no-final-submit | gated | `scripts/google/common/live_inputs.py` | `data/google_live_input_latest.json` |
| Work live-fill manifest | `python scripts\entry\cdp_cli.py google work live-fill-manifest <manifest_path> --no-final-submit` | prepare/no-final-submit | gated | `scripts/google/common/live_inputs.py` | `data/google_live_input_manifest_latest.json` |
| Work coverage/gaps | `python scripts\entry\cdp_cli.py google work live-coverage`, `undeveloped` | read/report | implemented | `scripts/google/common/live_inputs.py`, `scripts/google/common/workflows.py` | `data/google_live_input_coverage_latest.json`, `data/google_work_undeveloped_latest.json` |

## Basic Feature Surfaces

Market Research / YouTube Research is locked as an internal module of the
current app. It should use topic presets and keyword expansion inside the
existing Google/YouTube tooling, not a separate public domain, unless a later
productization plan is explicitly approved.

YouTube topic presets support `--topic=<name> --auto-keywords` for common
research areas such as `스마트스토어`, `쇼핑몰`, `구매대행`, `마케팅`, and
`ai업무자동화`.

Example:

```powershell
python scripts\entry\cdp_cli.py google youtube topic --topic=스마트스토어 --auto-keywords --per-keyword-limit=10 --collect-transcripts=false
```

`scripts/google/workspace_basic.py` currently locks 22 surfaces and 59 feature
plans:

| Surface | Read/Search | Prepare/Approval | User-Only / Blocked Boundary |
| --- | --- | --- | --- |
| Gmail | list, search, read/analyze | compose draft | send, delete |
| Drive | list, search, file info | upload/share prepare | delete |
| Photos | list, search, album list | download/share/upload prepare | delete, face/location/EXIF output |
| Calendar | today, search | event create prepare | final create without approval |
| Docs | recent | create/edit prepare | final save/publish without approval |
| Sheets | recent | cell update prepare | final update without approval |
| Slides | recent | later prepare work through workflow gate | final publish without approval |
| Forms | recent | later prepare work through workflow gate | final publish without approval |
| Meet | none | meeting prepare | final create without approval |
| Chat | spaces list | message draft | final send without approval |
| Contacts | list | contact create prepare | final create without approval |
| Keep | list | note draft | final save without approval |
| Tasks | list | task draft | final save without approval |
| Search | web search, related queries | save result prepare | save without approval |
| YouTube | search videos, summarize video prepare | playlist save prepare | playlist change without approval |
| Maps | place search, route check | save place prepare | location-history output |
| Translate | text translate | document translate prepare | document upload without approval |
| News | search news, briefing | none | state-changing actions |
| Alerts | none | alert create prepare | alert creation without approval |
| Shopping | product search, compare prices | none | purchase/payment |
| Google Account | security check, connected apps check | none | revoke access/permission changes |
| Chrome | bookmarks check, history search | none | password check/output |

Status counts:

- `read_only`: 34
- `draft_only_no_final_submit`: 4
- `approval_required`: 15
- `user_only`: 6

## Primary Artifacts

- `data/google_surface_catalog_latest.json`
- `data/google_work_action_catalog_latest.json`
- `data/google_execution_adapter_catalog_latest.json`
- `data/google_prepare_latest.json`
- `data/google_live_input_latest.json`
- `data/google_live_input_manifest_latest.json`
- `data/google_live_input_coverage_latest.json`
- `data/google_work_undeveloped_latest.json`
- `data/google_cloud_console_live_latest.json`
- `data/google_domain_taxonomy_latest.json`
- `data/google_console_oauth_fill_latest.json`
- `data/google_vision_usage_gate_latest.json`
- `data/google_youtube_search_latest.json`
- `data/google_youtube_rank_analysis_latest.json`
- `data/google_youtube_topic_analysis_latest.json`
- `data/google_youtube_upload_plan_latest.json`

## Domain Function Index

Use `docs/google_domain_function_index.md` when deciding which Google domain a
new task belongs to. It maps 32 registered hosts to their function, purpose,
allowed automation, and approval or blocked boundary.

## Verification

Latest focused verification:

```powershell
python -m pytest tests\test_google_workspace_basic.py -q
python scripts\ops\audit_google_automation_baseline_contract.py
python tools\quality\required_quality_gate.py
```

Latest result:

- `tests\test_google_workspace_basic.py`: `23 passed`
- `scripts\ops\audit_google_automation_baseline_contract.py`:
  `RESULT=PASS_GOOGLE_AUTOMATION_BASELINE_CONTRACT`
- `tools\quality\required_quality_gate.py`: `RESULT=PASS_REQUIRED_QUALITY_GATE`

## Remaining Work

- Live read reports should be expanded per surface before promoting any
  surface from catalog-first to live-operational.
- Official APIs should be preferred for Gmail, Drive, Calendar, Docs, Sheets,
  Photos, and YouTube when scopes and OAuth approval are available.
- Any new Google tool must be added here, wired into the relevant gate, and
  covered by a focused test before commit.

# Google Business Workflow Reference - 2026-05-13

## Purpose

Google business work is implemented as an approval-gated workflow catalog.
The operator can prepare all required inputs and evidence before final review,
but state-changing execution remains blocked until explicit user approval.

## Pipeline

```text
discover -> plan -> prepare -> approval -> execute -> verify -> log
```

Rules:

- Read actions can open or inspect the target surface.
- Write, publish, upload, billing, IAM, API key, deploy, release, indexing,
  comment, message, and public listing actions require dry-run preparation.
- Final execution requires `--approved --confirm=GOOGLE_APPROVED_EXECUTE`.
- Credentials, cookies, tokens, API keys, and secret values must be redacted.
- Prefer official OAuth/API/CLI paths where available; browser paths are
  handoff/final confirmation paths unless a surface adapter is explicitly
  implemented.

## Artifacts

- Surface catalog: `data/google_surface_catalog_latest.json`
- Action catalog: `data/google_work_action_catalog_latest.json`
- Execution adapter catalog: `data/google_execution_adapter_catalog_latest.json`
- Full Google live-read latest: `data/google_surface_live_latest.json`
- Cloud Console live-read latest: `data/google_cloud_console_live_latest.json`
- Prepare latest: `data/google_prepare_latest.json`
- Prepare history: `data/google_prepares/`
- Execution audit results: `data/google_execution_results/`
- Execution verifications: `data/google_execution_verifications/`

## Commands

```powershell
python scripts\entry\cdp_cli.py google surfaces catalog
python scripts\entry\cdp_cli.py google subdomains catalog
python scripts\entry\cdp_cli.py google subdomains classify gmail read
python scripts\entry\cdp_cli.py google subdomains classify mail.google.com send
python scripts\entry\cdp_cli.py google tabs catalog
python scripts\entry\cdp_cli.py google tabs classify workspace gmail read
python scripts\entry\cdp_cli.py google tabs classify workspace mail.google.com send
python scripts\entry\cdp_cli.py google cloud live-read
python scripts\entry\cdp_cli.py google cloud live-logic
python scripts\entry\cdp_cli.py google surfaces live-read
python scripts\entry\cdp_cli.py google surfaces live-logic
python scripts\entry\cdp_cli.py google work catalog
python scripts\entry\cdp_cli.py google work adapters
python scripts\entry\cdp_cli.py google work live-coverage
python scripts\entry\cdp_cli.py google work prepare youtube_studio_upload_video video_path=C:\tmp\sample.mp4 title=draft description=draft visibility=private
python scripts\entry\cdp_cli.py google work live-fill data\google_prepare_latest.json --no-final-submit
python scripts\entry\cdp_cli.py google work live-fill-manifest configs\google_live_input_manifest_template.json --no-final-submit
python scripts\entry\cdp_cli.py google work execute data\google_prepare_latest.json --approved --confirm=GOOGLE_APPROVED_EXECUTE
python scripts\entry\cdp_cli.py google work verify data\google_execution_results\<result>.json
```

The last command is intentionally approval-gated. Without approval it records a
blocked execution result and does not change Google state.

## Subdomain Logic

`scripts/google/common/subdomain_logic.py` groups the Google surface and workflow
catalogs by host. The logic is intentionally server-first and user-present:

- login operations create only a user-present login entry task; auto-login,
  credential replay, cookies, tokens, and session export stay blocked
- read/open/status/inspect operations create `web_open_url_readonly`
  local-agent tasks
- send, publish, upload, billing, IAM, deploy, secret, credential, delete, and
  other state-changing operations return an approval-gate result without a
  local-agent task
- unknown Google subdomains fail closed

## Tab Logic

`scripts/google/common/tab_logic.py` exposes the same logic per Google tab:
`search`, `identity`, `workspace`, `cloud`, `ai`, `youtube`, `marketing`,
`developer`, and `media`.

Every tab package exports:

- `summary()`
- `catalog()`
- `classify_operation(key_or_host, operation)`

The app can attach tab UI to these functions. A host outside the requested tab
fails closed, read operations stay `web_open_url_readonly`, and state-changing
operations stay approval-gated without creating a local-agent execution task.

Each tab catalog includes `user_guidance` so the app can explain what a user
can request:

- Search: open Google home/search read-only and inspect public controls.
- Identity: check account/login state and guide user-present login.
- Workspace: open Gmail, Drive, Calendar, Docs, Sheets, Slides, Forms, Meet,
  Chat, Contacts, Keep, and Tasks; prepare drafts/plans; approval is required
  for send/share/upload/create/edit/publish/delete.
- Cloud: open Cloud Console surfaces read-only; approval is required for API
  keys, IAM, billing, deploys, resource changes, and secret changes.
- AI: open AI Studio, Gemini, and Vertex AI read-only; approval is required for
  prompts, key creation, training, or deploy.
- YouTube: open YouTube/Studio read-only and prepare upload/metadata plans;
  approval is required for upload, publish, metadata edits, and interactions.
- Marketing: open Search Console, Business Profile, Analytics, Tag Manager,
  Ads, Merchant Center, AdSense, and Looker Studio read-only; approval is
  required for indexing, listing changes, tag publish, ad spend, and merchant
  listing changes.
- Developer: open developer docs, Play Console, Firebase, Apps Script, and
  Colab read-only; approval is required for release, config, deploy, and code
  execution.
- Media: open Photos read-only; approval is required for upload, delete, share,
  or album changes.

## Cloud Console Live Logic

`scripts/google/cloud/live_console_explorer.py` performs direct-CDP,
read-only Cloud Console inspection against the already running local Chrome
debugging profile. It does not use Playwright, does not click, does not type,
does not submit, and does not export cookies, storage, tokens, or secret
values.

The live command stores redacted evidence in:

- `data/google_cloud_console_live_latest.json`
- `data/google_cloud_console_live/`

`google cloud live-logic` converts the latest evidence into Cloud-tab logic:
per surface live-read status, observed headings, observed control counts,
observed risk controls, read actions, and approval-gated actions.
It also includes per-surface `user_guidance`, so the app can show what the user
may ask for on Cloud Console pages such as IAM, Billing, Cloud Run, Compute
Engine, Storage, BigQuery, GKE, SQL, Pub/Sub, Secret Manager, Logging, and
Monitoring.

`scripts/google/live_surface_explorer.py` performs the same direct-CDP,
read-only inspection for all 50 Google surfaces and writes:

- `data/google_surface_live_latest.json`
- `data/google_surface_live/`

`google surfaces live-logic` converts that evidence into app logic for all
Google surfaces, including Search, Identity, Workspace, Cloud, AI, YouTube,
Marketing, Developer, and Media tabs. If a full 50-surface report is not the
latest report, the logic can merge the latest Cloud report so the app still
gets one complete Google live-logic contract.

## Coverage Baseline

- 50 Google surfaces are indexed.
- 50 Google surfaces are represented by `google surfaces live-logic`.
- 96 Google work actions are indexed.
- 50 read actions are implemented as catalog/read entries.
- 46 state-changing actions are implemented as approval-gated prepare/execute
  contracts.
- 96 execution adapter profiles are indexed.
- 9 approval actions have no-final-submit live input/handoff adapters.
- 37 approval actions remain prepare/open-only until surface-specific live
  adapters are added.
- Approved handoff execution can optionally open the target surface with
  `--live-open`; final submit/publish/delete/permission-changing action still
  requires final confirmation evidence.
- Live input can run per plan or from a manifest while preserving
  `--no-final-submit`.
- Live input records detected final controls so the audit artifact can show
  which controls were present but left untouched.

Covered areas include:

- Workspace: Gmail, Drive, Calendar, Docs, Sheets, Slides, Forms, Meet, Chat,
  Contacts, Keep, Tasks, Photos.
- YouTube: YouTube and YouTube Studio uploads, metadata, comments/interactions.
- Developer and AI: Cloud Console, AI Studio, Gemini, Vertex AI, Firebase,
  Apps Script, Colab, Android Developers, Play Console.
- Cloud infrastructure: APIs/Credentials, IAM, Billing, Cloud Run, Compute
  Engine, Cloud Storage, BigQuery, GKE, Cloud SQL, Pub/Sub, Secret Manager,
  Logging, Monitoring.
- Business and marketing: Business Profile, Analytics, Tag Manager, Ads,
  Merchant Center, AdSense, Looker Studio, Maps Platform.

## Approval Boundary

`approved_handoff_ready` means the gate accepted the prepared artifact and the
next adapter/manual final confirmation may proceed under audit logging. It does
not mean the system silently clicked a final submit/publish/delete button.

This keeps the development path complete while preserving the user's final
approval role.

## Live-Fill Manifest

Manifest template:

- `configs/google_live_input_manifest_template.json`
- Coverage latest:
  `data/google_live_input_coverage_latest.json`

Manifest behavior:

- Each item is prepared with `workflows.prepare_action`.
- Missing required inputs are recorded as `blocked_missing_inputs` before the
  browser is touched.
- Supported live adapters fill safe pre-final inputs for Gmail, YouTube Studio
  upload, YouTube Studio metadata lookup, Search Console URL inspection,
  Search Console sitemap input, Cloud IAM, Cloud Credentials, AI Studio API
  key page, and Play Console release handoff.
- Unsupported actions open/read the target only and record skipped inputs.
- Final controls such as `Send`, `Publish`, `Submit`, `Save`, `Grant`,
  `Request indexing`, and `Release` remain blocked until explicit approval.

## Current Live-Fill Coverage

Supported no-final-submit live adapters:

- `gmail_send_email`
- `youtube_studio_upload_video`
- `youtube_studio_edit_video_metadata`
- `search_console_submit_indexing`
- `search_console_submit_sitemap`
- `ai_studio_create_api_key`
- `play_console_prepare_release`
- `cloud_create_api_credential`
- `cloud_iam_change_role`

Remaining approval actions stay at prepare/open-only unless a surface-specific
safe adapter is added and tested.

## Completion Definition

Google is considered complete at the common baseline when every action has:

- a surface entry
- a work action entry
- a prepare contract
- an execution adapter profile
- approval policy
- evidence requirements
- verification checks
- audit artifact paths

Surface-specific final adapters may still be strengthened later, but they must
plug into this contract and cannot bypass approval.

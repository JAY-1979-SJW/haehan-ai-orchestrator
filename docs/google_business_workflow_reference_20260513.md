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
- Prepare latest: `data/google_prepare_latest.json`
- Prepare history: `data/google_prepares/`
- Execution audit results: `data/google_execution_results/`
- Execution verifications: `data/google_execution_verifications/`

## Commands

```powershell
python scripts\cdp_client.py google surfaces catalog
python scripts\cdp_client.py google work catalog
python scripts\cdp_client.py google work adapters
python scripts\cdp_client.py google work live-coverage
python scripts\cdp_client.py google work prepare youtube_studio_upload_video video_path=C:\tmp\sample.mp4 title=draft description=draft visibility=private
python scripts\cdp_client.py google work live-fill data\google_prepare_latest.json --no-final-submit
python scripts\cdp_client.py google work live-fill-manifest configs\google_live_input_manifest_template.json --no-final-submit
python scripts\cdp_client.py google work execute data\google_prepare_latest.json --approved --confirm=GOOGLE_APPROVED_EXECUTE
python scripts\cdp_client.py google work verify data\google_execution_results\<result>.json
```

The last command is intentionally approval-gated. Without approval it records a
blocked execution result and does not change Google state.

## Coverage Baseline

- 50 Google surfaces are indexed.
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

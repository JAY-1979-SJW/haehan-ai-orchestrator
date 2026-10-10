# Google Surface Catalog Reference - 2026-05-13

## Purpose

Google work starts with a static surface catalog before live browser work.
This prevents blind clicking across account, billing, developer, creator, and
publishing consoles.

## Common Rule

Order of work:

1. Confirm CDP live endpoint is responding.
2. Generate or read `data/google_surface_catalog_latest.json`.
3. Finish one surface before moving to the next.
4. Prefer official OAuth/API paths for private Google data.
5. Require dry-run and explicit approval before write, publish, billing, IAM,
   upload, release, API key, or indexing actions.
6. Live exploration is read-only: URL navigation and DOM inspection only.
   No clicks, no typing, no submit/publish/save/release controls.

## Included Surfaces

The catalog currently indexes 50 Google surfaces. Core groups:

- Workspace: Google Home, Google Account, Gmail, Drive, Calendar, Docs, Sheets,
  Slides, Forms, Meet, Chat, Contacts, Keep, Tasks, Photos.
- YouTube and creator: YouTube, YouTube Studio.
- Developer and AI: Google Cloud Console, Search Console, Google AI Studio,
  Gemini, Android Developers, Google Play Console, Firebase Console, Google for
  Developers, Chrome for Developers, Apps Script, Colab, Vertex AI.
- Cloud products: APIs/Credentials, IAM, Billing, Cloud Run, Compute Engine,
  Cloud Storage, BigQuery, GKE, Cloud SQL, Pub/Sub, Secret Manager, Logging,
  Monitoring, Maps Platform.
- Business and marketing: Business Profile, Analytics, Tag Manager, Ads,
  Merchant Center, AdSense, Looker Studio.

## Command

```powershell
python scripts\entry\cdp_cli.py google surfaces catalog
python scripts\entry\cdp_cli.py google surfaces explore --timeout-ms=45000
python scripts\entry\cdp_cli.py google work catalog
```

Outputs:

- `data/google_surface_catalog_latest.json`
- `data/google_surface_catalogs/google_surface_catalog_<timestamp>.json`
- `data/google_surface_exploration_latest.json`
- `data/google_surface_explorations/google_surface_exploration_<timestamp>.json`
- `data/google_work_action_catalog_latest.json`
- `data/google_work_action_catalogs/google_work_action_catalog_<timestamp>.json`
- `data/google_execution_adapter_catalog_latest.json`
- `data/google_execution_adapter_catalogs/google_execution_adapter_catalog_<timestamp>.json`

## Work Action Catalog

Reference: `docs/google_business_workflow_reference_20260513.md`

Current baseline:

- 96 total Google work actions
- 50 read actions
- 46 approval-gated state-changing actions
- 96 execution adapter profiles

Approval-gated actions include Gmail send, Drive upload/share, Calendar event
create, Docs/Sheets/Slides/Forms edits, YouTube Studio upload/metadata, Search
Console indexing/sitemap, AI Studio key creation, Gemini prompt submission, Play
Console release preparation, Firebase deploy, Cloud IAM/Billing/Run/Compute/
Storage/BigQuery/GKE/SQL/PubSub/Secret/Logging/Monitoring/Vertex changes,
Business Profile updates, Analytics/Tag Manager/Ads/Merchant/AdSense/Looker
changes.

Every work action now has an execution adapter profile. The adapter profile
defines the execution mode, final-state policy, evidence requirements,
verification checks, and rollback notes.

## Status

Full read-only surface exploration is now complete:

- planned surfaces: 50
- visited surfaces: 50
- accessible surfaces: 45
- login-required surfaces: 5
- failed surfaces: 0
- surfaces with risk controls detected: 29
- latest evidence:
  `data/google_surface_exploration_latest.json`

The broader Google/YouTube work remains catalog-first and read-only until a
per-surface workflow is prepared and approved.

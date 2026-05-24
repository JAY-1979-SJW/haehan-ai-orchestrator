# HAEHAN Google Automation Baseline

Status: LOCKED
Baseline ID: GOOGLE-AUTOMATION-BASELINE-01
Approved by: user approval in current Codex session
Baseline HEAD: c2307e8ffe9d38d6842a542c7be68efe5f234b09
Last updated: 2026-05-24

## 1. Purpose

This baseline locks the Google automation structure before deeper refactoring.
Google work must be managed by sub-tab, host, risk, authentication policy, and
verification. New Google work must be registered before implementation.

Current locked counts:

- Google tabs: 9
- Google surfaces: 50
- Google actions: 96
- Read actions: 50
- Approval actions: 46
- Host normalization warnings: 0

## 2. Required Sub-Tabs

Every Google surface and action must belong to exactly one sub-tab:

| Tab | Responsibility |
| --- | --- |
| `search` | Google Home and public search entry points |
| `identity` | Google Account, login state, and user-present session policy |
| `workspace` | Gmail, Drive, Calendar, Docs, Sheets, Slides, Forms, Meet, Chat, Contacts, Keep, Tasks |
| `cloud` | Cloud Console, IAM, Billing, Cloud Run, Compute, Storage, BigQuery, GKE, SQL, Pub/Sub, Secret Manager, Logging, Monitoring |
| `ai` | AI Studio, Gemini, Vertex AI |
| `youtube` | YouTube and YouTube Studio |
| `marketing` | Search Console, Ads, Analytics, Tag Manager, Merchant Center, Business Profile, AdSense, Looker Studio |
| `developer` | Firebase, Apps Script, Colab, Play Console, Google/Chrome/Android developer docs |
| `media` | Google Photos and private media workflows |

The code contract is `scripts/google/tab_registry.py`.

## 3. Authentication Rules

Allowed:

- existing browser session
- user-present login session
- official OAuth/API flow after separate approval

Forbidden:

- Google ID/password replay
- saved Google password credential storage
- automatic MFA/2FA bypass
- cookie, token, storage state, Authorization, OTP, or password output
- account, mail, file, prompt, or private content output in logs

The active login method is `user_present_session`.

## 4. Action Risk Rules

Google actions are classified into:

- Read: open or inspect without state change.
- Prepare: create a plan, manifest, diff, or handoff artifact with no state change.
- Approval: send, upload, create, edit, delete, publish, deploy, grant, bill, spend, execute, or submit.

Approval actions must:

- require explicit approval
- keep `state_change` false until final user-approved execution
- require an approval phrase where the workflow supports final execution
- default to no final submit for live browser input
- save a verification or evidence artifact

## 5. Host Rules

Surface host and action target host must match unless a documented exception is
approved. The current baseline requires:

```text
host_warnings == []
```

Representative host boundaries:

- `mail.google.com`: Gmail
- `drive.google.com`: Drive
- `calendar.google.com`: Calendar
- `docs.google.com`: Docs, Sheets, Slides, Forms
- `console.cloud.google.com`: Cloud, IAM, Billing, Infra, Vertex
- `studio.youtube.com`: YouTube Studio
- `www.youtube.com`: YouTube
- `search.google.com`: Search Console
- `aistudio.google.com`: AI Studio
- `gemini.google.com`: Gemini
- `ads.google.com`: Ads
- `analytics.google.com`: Analytics
- `tagmanager.google.com`: Tag Manager
- `merchants.google.com`: Merchant Center
- `adsense.google.com`: AdSense

## 6. Current Code Ownership

- `scripts/google/auth.py`: user-present Google session authentication.
- `scripts/google/tab_registry.py`: official Google sub-tab registry.
- `scripts/google/surfaces.py`: 50 Google surfaces.
- `scripts/google/workflows.py`: 96 Google actions and approval handoff contract.
- `scripts/google/live_inputs.py`: live input coverage and no-final-submit policy.
- `tests/test_google_tab_registry.py`: tab, host, count, and owner-package contract.

## 7. Required Verification

Minimum verification before committing Google work:

```text
python -m py_compile scripts/google/auth.py scripts/google/tab_registry.py scripts/google/surfaces.py scripts/google/workflows.py scripts/google/live_inputs.py
python -m pytest tests/test_google_tab_registry.py tests/test_google_site_engine.py tests/test_google_surfaces.py tests/test_google_workflows.py tests/test_google_user_present_session_auth.py tests/test_youtube_site_engine.py tests/test_youtube_workflow.py -q
python scripts/ops/audit_google_automation_baseline_contract.py
python scripts/module_quality_gate.py --module repo_guard
```

## 8. Development Sequence

Google refactoring must be staged:

1. Baseline and registry lock.
2. Workspace module split. Detailed baseline: `docs/baseline/GOOGLE_WORKSPACE_MODULE_BASELINE.md`.
3. Cloud module split. Detailed baseline: `docs/baseline/GOOGLE_CLOUD_MODULE_BASELINE.md`.
4. YouTube module split.
5. Marketing module split.
6. AI and developer module split.
7. Dedicated Google gates in release checks.

Do not split all Google modules in one change.

## 9. Known WARN

- Runtime live E2E with real Google account/OAuth is separate from this static
  baseline.
- Workspace/Cloud/YouTube/Marketing modules currently have package placeholders;
  deeper file movement must preserve the locked counts.
- Approval actions are contract-gated, but not all have final production API
  execution adapters.

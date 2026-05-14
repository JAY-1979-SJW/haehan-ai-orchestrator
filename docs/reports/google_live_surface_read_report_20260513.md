# Google Live Surface Read Report - 2026-05-13

## Scope

Read-only live verification after Google login. No write, publish, create,
delete, upload, prompt submit, API key creation, release, IAM, billing, or
indexing action was executed.

## Session

- Credential source: `data/credentials.json` through `scripts.credentials`
- Password handling: encrypted at rest, not printed
- Login result: successful after 2FA/user-present handling
- Session check: `[ok] logged in`
- CDP: `http://127.0.0.1:9222` responding
- Bot radar: clean on saved snapshots

## Verified Surfaces

| Surface | Result | Read-only findings |
| --- | --- | --- |
| Google Home | reached | Search box, Google apps, login/account links, AI mode button detected |
| Google Account | reached | Account home reached after login; security/login surface detected |
| Android Developers | reached | Public docs/search surface; Android Studio download and Play Console links detected |
| YouTube | reached | Home/search surface detected |
| YouTube Studio | reached | Channel dashboard reached; dashboard/content/analytics/community/subtitles/monetization/customization links detected |
| Google Cloud Console | reached | Project `haehan-ai` visible; API, IAM, billing, compute, storage, BigQuery links detected |
| Google AI Studio | reached | New chat surface reached; prompt input, Get API key, model/app/gallery controls detected |
| Play Console | reached | Developer/account selector surface detected |
| Firebase Console | reached | Project setup, AI sample, Gemini, Cloud Shell/help controls detected |
| Search Console | reached | Property `haehan-ai.kr` reached; URL inspection, pages, sitemaps, removals, settings detected |
| Gemini | reached | Prompt textbox, model selector, upload/tools, microphone controls detected |
| Gmail | reached | Inbox/search/compose/label/navigation controls detected; full private snapshot intentionally skipped |
| Google Drive | reached | Home/search/new/filter/layout/details controls detected; full private snapshot intentionally skipped |
| Google Calendar | reached | Today view/search/create/calendar selector controls detected; event detail capture skipped |
| Google Docs | reached | Search/template/gallery/open/sort/filter controls detected |
| Google Sheets | reached | Search/template/gallery/open/sort/filter controls detected |

## Approval Gates

The following controls are present and must remain blocked unless a separate
dry-run and explicit approval exist:

- YouTube Studio: upload video, start live stream, create post, channel edits
- Cloud Console: Gemini API key, VM creation, app deploy, storage bucket,
  IAM, billing, API/service changes
- AI Studio/Gemini: prompt submission, API key creation, generated outputs
- Play Console: app release, listing, pricing, users, policy changes
- Firebase: project creation, deploy/config/rules/key changes
- Search Console: URL inspection submission, indexing, removals, sitemap
  submission, property settings
- Gmail/Drive/Calendar/Docs/Sheets: send, delete, share, edit, create,
  upload/download/export, calendar mutation

## Artifacts

- Catalog: `data/google_surface_catalog_latest.json`
- Studio snapshot: `data/manual_visits/studio.youtube.com/channel_UCGu2vJG4a9udIej9ef48suw__20260513_060913.json`
- Cloud Console snapshot: `data/manual_visits/console.cloud.google.com/welcome_pli_1_project_haehan-ai__20260513_060957.json`
- AI Studio snapshot: `data/manual_visits/aistudio.google.com/prompts_new_chat__20260513_061032.json`
- Play Console snapshot: `data/manual_visits/play.google.com/console_developers__20260513_061101.json`
- Firebase snapshot: `data/manual_visits/console.firebase.google.com/root_pli_1__20260513_061158.json`
- Search Console snapshot: `data/manual_visits/search.google.com/search-console_resource_id_sc-domain_haehan-ai.kr__20260513_061258.json`
- Gemini snapshot: `data/manual_visits/gemini.google.com/app__20260513_061353.json`

## Next Work

1. Keep Google workspace operations API-first where official APIs exist.
2. Build per-surface action catalogs before any write-capable workflow.
3. Require dry-run evidence and approval text for every state-changing action.
4. Fix stale CDP daemon state separately; live CDP is currently usable but the
   daemon state file still reports inactive.

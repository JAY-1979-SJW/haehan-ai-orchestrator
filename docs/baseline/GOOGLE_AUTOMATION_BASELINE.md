# HAEHAN Google Automation Baseline

Status: LOCKED
Baseline ID: GOOGLE-AUTOMATION-BASELINE-01
Approved by: user approval in current Codex session
Baseline HEAD: c2307e8ffe9d38d6842a542c7be68efe5f234b09
Last updated: 2026-05-26

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
- Live input supported approval actions: 46
- Prepare/open-only approval actions: 0
- Production final execution blocked: 46
- Host normalization warnings: 0
- Live logic surfaces: 50

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

### 3.1 Google Connection Sequence Lock

All Google browser/OAuth work must start from the Google primary entry and move
in order. Directly opening a Google subdomain, Google OAuth URL, YouTube Studio,
or Cloud Console URL without this sequence is a runtime error and must be logged
before retry.

Locked sequence:

1. Open Google Home: `https://www.google.com/`.
2. Check account state through `https://myaccount.google.com/` using only
   non-secret indicators.
3. Open the requested registered Google subdomain in the same local browser
   profile.
4. Open approval/OAuth URLs only after steps 1-3 have been verified.

Runtime rules:

- The browser profile must be the managed local-agent/CDP profile when screen
  or tab verification is required.
- OS/default browser openers are forbidden for Google/YouTube Console, OAuth,
  approval, and setup flows. Do not use `Start-Process <url>`,
  `webbrowser.open`, `os.startfile`, Explorer URL opens, or shell URL opens for
  these flows. The only allowed browser opener is the managed local-agent/CDP
  path (`python scripts/cdp_daemon.py start` plus `python scripts/cdp_client.py
  goto ...` or a Google router command backed by `scripts.web_connector`).
- The locked Google Console OAuth helper command is:
  `python scripts/cdp_client.py google console youtube-oauth-open`. Use
  `--dry-run` for preflight. This command opens Google Home, Google Account,
  then Cloud Console Credentials in the same managed CDP profile.
- If a URL is opened in a normal browser window and CDP cannot inspect it, record
  `OAUTH_WINDOW_OPENED_OUTSIDE_CDP`, close or ignore that tab, and retry through
  the locked sequence.
- If Playwright cannot attach because of Windows permission errors, record
  `PLAYWRIGHT_PROCESS_PERMISSION_DENIED` and use the direct Chrome DevTools HTTP
  API only for read-only tab open/status checks.
- OAuth helper URLs must use a registered redirect URI. The final YouTube
  captions OAuth baseline is server-first: Google Console must register the
  web callback `https://haehan-ai.kr/orchestrator/api/v1/oauth/youtube/callback`
  and the server must keep client JSON and authorized-user token files outside
  Git. Local loopback redirect `http://127.0.0.1:8765/oauth2callback` is a
  development fallback only, not the final operating baseline. OOB redirect
  `urn:ietf:wg:oauth:2.0:oob` is not the runtime baseline.
- Do not proceed from Google Home to OAuth unless the target subdomain is
  registered and the operation remains read-only or approval-gated.
- This sequence and OAuth-client matching rule is common SSO policy, not a
  YouTube-only workaround. Other Google services must not use the older direct
  OAuth-entry pattern.
- A web-app OAuth client must be used only with its registered web callback
  URI and declared scopes. For YouTube caption read/list/download, the locked
  final target is the server web OAuth client and scope
  `https://www.googleapis.com/auth/youtube.force-ssl`. Desktop app OAuth JSON
  may be used only for isolated local development checks and must not be
  presented as the final server result.
- For Google Console setup screens, the agent may enter non-secret setup values
  such as application type, client name, and redirect URI when CDP can inspect
  the page. The agent must stop before the final Google Console Create/Save
  button so the user only needs to press the final visible approval button. If
  CDP cannot inspect the page, the agent must stop and report
  `GOOGLE_CONSOLE_NOT_INSPECTABLE` instead of handing the whole flow back as a
  manual implementation path.
- The current YouTube server OAuth setup uses `final_approval_only` mode. The
  agent must not stop to ask whether the user wants intermediate/manual
  implementation choices; it prepares the non-secret inputs, opens the managed
  console, fills the OAuth setup fields, and then stops before the final
  Create/Save button. After the user clicks the final button, the agent handles
  the issued client JSON and server token flow through approved secret storage.
  The user handles only Google login/MFA and the final visible approval button.
- User-specific Google/YouTube client JSON, OAuth tokens, API keys, and other
  secret values may be placed by the user or an approved local-agent step into
  the local OS user secret store. The runtime reference format is
  `local-secret://<kind>/<name>`; for YouTube OAuth client JSON the locked
  reference is `local-secret://youtube/oauth_client_json`. The agent may verify
  presence and use the reference for OAuth preparation, but must not print,
  log, commit, or include the raw secret value in reports. If the OS keyring is
  unavailable, the flow must stop and report `keyring_unavailable`.

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
- `scripts/google/subdomain_logic.py`: host-level read and approval boundary.
- `scripts/google/tab_logic.py`: app-attachable tab-level logic and user guidance.
- `scripts/google/live_surface_explorer.py`: direct-CDP read-only live evidence for all 50 surfaces.
- `scripts/google/cloud/live_console_explorer.py`: direct-CDP read-only Cloud Console evidence.
- `scripts/google/live_inputs.py`: live input coverage and no-final-submit policy.
- `scripts/google/managed_console.py`: managed-CDP-only Google Console/OAuth
  entrypoint; default browser openers are forbidden.
- `python scripts/cdp_client.py google work undeveloped`: required Google gap
  report for separating implemented read-only work, no-final-submit input
  support, prepare/open-only items, and production final-execution blocks.
- `tests/test_google_tab_registry.py`: tab, host, count, and owner-package contract.
- `tests/test_google_subdomain_logic.py`: host-level execution boundary contract.
- `tests/test_google_tab_logic.py`: tab-level execution boundary and UI guidance contract.
- `tests/test_google_live_surface_explorer.py`: 50-surface live-logic contract.
- `tests/test_google_cloud_live_console_explorer.py`: Cloud Console live-logic contract.

## 7. Required Verification

Minimum verification before committing Google work:

```text
python -m py_compile scripts/google/auth.py scripts/google/tab_registry.py scripts/google/surfaces.py scripts/google/workflows.py scripts/google/live_inputs.py scripts/google/subdomain_logic.py scripts/google/tab_logic.py scripts/google/live_surface_explorer.py scripts/google/cloud/live_console_explorer.py
python -m py_compile scripts/google/managed_console.py
python -m pytest tests/test_google_tab_registry.py tests/test_google_site_engine.py tests/test_google_surfaces.py tests/test_google_workflows.py tests/test_google_user_present_session_auth.py tests/test_youtube_site_engine.py tests/test_youtube_workflow.py tests/test_google_subdomain_logic.py tests/test_google_tab_logic.py tests/test_google_live_surface_explorer.py tests/test_google_cloud_live_console_explorer.py tests/test_google_managed_console.py -q
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
- Workspace, Cloud, YouTube, Marketing, AI, Developer, and Media expose common
  app-attachable tab logic; deeper file movement must preserve the locked counts.
- Approval actions are contract-gated, but not all have final production API
  execution adapters.
- Current undeveloped-work baseline: 0 approval actions are prepare/open-only,
  all 46 approval actions support either a surface-specific or generic live
  input handoff with `--no-final-submit`, and all 46 approval actions remain
  blocked from agent final execution until a separate production adapter is
  explicitly approved.

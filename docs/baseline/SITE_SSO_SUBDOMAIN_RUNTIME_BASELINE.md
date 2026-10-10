# HAEHAN Site SSO Subdomain Runtime Baseline

Status: LOCKED
Baseline ID: SITE-SSO-SUBDOMAIN-RUNTIME-BASELINE-01
Approved by: user approval in current Codex session
Baseline HEAD: 45d10852a3ba8756ecb11c5cdcec8a5ad4da8ac2
Last updated: 2026-05-26

## 1. Purpose

This baseline standardizes how large portal sites with many subdomains are
handled. Google, Naver, and similar providers must use the same runtime model:
one user-present login in a local browser profile, then read-only checks across
approved subdomains and services.

This baseline does not approve automatic login, credential replay, cookie
export, session export, or write actions.

Google subdomain-specific feature logic is implemented in
`scripts/google/common/subdomain_logic.py`. It converts the locked Google surface and
workflow catalogs into host-level read and approval boundaries without
performing credential entry or exporting session material.
Google tab-level feature logic is implemented in `scripts/google/common/tab_logic.py`
and exposed through all nine Google tab packages.

## 1.1 Occasional Site Login Handoff

For sites that are used only once or infrequently, a developed site module is not required before login assistance.
The allowed mode is an occasional-site login handoff:

- open the approved entry URL in the local-agent browser with
  `web_open_url_readonly`
- the user enters credentials directly
- auto login and credential replay remain false
- the agent may perform only a read-only session check using non-secret page
  indicators
- cookies, sessions, tokens, passwords, OTPs, Authorization headers, and raw
  page content must not be exported
- no state-changing work is allowed after login unless the user separately
  approves the final action
- if the site becomes repeated or business-critical, it must be promoted to a
  registered site module before broader automation is added

## 2. Universal Flow

All SSO providers must follow this flow:

1. Open the provider's primary login entry in a local browser profile.
2. The user completes login manually.
3. The app verifies only non-secret state: host, title, visible account/login
   indicators, and whether the service page is reachable.
4. The same local browser profile is reused for subdomain navigation.
5. Subdomain and service checks are read-only by default.
6. Write, create, delete, purchase, publish, send, deploy, IAM, billing, secret,
   or credential actions require a separate approval flow and final execution
   gate.

Common connection lock:

- direct OAuth URL entry is forbidden before the provider primary entry,
  account-state check, and target registered subdomain check are complete
- failed direct OAuth entry must be recorded as
  `SSO_DIRECT_OAUTH_ENTRY_BLOCKED` before retry
- browser/OAuth work that requires screen or tab verification must use the
  managed local-agent/CDP browser profile
- if Playwright attachment fails, use direct Chrome DevTools HTTP API only for
  read-only open/status checks and record the failure

Common OAuth client lock:

- OAuth client type must match the runtime that is executing the flow
- redirect URI must match the URI registered on that OAuth client
- requested scope must match the declared workflow and consent setup
- web-app OAuth clients must not be reused for local CLI token exchange unless
  the web client explicitly has a matching local redirect URI and scope
- local CLI/API token exchange should use a Desktop app OAuth client JSON
- the agent may prefill non-secret fields such as app type, display name,
  callback URI, scope label, and description when the target page is observable
  through the managed browser runtime
- if the target page is not observable, the agent must request or provide the
  exact input values and wait for the user to enter them
- final external create, save, submit, publish, grant, billing, IAM, or
  credential-generation actions must remain user-direct unless a separate
  explicit final-execution approval gate exists
- mismatches must be recorded as `OAUTH_CLIENT_REDIRECT_SCOPE_MISMATCH`

## 3. Locked Providers

The initial locked SSO providers are:

- `google`
- `naver`

## 4. Provider Login Entries

Google:

- primary host: `google.com`
- login entry: `https://www.google.com/`
- account entry: `https://myaccount.google.com/`
- login policy: `user_present_sso_profile`
- connection sequence lock:
  1. `https://www.google.com/`
  2. `https://myaccount.google.com/`
  3. requested registered Google subdomain in the same browser profile
  4. approval/OAuth URL only after the first three steps are verified
- direct OAuth/subdomain entry before Google Home is a runtime error and must be
  recorded before retry
- YouTube/local API token work must use a Desktop app OAuth client unless the
  existing web-app client has an explicitly matching redirect URI and scope

Naver:

- primary host: `naver.com`
- login entry: `https://www.naver.com/`
- account entry: `https://nid.naver.com/`
- login policy: `user_present_sso_profile`

## 5. Locked Subdomain Services

Google services:

- `google_home`: `www.google.com`
- `google_account`: `myaccount.google.com`
- `gmail`: `mail.google.com`
- `drive`: `drive.google.com`
- `calendar`: `calendar.google.com`
- `docs`: `docs.google.com`
- `cloud_console`: `console.cloud.google.com`
- `youtube`: `www.youtube.com`
- `youtube_studio`: `studio.youtube.com`
- `search_console`: `search.google.com`
- `ai_studio`: `aistudio.google.com`
- `gemini`: `gemini.google.com`

Naver services:

- `naver_home`: `www.naver.com`
- `naver_login`: `nid.naver.com`
- `naver_mail`: `mail.naver.com`
- `naver_cafe`: `cafe.naver.com`
- `naver_blog`: `blog.naver.com`
- `naver_mybox`: `mybox.naver.com`
- `naver_calendar`: `calendar.naver.com`
- `naver_pay`: `new-m.pay.naver.com`
- `naver_smartstore`: `smartstore.naver.com`
- `naver_search_advisor`: `searchadvisor.naver.com`
- `naver_place`: `new.smartplace.naver.com`

## 6. Runtime Contract

The shared runtime contract is:

- provider id must be registered
- service id must be registered under that provider
- navigation must use `web_open_url_readonly`
- execution location must be `local_agent`
- risk level must be `read`
- auto login must be false
- user-present login must be true
- shared profile must be true
- same-profile subdomain navigation must be true
- raw cookies, sessions, tokens, passwords, OTPs, Authorization headers, and
  secret values must not be returned
- blocked actions must not create local-agent tasks

Google subdomain feature logic must also enforce:

- `login`, `signin`, and account entry operations return a user-present login
  entry task only; auto-login and credential replay stay false
- read/open/status/inspect operations create only `web_open_url_readonly`
  local-agent tasks
- send, publish, upload, billing, IAM, deploy, secret, credential, delete, and
  other state-changing operations return an approval-gate result without a
  local-agent execution task
- unknown Google subdomains fail closed before execution
- tab-level logic must expose `summary()`, `catalog()`, and
  `classify_operation(...)` for every locked Google tab
- hosts outside the requested Google tab must fail closed

## 7. Forbidden Behavior

The following are forbidden in this baseline:

- automatic username/password entry
- credential replay
- cookie export
- session export
- localStorage or sessionStorage export
- token or Authorization header output
- cross-provider profile mixing
- write, create, delete, publish, send, purchase, billing, IAM, deploy, or
  secret-value actions without a separate approval gate

## 8. Required Verification

Minimum verification:

```text
python tools/audits/app/audit_site_sso_subdomain_runtime_baseline.py
python -m pytest tests/test_site_sso_subdomain_runtime.py tests/test_google_subdomain_logic.py tests/test_google_tab_logic.py -q
python tools/quality/module_quality_gate.py --module repo_guard
```

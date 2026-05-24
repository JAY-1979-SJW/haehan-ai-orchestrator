# HAEHAN Site SSO Subdomain Runtime Baseline

Status: LOCKED
Baseline ID: SITE-SSO-SUBDOMAIN-RUNTIME-BASELINE-01
Approved by: user approval in current Codex session
Baseline HEAD: 45d10852a3ba8756ecb11c5cdcec8a5ad4da8ac2
Last updated: 2026-05-24

## 1. Purpose

This baseline standardizes how large portal sites with many subdomains are
handled. Google, Naver, and similar providers must use the same runtime model:
one user-present login in a local browser profile, then read-only checks across
approved subdomains and services.

This baseline does not approve automatic login, credential replay, cookie
export, session export, or write actions.

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
python scripts/ops/audit_site_sso_subdomain_runtime_baseline.py
python -m pytest tests/test_site_sso_subdomain_runtime.py -q
python scripts/module_quality_gate.py --module repo_guard
```


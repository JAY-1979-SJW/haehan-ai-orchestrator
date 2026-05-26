# YouTube OAuth Root Cause Analysis - 2026-05-25

## Verdict

The repeated OAuth block is not only a local browser problem. The confirmed
Google error is `redirect_uri_mismatch`, and the current evidence shows an
input/client mismatch:

- Existing OAuth client type: Web application
- Existing authorized redirect URI:
  `https://attendance.haehan-ai.kr/api/auth/callback/google`
- OAuth helper generated redirect URIs during the failed attempts:
  - `urn:ietf:wg:oauth:2.0:oob`
  - `http://127.0.0.1:8765/oauth2callback`
- Existing app Google login scope: `openid email profile`
- YouTube API token attempt scope:
  `https://www.googleapis.com/auth/youtube.readonly`

## Findings

1. `WinError 5` is a local Playwright transport failure.
   It prevented `cdp_client.py goto` from attaching through Playwright, but the
   direct Chrome DevTools HTTP API successfully opened Google tabs afterward.

2. The Google OAuth block remains after bypassing Playwright.
   That means `WinError 5` is not the final OAuth blocker.

3. The existing credentials belong to the construction attendance web app.
   Its recorded redirect URI is
   `https://attendance.haehan-ai.kr/api/auth/callback/google`.

4. The OAuth helper used a local CLI redirect URI against a web-app client.
   This is an input mismatch and triggers Google `redirect_uri_mismatch`.

5. The requested YouTube readonly scope is outside the existing Google login
   baseline, which uses `openid email profile`.
   YouTube Data API access should use a dedicated OAuth client/scope path or be
   explicitly added to the existing app's OAuth consent and callback flow.

## Corrective Action

Use one of these paths:

1. Dedicated local YouTube token path:
   Create or provide a Desktop app OAuth client JSON and use it for
   `youtube.readonly`.

2. Existing web-app path:
   Generate OAuth through the app's registered callback
   `https://attendance.haehan-ai.kr/api/auth/callback/google`, and handle the
   returned Google token inside that web app flow.

3. Web client plus local callback path:
   Add `http://127.0.0.1:8765/oauth2callback` to the web client's authorized
   redirect URIs and add the YouTube readonly scope to the consent setup.

## Runtime Rule Update

Do not reuse a web-app OAuth client for local CLI token exchange unless the
redirect URI and requested scopes match the registered Google Cloud Console
configuration.

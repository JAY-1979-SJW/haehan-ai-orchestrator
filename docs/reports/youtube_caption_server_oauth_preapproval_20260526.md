# YouTube Caption Server OAuth Preapproval

Status: ready_for_user_console_approval
Final location: server
User approval mode: final approval only
Date: 2026-05-26

## Locked Console Inputs

These values are the server-first baseline for YouTube caption list/download
through the official YouTube Data API.

| Field | Value |
| --- | --- |
| Google Cloud project | `haehan-ai` |
| API | `YouTube Data API v3` |
| Credential type | `OAuth client ID` |
| Application type | `Web application` |
| OAuth client name | `haehan-youtube-server-captions` |
| Authorized redirect URI | `https://haehan-ai.kr/orchestrator/api/v1/oauth/youtube/callback` |
| Scope | `https://www.googleapis.com/auth/youtube.force-ssl` |

## Server Placement

| Item | Server path |
| --- | --- |
| OAuth client JSON mounted in runtime | `/run/secrets/api/youtube_oauth_client.json` |
| Authorized-user token file | `/app/ai_orchestrator/storage/secrets/youtube_oauth_authorized_user.json` |

The client JSON, access token, refresh token, and authorization code must never
be committed to Git or printed in reports.

## Server Environment

```env
YOUTUBE_CLIENT_SECRETS_FILE=/run/secrets/api/youtube_oauth_client.json
YOUTUBE_OAUTH_REDIRECT_URI=https://haehan-ai.kr/orchestrator/api/v1/oauth/youtube/callback
YOUTUBE_OAUTH_TOKEN_FILE=/app/ai_orchestrator/storage/secrets/youtube_oauth_authorized_user.json
YOUTUBE_OAUTH_CALLBACK_EXCHANGE_ENABLED=true
```

Optional user-local secret reference:

```text
YOUTUBE_CLIENT_SECRETS_FILE=local-secret://youtube/oauth_client_json
YOUTUBE_CLIENT_SECRETS_REF=local-secret://youtube/oauth_client_json
```

The local secret reference points to the current Windows/OS user keyring entry.
It may be used after the user approves storing the Google OAuth client JSON
locally. Reports and command output must show only the reference, not the raw
client JSON, client secret, token, or authorization code.

Local user secret commands:

```powershell
python scripts/local_user_secret_store.py put-file youtube oauth_client_json <downloaded_oauth_client_json>
python scripts/local_user_secret_store.py status youtube oauth_client_json
```

## Post-Approval Commands

Run these on the server after the user creates/saves the Google Console OAuth
client and places the downloaded client JSON in the server secret path.

```bash
python scripts/cdp_client.py youtube oauth start scope=force-ssl client_file=/run/secrets/api/youtube_oauth_client.json redirect_uri=https://haehan-ai.kr/orchestrator/api/v1/oauth/youtube/callback
python scripts/cdp_client.py youtube oauth exchange code=<returned_code> client_file=/run/secrets/api/youtube_oauth_client.json redirect_uri=https://haehan-ai.kr/orchestrator/api/v1/oauth/youtube/callback output=/app/ai_orchestrator/storage/secrets/youtube_oauth_authorized_user.json
python scripts/cdp_client.py youtube research caption-list video_id=<owned_or_authorized_video_id> token_file=/app/ai_orchestrator/storage/secrets/youtube_oauth_authorized_user.json
```

## Approval Boundary

This is the final-approval-only version. The agent prepares exact input values,
non-secret command lines, and redacted reports without asking the user to choose
between intermediate implementation paths. The user performs only the final
Google Console Create/Save action and any Google OAuth consent approval.

If the server callback endpoint is not reachable from Google, stop and report
that as a server route/deploy issue before attempting token exchange.

## Server Callback

The server callback route is:

```text
GET /api/v1/oauth/youtube/callback
```

The public deployment path is:

```text
https://haehan-ai.kr/orchestrator/api/v1/oauth/youtube/callback
```

The callback never returns raw authorization codes or OAuth tokens. When
`YOUTUBE_OAUTH_CALLBACK_EXCHANGE_ENABLED=true` is configured on the server, the
callback may exchange the returned code after the user's final Google consent
and write the authorized-user token to the configured server token file.

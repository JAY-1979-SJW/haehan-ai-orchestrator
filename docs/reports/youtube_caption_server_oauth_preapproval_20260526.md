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

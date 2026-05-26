# Google Desktop OAuth Client Preapproval - 2026-05-25

## Purpose

Prepare a dedicated Desktop app OAuth client for local YouTube Data API read
work. This replaces the failed attempt to reuse the attendance web-app OAuth
client for local CLI token exchange.

## Locked Input Values

- Google Cloud project: `haehan-ai`
- Console page: `https://console.cloud.google.com/apis/credentials?project=haehan-ai`
- Credential type: `OAuth client ID`
- Application type: `Desktop app`
- Client name: `haehan-youtube-local`
- Intended scope for token flow:
  `https://www.googleapis.com/auth/youtube.readonly`
- Output file expected after approval/download: `client_secret_*.json`

## User Approval Boundary

The user should approve only this final external state change:

- Create the Desktop app OAuth client in Google Cloud Console.

After creation, download the JSON client file. The agent can then run:

```powershell
python scripts\cdp_client.py youtube oauth start scope=readonly client_file=<downloaded-client-secret-json>
python scripts\cdp_client.py youtube oauth exchange code=<returned-code> client_file=<downloaded-client-secret-json>
python scripts\cdp_client.py youtube research caption-list video_id=<video-id> token_file=data\secrets\youtube_oauth_authorized_user.json
```

## Current Automation Block

Automatic form filling was not completed because the Google Cloud Console page
target stopped responding to CDP `Runtime.evaluate` and `Page.captureScreenshot`.
Proceeding with blind coordinate or keyboard input would risk creating the wrong
credential in the wrong project.

Recorded blocker:

- `GOOGLE_CONSOLE_CDP_TARGET_UNRESPONSIVE`

## Common Rule

For Google/SSO work, do not bypass the managed connection sequence and do not
reuse a web-app OAuth client for local CLI token exchange. Use a Desktop app
OAuth client JSON for local YouTube API work.

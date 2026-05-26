# YouTube OAuth Managed Browser Open Lock

Status: locked
Date: 2026-05-26

Google Console and YouTube OAuth approval preparation must not open the OS
default browser. The locked opener is the managed local-agent/CDP profile.

Allowed command:

```powershell
python scripts/cdp_client.py google console youtube-oauth-open
```

Preflight command:

```powershell
python scripts/cdp_client.py google console youtube-oauth-open --dry-run
```

Locked order:

1. `https://www.google.com/`
2. `https://myaccount.google.com/`
3. `https://console.cloud.google.com/apis/credentials`

The agent may enter non-secret setup values only when the managed CDP page is
inspectable. The final Google Console Create/Save and OAuth consent actions
remain user-only.

Regression check:

```powershell
python -m pytest tests/test_google_managed_console.py tests/test_google_subdomain_logic.py tests/test_youtube_oauth.py -q
```

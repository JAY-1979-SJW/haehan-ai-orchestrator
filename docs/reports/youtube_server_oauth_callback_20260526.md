# YouTube Server OAuth Callback

Status: completed
Date: 2026-05-26
Final location: server

## Scope

Added the server callback route for YouTube caption OAuth.

## Route

```text
GET /api/v1/oauth/youtube/callback
```

Public server URL:

```text
https://haehan-ai.kr/orchestrator/api/v1/oauth/youtube/callback
```

## Safety Boundary

- Raw authorization code is never returned in the HTTP response.
- OAuth tokens are never returned in the HTTP response.
- Default behavior is code-received reporting only.
- Server token exchange runs only when
  `YOUTUBE_OAUTH_CALLBACK_EXCHANGE_ENABLED=true` is configured.
- Token file output remains the configured server secret path.

## Verification

- `python -m pytest tests\test_youtube_oauth.py tests\test_youtube_oauth_callback_route.py tests\test_youtube_research.py -q`
- `python -m py_compile scripts\youtube\oauth.py ai_orchestrator/routers/youtube_oauth_router.py ai_orchestrator\router.py`

"""Low-level YouTube Data API HTTP helpers (L3 connector).

Shared by scripts/youtube/research.py and scripts/google/youtube/search.py.
No business logic here — only transport, auth resolution, and proxy fallback.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from scripts.common.http_retry import urlopen_with_dead_proxy_fallback

# ── API key ───────────────────────────────────────────────────────────────────


def api_key(explicit: str | None = None) -> str:
    """Return the best available YouTube Data API key."""
    return (
        explicit
        or os.environ.get("YOUTUBE_DATA_API_KEY", "")
        or os.environ.get("YOUTUBE_API_KEY", "")
        or os.environ.get("GOOGLE_YOUTUBE_API_KEY", "")
    )


# ── OAuth token helpers ───────────────────────────────────────────────────────

_DEFAULT_TOKEN_PATH = (
    Path(__file__).resolve().parents[2]
    / "ai_orchestrator"
    / "storage"
    / "secrets"
    / "youtube_oauth_authorized_user.json"
)


def refresh_oauth_token(parsed: dict[str, Any]) -> str:
    """Exchange a refresh token for a fresh access token. Returns "" on failure."""
    refresh = str(parsed.get("refresh_token") or "")
    client_id = str(parsed.get("client_id") or "")
    client_secret = str(parsed.get("client_secret") or "")
    token_uri = str(parsed.get("token_uri") or "https://oauth2.googleapis.com/token")
    if not refresh or not client_id or not client_secret:
        return ""
    encoded = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh,
            "grant_type": "refresh_token",
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        token_uri,
        data=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return str(json.loads(r.read().decode("utf-8")).get("access_token") or "")
    except Exception:  # noqa: BLE001 - OAuth 토큰 교환 실패 시 빈 문자열을 반환하는 안전한 기본값 — 호출부에서 빈 토큰을 유효하지 않은 토큰으로 취급.
        return ""


def oauth_token(
    explicit: str | None = None,
    token_file: str | Path | None = None,
) -> str:
    """Resolve an OAuth access token from explicit value, env var, or token file."""
    if explicit:
        return explicit
    env = os.environ.get("YOUTUBE_OAUTH_ACCESS_TOKEN", "") or os.environ.get("GOOGLE_YOUTUBE_OAUTH_ACCESS_TOKEN", "")
    if env:
        return env
    # 명시적 token_file > 환경변수 > 기본 경로
    path = Path(token_file or os.environ.get("YOUTUBE_OAUTH_TOKEN_FILE", "") or _DEFAULT_TOKEN_PATH)
    if not path.exists():
        return ""
    raw = path.read_text(encoding="utf-8", errors="replace").strip()
    if not raw:
        return ""
    if raw.startswith("{"):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return ""
        refreshed = refresh_oauth_token(parsed)
        if refreshed:
            return refreshed
        return str(parsed.get("access_token") or parsed.get("token") or "")
    return raw


# ── HTTP transport ────────────────────────────────────────────────────────────
# urlopen_with_dead_proxy_fallback 는 scripts/common/http_retry.py 로 옮겼다(위 import 로 재노출, __all__ 유지).


# ── JSON / text fetchers ──────────────────────────────────────────────────────


def get_json(
    url: str,
    params: dict[str, str | int],
    *,
    token: str | None = None,
    timeout: int = 20,
) -> dict[str, Any]:
    """GET JSON from url+params. Pass token for Bearer auth."""
    query = urllib.parse.urlencode(params)
    headers: dict[str, str] = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(f"{url}?{query}", headers=headers)
    with urlopen_with_dead_proxy_fallback(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def get_text(
    url: str,
    params: dict[str, str | int],
    *,
    token: str,
    timeout: int = 20,
) -> str:
    """GET plain/vtt/srt text with Bearer auth."""
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{url}?{query}",
        headers={
            "Accept": "text/plain,text/vtt,application/x-subrip,*/*",
            "Authorization": f"Bearer {token}",
        },
    )
    with urlopen_with_dead_proxy_fallback(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


__all__ = [
    "api_key",
    "get_json",
    "get_text",
    "oauth_token",
    "refresh_oauth_token",
    "urlopen_with_dead_proxy_fallback",
]

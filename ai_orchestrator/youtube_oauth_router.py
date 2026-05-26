"""Server-side YouTube OAuth callback routes."""
from __future__ import annotations

from fastapi import APIRouter, Query

from scripts.youtube import oauth


youtube_oauth_router = APIRouter(prefix="/oauth/youtube", tags=["youtube-oauth"])


@youtube_oauth_router.get("/callback")
def youtube_oauth_callback(
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
):
    """Receive Google OAuth callback without exposing raw code or token values."""
    result, path = oauth.handle_server_callback({"code": code, "state": state, "error": error})
    return {
        "ok": result.get("status") == "ok",
        "status": result.get("status"),
        "reason": result.get("reason", ""),
        "code_received": bool(result.get("code_received")),
        "code_output": "redacted",
        "token_output": "redacted",
        "next_step": result.get("next_step", ""),
        "report_path": str(path),
    }

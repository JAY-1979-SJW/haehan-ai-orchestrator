"""YouTube OAuth 콜백 + 인증 관리 라우트."""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request

from fastapi import APIRouter, Depends, Query

from scripts.youtube import oauth as _oauth_svc
from tools.gates.auth import require_role

from ._helpers import token_path

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/callback")
def youtube_oauth_callback(
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
):
    """Google OAuth 콜백 — code 수신 후 토큰 교환."""
    result, path = _oauth_svc.handle_server_callback({"code": code, "state": state, "error": error})
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


@router.get("/auth-url")
def youtube_oauth_auth_url(
    scope: str = Query(default="force-ssl upload"),
    user: dict = Depends(require_role("admin", "owner")),
):
    """YouTube OAuth 인증 URL 생성 — 브라우저에서 열어 Google 계정 승인."""
    result, _ = _oauth_svc.build_auth_plan({"scope": scope})
    return {
        "ok": result.get("status") == "ready_for_user_approval",
        "auth_url": result.get("auth_url", ""),
        "scope": result.get("scope", ""),
        "redirect_uri": result.get("redirect_uri", ""),
        "status": result.get("status"),
        "reason": result.get("reason", ""),
    }


@router.get("/status")
def youtube_oauth_status(user: dict = Depends(require_role("admin", "owner"))):
    """현재 저장된 YouTube OAuth 토큰 상태 확인."""
    p = token_path()
    if not p:
        return {"ok": False, "status": "no_token", "scopes": [], "has_upload_scope": False}

    try:
        t = json.loads(p.read_text(encoding="utf-8"))
        scopes = t.get("scopes", [])
        has_upload = "https://www.googleapis.com/auth/youtube.upload" in scopes

        data = urllib.parse.urlencode(
            {
                "client_id": t["client_id"],
                "client_secret": t["client_secret"],
                "refresh_token": t["refresh_token"],
                "grant_type": "refresh_token",
            }
        ).encode()
        req = urllib.request.Request(  # noqa: S310
            t.get("token_uri", "https://oauth2.googleapis.com/token"),
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        access = json.loads(urllib.request.urlopen(req, timeout=10).read()).get("access_token", "")  # noqa: S310

        channel: dict = {}
        if access:
            req2 = urllib.request.Request(
                "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true&maxResults=1",
                headers={"Authorization": f"Bearer {access}"},
            )
            try:
                d = json.loads(urllib.request.urlopen(req2, timeout=10).read())  # noqa: S310
                items = d.get("items", [])
                if items:
                    channel = {"title": items[0]["snippet"]["title"], "id": items[0]["id"]}
            except Exception as exc:  # noqa: BLE001
                logger.debug("YouTube 채널 정보 조회 실패: %s", type(exc).__name__)
                pass

        return {
            "ok": True,
            "status": "active",
            "scopes": scopes,
            "has_upload_scope": has_upload,
            "channel": channel,
        }
    except Exception as e:  # noqa: BLE001 - YouTube OAuth 토큰 상태 확인 -- 실패 시 상태값만 반환(token_error), 에러 메시지 100자로 절단해 토큰/시크릿 값 자체는 노출하지 않음
        logger.warning("YouTube OAuth 토큰 상태 확인 실패: %s", type(e).__name__)
        return {"ok": False, "status": "token_error", "error": str(e)[:100], "scopes": []}

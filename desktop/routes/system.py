"""/health, /logs, /whoami, /app-new, /proxy/admin 시스템 라우트."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import Response

logger = logging.getLogger(__name__)

router = APIRouter()

_LOG_FILE = Path(__file__).parent.parent.parent / "data" / "logs" / "app.log"
_LOG_MAX_LINES = 500
_WHOAMI_KNOWN_ROLES = frozenset({"any", "user", "viewer", "admin", "owner"})
_AUTOWORK_BASE = "https://autowork.haehan-ai.kr"
_PROXY_STRIP_HEADERS = {"x-frame-options", "content-security-policy", "content-encoding", "transfer-encoding"}


def _resolve_whoami_role() -> tuple[str, str]:
    import os

    env_role = os.environ.get("HAEHAN_ROLE", "").strip().lower()
    if env_role in _WHOAMI_KNOWN_ROLES:
        return env_role, "env"
    return "any", "default"


@router.get("/health")
async def health_check():
    from desktop.app_config import LOCAL_HOST, LOCAL_PORT

    return {
        "ok": True,
        "service": "haehan-local-server",
        "host": LOCAL_HOST,
        "port": LOCAL_PORT,
        "ts": int(time.time()),
    }


@router.get("/logs")
async def get_logs():
    try:
        if not _LOG_FILE.exists():
            return {"lines": [], "error": "로그 파일 없음"}
        lines = _LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-_LOG_MAX_LINES:]
        return {"lines": lines}
    except Exception as exc:
        logger.warning("logs read error: %s", exc)
        return {"lines": [], "error": str(exc)}


@router.get("/api/v1/whoami")
async def whoami():
    role, source = _resolve_whoami_role()
    return {"ok": True, "role": role, "admin": role in ("admin", "owner"), "source": source}


@router.get("/proxy/admin/{path:path}")
async def proxy_admin(path: str, request: Request) -> Response:
    target = f"{_AUTOWORK_BASE}/{path}"
    if request.url.query:
        target += f"?{request.url.query}"
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            resp = await client.get(target, headers={"Accept": "text/html,application/xhtml+xml,*/*"})
        headers = {k: v for k, v in resp.headers.items() if k.lower() not in _PROXY_STRIP_HEADERS}
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=headers,
            media_type=resp.headers.get("content-type"),
        )
    except Exception as exc:
        logger.warning("proxy error %s: %s", target, exc)
        return Response(content=f"프록시 오류: {exc}".encode(), status_code=502)


@router.get("/app-new")
async def new_shell():
    import json as _json

    from desktop.local_agent_service import local_agent_health as _la_health
    from desktop.local_agent_service import local_agent_preflight as _preflight
    from desktop.ui_new.shell_html import build_html_from_data

    la_health_data = _la_health()
    preflight_data = _preflight()

    try:
        from desktop.tray_runtime import check_registration_status

        reg = check_registration_status()
        agent_data = {
            "ok": reg.registered,
            "agent_id": getattr(reg, "agent_id", ""),
            "server_url": getattr(reg, "server_url", ""),
            "server_connected": getattr(reg, "registered", False),
        }
    except Exception:
        agent_data = {"ok": False, "agent_id": "", "server_connected": False}

    try:
        from desktop.admin_webview import resolve_current_role

        role = resolve_current_role()
    except Exception:
        role = "unknown"

    try:
        log_lines = _LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-15:]
    except Exception:
        log_lines = []

    data = {
        "health": {"ok": True, "service": "haehan-local-server", "ts": int(time.time())},
        "agent": agent_data,
        "la_health": la_health_data if isinstance(la_health_data, dict) else la_health_data.__dict__,
        "preflight": (
            preflight_data
            if isinstance(preflight_data, dict)
            else _json.loads(_json.dumps(preflight_data, default=str))
        ),
        "whoami": {"ok": True, "role": role},
        "logs": {"lines": log_lines},
    }
    html = build_html_from_data(data)
    return Response(
        content=html.encode("utf-8"),
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )

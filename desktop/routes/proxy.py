"""/api/v1/{path} CAD 원격 프록시 + SPA fallback + 정적 파일 서빙."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import Response

logger = logging.getLogger(__name__)

router = APIRouter()

_CAD_REMOTE_BASE = "https://cad.haehan-ai.kr"
_HOP_BY_HOP = frozenset(
    [
        "host",
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "authorization",
    ]
)


async def _proxy_to_remote(method: str, path: str, request: Request) -> Response:
    url = f"{_CAD_REMOTE_BASE}/api/v1/{path}"
    if request.url.query:
        url += f"?{request.url.query}"
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _HOP_BY_HOP}
    body = await request.body() if method in ("POST", "PUT", "PATCH") else None
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            resp = await c.request(method, url, headers=headers, content=body)
        resp_headers = {k: v for k, v in resp.headers.items() if k.lower() not in _HOP_BY_HOP}
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=resp_headers,
            media_type=resp.headers.get("content-type"),
        )
    except Exception as exc:
        logger.warning("remote proxy error %s %s: %s", method, url, exc)
        return Response(content=b'{"detail":"REMOTE_PROXY_ERROR"}', status_code=502, media_type="application/json")


@router.get("/api/v1/{path:path}")
async def proxy_api_get(path: str, request: Request):
    return await _proxy_to_remote("GET", path, request)


@router.post("/api/v1/{path:path}")
async def proxy_api_post(path: str, request: Request):
    return await _proxy_to_remote("POST", path, request)


@router.put("/api/v1/{path:path}")
async def proxy_api_put(path: str, request: Request):
    return await _proxy_to_remote("PUT", path, request)


@router.delete("/api/v1/{path:path}")
async def proxy_api_delete(path: str, request: Request):
    return await _proxy_to_remote("DELETE", path, request)


def build_spa_router(ui_dir) -> APIRouter:
    """UI 디렉토리를 받아 SPA fallback + index.html 라우터 생성."""
    from pathlib import Path

    _ui_dir = Path(ui_dir)
    spa = APIRouter()

    @spa.get("/")
    @spa.get("/index.html")
    async def serve_index():
        content = (_ui_dir / "index.html").read_bytes()
        return Response(
            content=content,
            media_type="text/html; charset=utf-8",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"},
        )

    @spa.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        import mimetypes

        _API_PREFIXES = ("api/", "cad/", "ws/", "proxy/", "agent/", "local-agent/", "logs", "health")
        if any(full_path == p.rstrip("/") or full_path.startswith(p) for p in _API_PREFIXES):
            return Response(
                content=b'{"detail":"NOT_FOUND","path":"/' + full_path.encode() + b'"}',
                status_code=404,
                media_type="application/json",
            )
        if full_path.startswith("assets/"):
            asset_file = _ui_dir / full_path
            if asset_file.is_file():
                mime, _ = mimetypes.guess_type(str(asset_file))
                return Response(
                    content=asset_file.read_bytes(),
                    media_type=mime or "application/octet-stream",
                    headers={"Cache-Control": "public, max-age=31536000, immutable"},
                )
        index_path = _ui_dir / "index.html"
        if not index_path.exists():
            return Response(content=b"index.html not found", status_code=404)
        return Response(
            content=index_path.read_bytes(),
            media_type="text/html; charset=utf-8",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    return spa

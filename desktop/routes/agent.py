"""에이전트 등록 / 상태 API."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Request

from desktop import agent_runtime_boundary
from desktop._broadcast import broadcast

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/agent/register")
async def agent_register(request: Request):
    """등록 코드로 에이전트를 서버에 등록하고 device_token을 저장."""
    try:
        body = await request.json()
    except Exception:
        return {"ok": False, "error": "요청 파싱 실패"}

    reg_code = (body.get("registration_code") or "").strip()
    server_url = (body.get("server_url") or "https://haehan-ai.kr/orchestrator").strip()
    if not reg_code:
        return {"ok": False, "error": "registration_code 필요"}

    try:
        import platform

        from desktop.ws_server import connect_to_server

        meta, device_token = agent_runtime_boundary.register_with_code(
            server_url=server_url,
            registration_code=reg_code,
            host=platform.node(),
            os_name=platform.system(),
            version="0.1.0",
        )
        agent_runtime_boundary.save_device_token(server_url, meta.agent_id, device_token)
        cfg = agent_runtime_boundary.load_desktop_config()
        cfg.server_url = server_url
        cfg.agent_id = meta.agent_id
        agent_runtime_boundary.save_desktop_config(cfg)
        logger.info("agent registered: agent_id=%s", meta.agent_id)
        await broadcast({"type": "system", "text": f"✅ 등록 완료 — agent_id: {meta.agent_id[:12]}…"})
        asyncio.create_task(connect_to_server())  # noqa: RUF006
        return {"ok": True, "agent_id": meta.agent_id}
    except Exception as exc:
        logger.error("register error: %s", exc)
        return {"ok": False, "error": str(exc)}


@router.get("/agent/status")
async def agent_status():
    """현재 등록된 에이전트 정보 반환 (token 제외)."""
    try:
        from desktop._broadcast import _server_ws as _ws

        cfg = agent_runtime_boundary.load_desktop_config()
        return {
            "ok": True,
            "server_url": cfg.server_url,
            "agent_id": cfg.agent_id,
            "is_complete": cfg.is_complete(),
            "server_connected": _ws is not None,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

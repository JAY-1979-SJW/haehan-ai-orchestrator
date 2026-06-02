"""/ws/ui WebSocket 엔드포인트 + UI 메시지 dispatch."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from . import _broadcast as _state
from ._broadcast import broadcast, send_to_server
from .blog_cafe_actions import (
    run_blog_confirm,
    run_blog_write,
    run_cafe_confirm,
    run_cafe_write,
    run_naver_cafe_list,
    run_naver_cafe_posts,
    run_naver_cafe_read,
)
from .browser_routes import (
    handle_browser_action,
    handle_browser_quit,
    handle_browser_start,
    handle_browser_status,
    handle_screenshot,
    handle_tab_close,
    handle_tab_list,
)
from .login_watcher import start_login_watcher, stop_login_watcher
from .user_settings import load_menu, save_menu

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/ui")
async def ws_ui(ws: WebSocket) -> None:
    await ws.accept()
    _state._ui_clients.append(ws)
    logger.info("UI client connected (total=%d)", len(_state._ui_clients))
    try:
        while True:
            data = await ws.receive_json()
            await _handle_ui_message(data, ws)
    except WebSocketDisconnect:
        pass
    finally:
        if ws in _state._ui_clients:
            _state._ui_clients.remove(ws)
        logger.info("UI client disconnected (total=%d)", len(_state._ui_clients))


async def _handle_ui_message(data: dict, ws: WebSocket) -> None:
    action = data.get("action", "")

    if action == "load_menu":
        menu = load_menu(data.get("user_id", "default"), data.get("role", "any"))
        await ws.send_json({"type": "menu", "items": menu})

    elif action == "save_menu":
        save_menu(data.get("user_id", "default"), data.get("items", []))
        await ws.send_json({"type": "menu_saved", "ok": True})

    elif action == "chat":
        text = data.get("text", "").strip()
        if text:
            await send_to_server({"action": "chat", "text": text})

    elif action == "approve":
        task_id = data.get("task_id")
        await send_to_server({"action": "approve", "task_id": task_id})
        await broadcast({"type": "system", "text": f"✅ 승인 전송: {task_id}"})

    elif action == "reject":
        task_id = data.get("task_id")
        await send_to_server({"action": "reject", "task_id": task_id})
        await broadcast({"type": "system", "text": f"❌ 거부 전송: {task_id}"})

    elif action == "blog_write":
        asyncio.create_task(run_blog_write(data))  # noqa: RUF006
    elif action == "blog_confirm":
        asyncio.create_task(run_blog_confirm())  # noqa: RUF006
    elif action == "cafe_write":
        asyncio.create_task(run_cafe_write(data))  # noqa: RUF006
    elif action == "cafe_confirm":
        asyncio.create_task(run_cafe_confirm())  # noqa: RUF006
    elif action == "naver_cafe_list":
        asyncio.create_task(run_naver_cafe_list(ws))  # noqa: RUF006
    elif action == "naver_cafe_posts":
        asyncio.create_task(run_naver_cafe_posts(ws, data))  # noqa: RUF006
    elif action == "naver_cafe_read":
        asyncio.create_task(run_naver_cafe_read(ws, data))  # noqa: RUF006

    elif action == "browser_status":
        await handle_browser_status(ws)
    elif action == "browser_start":
        await handle_browser_start(ws)
    elif action == "browser_quit":
        await handle_browser_quit(ws)
    elif action == "tab_list":
        await handle_tab_list(ws)
    elif action == "tab_close":
        await handle_tab_close(ws, data.get("tab_id", ""))
    elif action == "login_watcher_start":
        await start_login_watcher()
        await ws.send_json({"type": "login_watcher_started", "ok": True})
    elif action == "login_watcher_stop":
        await stop_login_watcher()
        await ws.send_json({"type": "login_watcher_stopped", "ok": True})
    elif action == "browser_action":
        await handle_browser_action(ws, data)
    elif action == "screenshot":
        await handle_screenshot(ws)

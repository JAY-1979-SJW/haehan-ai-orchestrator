"""공유 상태: UI 클라이언트 목록 + broadcast + 서버 WS send.

모든 모듈이 이 모듈을 import 해서 _ui_clients / _server_ws 를 공유한다.
FastAPI WebSocket 타입은 런타임에만 필요하므로 TYPE_CHECKING 으로 분리.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import WebSocket

logger = logging.getLogger(__name__)

# ── 공유 상태 ─────────────────────────────────────────────────────────────────
_ui_clients: list[WebSocket] = []
_server_ws: Any = None  # websockets.ClientConnection | None


async def broadcast(msg: dict[str, Any]) -> None:
    """연결된 모든 UI 클라이언트에 메시지 전송."""
    dead = []
    for ws in _ui_clients:
        try:
            await ws.send_json(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ui_clients.remove(ws)


async def send_to_server(msg: dict) -> None:
    """서버 WebSocket 으로 메시지 전송."""
    global _server_ws
    if _server_ws:
        try:
            await _server_ws.send(json.dumps(msg))
        except Exception as exc:
            logger.warning("server ws send error: %s", exc)

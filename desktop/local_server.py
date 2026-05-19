"""로컬 데스크탑 앱 전용 FastAPI 서버 (포트 8765).

- 서버(8000)와 WebSocket으로 연결 → 태스크 Push 수신
- 로컬 UI(HTML)에 WebSocket으로 실시간 전달
- 사용자 설정 저장/로드 API 제공
- 민감 정보 절대 노출 금지
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from .user_settings import load_menu, save_menu

logger = logging.getLogger(__name__)

_UI_DIR = Path(__file__).parent / "ui_dist"
_SERVER_WS_URL = "wss://api.haehan-ai.kr/ws/desktop"  # 서버 측 Push WebSocket

app = FastAPI(title="Haehan Desktop Local Server", docs_url=None, redoc_url=None)

# ── 연결된 로컬 UI 클라이언트 목록 ────────────────────────────────────────────
_ui_clients: list[WebSocket] = []


async def _broadcast(msg: dict[str, Any]) -> None:
    """연결된 모든 UI 클라이언트에 메시지 전송."""
    dead = []
    for ws in _ui_clients:
        try:
            await ws.send_json(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ui_clients.remove(ws)


# ── UI ↔ 로컬서버 WebSocket ───────────────────────────────────────────────────
@app.websocket("/ws/ui")
async def ws_ui(ws: WebSocket):
    await ws.accept()
    _ui_clients.append(ws)
    logger.info("UI client connected (total=%d)", len(_ui_clients))
    try:
        while True:
            data = await ws.receive_json()
            await _handle_ui_message(data, ws)
    except WebSocketDisconnect:
        pass
    finally:
        if ws in _ui_clients:
            _ui_clients.remove(ws)
        logger.info("UI client disconnected (total=%d)", len(_ui_clients))


async def _handle_ui_message(data: dict, ws: WebSocket) -> None:
    """UI에서 온 메시지 처리."""
    action = data.get("action", "")

    if action == "load_menu":
        user_id = data.get("user_id", "default")
        role = data.get("role", "any")
        menu = load_menu(user_id, role)
        await ws.send_json({"type": "menu", "items": menu})

    elif action == "save_menu":
        user_id = data.get("user_id", "default")
        items = data.get("items", [])
        save_menu(user_id, items)
        await ws.send_json({"type": "menu_saved", "ok": True})

    elif action == "chat":
        text = data.get("text", "").strip()
        if text:
            # UI가 이미 자기 메시지를 로컬 추가했으므로 broadcast 불필요 — 서버 전달만
            await _send_to_server({"action": "chat", "text": text})

    elif action == "approve":
        task_id = data.get("task_id")
        await _send_to_server({"action": "approve", "task_id": task_id})
        await _broadcast({"type": "system", "text": f"✅ 승인 전송: {task_id}"})

    elif action == "reject":
        task_id = data.get("task_id")
        await _send_to_server({"action": "reject", "task_id": task_id})
        await _broadcast({"type": "system", "text": f"❌ 거부 전송: {task_id}"})


# ── 서버(8000) WebSocket 연결 및 Push 수신 ────────────────────────────────────
_server_ws: Any = None


async def _send_to_server(msg: dict) -> None:
    global _server_ws
    if _server_ws:
        try:
            await _server_ws.send(json.dumps(msg))
        except Exception as exc:
            logger.warning("server ws send error: %s", exc)


async def _connect_to_server() -> None:
    """서버 WebSocket에 연결 — 재연결 루프."""
    global _server_ws
    import websockets  # type: ignore

    while True:
        try:
            async with websockets.connect(_SERVER_WS_URL) as ws:
                _server_ws = ws
                await _broadcast({"type": "system", "text": "🟢 서버 연결됨"})
                logger.info("connected to server WebSocket")
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        await _on_server_message(msg)
                    except Exception as exc:
                        logger.warning("server message parse error: %s", exc)
        except Exception as exc:
            _server_ws = None
            await _broadcast({"type": "system", "text": f"🔴 서버 연결 끊김 — 재연결 중…"})
            logger.warning("server ws disconnected: %s — retry in 5s", exc)
            await asyncio.sleep(5)


async def _on_server_message(msg: dict) -> None:
    """서버에서 온 메시지를 UI로 전달."""
    msg_type = msg.get("type", "")

    if msg_type == "task":
        await _broadcast({
            "type": "task",
            "task_id": msg.get("task_id"),
            "action_type": msg.get("action_type", ""),
            "domain": msg.get("domain", ""),
            "risk_level": msg.get("risk_level", "low"),
            "description": msg.get("description", ""),
            "needs_approval": msg.get("needs_approval", False),
            "execution_location": msg.get("execution_location", ""),
            "status": msg.get("status", "수신 대기"),
            "ts": time.time(),
        })
    elif msg_type == "result":
        await _broadcast({
            "type": "chat",
            "role": "assistant",
            "text": msg.get("message", "작업 완료"),
            "ts": time.time(),
        })
    elif msg_type == "browser_status":
        await _broadcast({"type": "browser_status", **msg})
    else:
        await _broadcast(msg)


_AUTOWORK_BASE = "https://autowork.haehan-ai.kr"
_PROXY_STRIP_HEADERS = {"x-frame-options", "content-security-policy", "content-encoding", "transfer-encoding"}

@app.get("/proxy/admin/{path:path}")
async def proxy_admin(path: str, request: Request) -> Response:
    """autowork.haehan-ai.kr 페이지를 프록시로 서빙 — X-Frame-Options 제거."""
    target = f"{_AUTOWORK_BASE}/{path}"
    params = str(request.url.query)
    if params:
        target += f"?{params}"
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            resp = await client.get(target, headers={"Accept": "text/html,application/xhtml+xml,*/*"})
        headers = {k: v for k, v in resp.headers.items() if k.lower() not in _PROXY_STRIP_HEADERS}
        return Response(content=resp.content, status_code=resp.status_code,
                        headers=headers, media_type=resp.headers.get("content-type"))
    except Exception as exc:
        logger.warning("proxy error %s: %s", target, exc)
        return Response(content=f"프록시 오류: {exc}".encode(), status_code=502)


_LOG_FILE = Path(__file__).parent.parent / "data" / "logs" / "app.log"
_LOG_MAX_LINES = 500


@app.get("/logs")
async def get_logs():
    """최근 로그 라인 반환."""
    try:
        if not _LOG_FILE.exists():
            return {"lines": [], "error": "로그 파일 없음"}
        text = _LOG_FILE.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()[-_LOG_MAX_LINES:]
        return {"lines": lines}
    except Exception as exc:
        logger.warning("logs read error: %s", exc)
        return {"lines": [], "error": str(exc)}


@app.on_event("startup")
async def startup():
    asyncio.create_task(_connect_to_server())
    logger.info("local server started on port 8765")


# ── 정적 파일 서빙 — 모든 API/WS 라우트 등록 후 마지막에 마운트 ────────────────
# index.html 이 /assets/... 경로로 JS/CSS 요청하므로 루트("/")에 마운트해야 함
app.mount("/", StaticFiles(directory=str(_UI_DIR), html=True), name="ui")


def run():
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")

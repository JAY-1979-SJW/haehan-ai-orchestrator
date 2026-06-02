"""서버 WebSocket 연결 + Push 수신 + 원격 제어 처리."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

from . import _broadcast as _state
from . import agent_runtime_boundary
from ._broadcast import broadcast, send_to_server

logger = logging.getLogger(__name__)


def load_agent_credentials() -> tuple[str, str, str]:
    try:
        cfg = agent_runtime_boundary.load_desktop_config()
        if not cfg.is_complete():
            return "", "", ""
        tok = agent_runtime_boundary.load_device_token(cfg.server_url, cfg.agent_id)
        return cfg.server_url, cfg.agent_id, tok
    except Exception as exc:
        logger.warning("credentials load error: %s", exc)
        return "", "", ""


async def connect_to_server() -> None:
    """서버 WebSocket 재연결 루프 — lifespan task 로 실행."""
    from urllib.parse import urlparse, urlunparse

    import websockets  # type: ignore

    while True:
        server_url, agent_id, device_token = load_agent_credentials()
        if not agent_id or not device_token:
            await broadcast({"type": "system", "text": "⚠️ agent_id/token 미설정 — 서버 연결 건너뜀"})
            logger.warning("server ws skip: agent_id or device_token not configured")
            await asyncio.sleep(30)
            continue

        _p = urlparse(server_url)
        _ws_scheme = "wss" if _p.scheme == "https" else ("ws" if _p.scheme == "http" else _p.scheme or "ws")
        ws_url = urlunparse((_ws_scheme, _p.netloc, _p.path.rstrip("/") + "/api/v1/local-agents/ws", "", "", ""))

        try:
            async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20) as ws:
                await ws.send(json.dumps({"type": "auth", "agent_id": agent_id, "device_token": device_token}))
                try:
                    first = json.loads(await asyncio.wait_for(ws.recv(), timeout=15.0))
                except TimeoutError:
                    logger.error("server auth timeout")
                    await asyncio.sleep(5)
                    continue
                if first.get("type") != "auth_ok":
                    await broadcast({"type": "system", "text": f"🔴 서버 인증 실패: {first.get('type')}"})
                    await asyncio.sleep(10)
                    continue

                _state._server_ws = ws
                await broadcast({"type": "system", "text": f"🟢 서버 연결됨 (agent: {agent_id[:8]}…)"})
                logger.info("connected to server WebSocket (agent_id=%s)", agent_id)
                async for raw in ws:
                    try:
                        await _on_server_message(json.loads(raw))
                    except Exception as exc:
                        logger.warning("server message parse error: %s", exc)
        except Exception as exc:
            _state._server_ws = None
            await broadcast({"type": "system", "text": "🔴 서버 연결 끊김 — 재연결 중…"})
            logger.warning("server ws disconnected: %s — retry in 5s", exc)
            await asyncio.sleep(5)


async def _on_server_message(msg: dict) -> None:
    msg_type = msg.get("type", "")

    if msg_type == "task":
        await broadcast(
            {
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
            }
        )
    elif msg_type == "user_present_task":
        task = msg.get("task") or {}
        if not _state._ui_clients:
            workflow_run_id = task.get("workflow_run_id", "")
            await send_to_server(
                {
                    "action": "user_present_ack",
                    "workflow_run_id": workflow_run_id,
                    "status": "WAITING_FOR_USER",
                    "ui_connected": False,
                }
            )
            logger.info("user_present_task held: UI disconnected (workflow_run_id=%s)", workflow_run_id)
            return
        await broadcast({"type": "user_present_task", "task": task, "ts": time.time()})
    elif msg_type == "task_blocked":
        await broadcast(
            {
                "type": "task_blocked",
                "task_id": msg.get("task_id", ""),
                "workflow_run_id": msg.get("workflow_run_id", ""),
                "reason": msg.get("reason", ""),
                "message_ko": msg.get("message_ko", ""),
                "ts": time.time(),
            }
        )
    elif msg_type == "result":
        await broadcast(
            {"type": "chat", "role": "assistant", "text": msg.get("message", "작업 완료"), "ts": time.time()}
        )
    elif msg_type == "browser_status":
        await broadcast({"type": "browser_status", **msg})
    elif msg_type == "remote_control":
        await _handle_remote_control(msg)
    else:
        await broadcast(msg)


async def _handle_remote_control(msg: dict) -> None:
    from .remote_access import ALLOWED_REMOTE_COMMANDS

    cmd = msg.get("command", "")
    req_id = msg.get("request_id", "")

    if cmd not in ALLOWED_REMOTE_COMMANDS:
        await send_to_server(
            {"type": "remote_control_result", "request_id": req_id, "ok": False, "error": f"허용되지 않은 명령: {cmd}"}
        )
        logger.warning("remote_control: blocked command=%s", cmd)
        return

    try:
        result = await _exec_remote_command(cmd, msg)
        await send_to_server(
            {"type": "remote_control_result", "request_id": req_id, "ok": True, "command": cmd, "data": result}
        )
    except Exception as exc:
        await send_to_server({"type": "remote_control_result", "request_id": req_id, "ok": False, "error": str(exc)})
        logger.error("remote_control error cmd=%s: %s", cmd, exc)


async def _exec_remote_command(cmd: str, msg: dict) -> dict:
    import platform

    if cmd == "ping":
        return {"pong": True, "ts": time.time()}

    if cmd == "get_status":
        from .local_runner import LocalRunner

        runner = LocalRunner()
        return {
            "runner_state": runner.get_status(),
            "platform": platform.system(),
            "ui_clients": len(_state._ui_clients),
        }

    if cmd == "get_logs_tail":
        log_file = Path(__file__).parent.parent / "data" / "logs" / "app.log"
        if not log_file.exists():
            return {"lines": []}
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        _FORBIDDEN = {"token", "password", "secret", "authorization", "cookie"}
        safe = [line for line in lines if not any(k in line.lower() for k in _FORBIDDEN)]
        return {"lines": safe[-100:]}

    if cmd == "open_url":
        import webbrowser

        url = str(msg.get("url", ""))
        if not url.startswith(("http://", "https://")):
            raise ValueError("허용되지 않은 URL 스킴")
        webbrowser.open(url)
        return {"opened": url}

    raise ValueError(f"미구현 명령: {cmd}")

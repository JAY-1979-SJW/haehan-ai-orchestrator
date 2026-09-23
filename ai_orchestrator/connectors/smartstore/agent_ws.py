"""로컬 CDP 에이전트 WebSocket 브릿지.

흐름:
  로컬 에이전트 → WS /smartstore/agent/ws?license=KEY
  서버 chat.py  → call_local_tool(license_key, tool, inputs)
               → WS로 명령 전송 → 에이전트 실행 → 결과 반환
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from .license import touch, verify

router = APIRouter()

# ── 연결된 에이전트 레지스트리 ────────────────────────────────────────────────
# license_key → WebSocket
_agents: dict[str, WebSocket] = {}
# request_id → Future (결과 대기)
_pending: dict[str, asyncio.Future] = {}


def get_connected_agents() -> list[str]:
    return list(_agents.keys())


# ── WebSocket 엔드포인트 ──────────────────────────────────────────────────────


@router.websocket("/agent/ws")
async def agent_ws(ws: WebSocket, license: str = Query(...)):
    ok, rec, reason = verify(license)
    if not ok:
        await ws.close(code=4001, reason=reason)
        return

    agent_id = str(uuid.uuid4())[:8]
    touch(license, agent_id=agent_id)
    _agents[license] = ws

    await ws.accept()
    await ws.send_json({"type": "connected", "agent_id": agent_id, "plan": rec["plan"]})

    try:
        while True:
            msg = await ws.receive_json()
            # 에이전트가 도구 실행 결과를 응답
            if msg.get("type") == "tool_result":
                req_id = msg.get("request_id")
                fut = _pending.pop(req_id, None)
                if fut and not fut.done():
                    fut.set_result(msg.get("result", {}))
    except WebSocketDisconnect:
        pass
    finally:
        _agents.pop(license, None)
        # 대기 중인 요청에 에러 반환
        for fut in _pending.values():
            if not fut.done():
                fut.set_exception(RuntimeError("agent_disconnected"))
        _pending.clear()


# ── 서버→에이전트 도구 호출 ───────────────────────────────────────────────────


async def call_local_tool(
    license_key: str,
    tool: str,
    inputs: dict[str, Any],
    timeout: float = 60.0,
) -> dict:
    """서버에서 로컬 에이전트의 CDP 도구를 호출하고 결과를 기다린다."""
    ws = _agents.get(license_key)
    if not ws:
        return {
            "ok": False,
            "error": "local_agent_not_connected",
            "hint": "로컬 에이전트가 연결되지 않았습니다. Haehan AI 앱을 실행하세요.",
        }

    req_id = str(uuid.uuid4())
    loop = asyncio.get_event_loop()
    fut: asyncio.Future = loop.create_future()
    _pending[req_id] = fut

    await ws.send_json(
        {
            "type": "tool_call",
            "request_id": req_id,
            "tool": tool,
            "inputs": inputs,
        }
    )

    try:
        result = await asyncio.wait_for(fut, timeout=timeout)
        touch(license_key)
        return result
    except TimeoutError:
        _pending.pop(req_id, None)
        return {"ok": False, "error": "agent_timeout", "hint": "로컬 에이전트 응답 시간 초과"}
    except Exception as e:
        _pending.pop(req_id, None)
        return {"ok": False, "error": str(e)}

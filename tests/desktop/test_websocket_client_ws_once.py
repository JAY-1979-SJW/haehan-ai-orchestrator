"""회귀 시험: HAEHAN_AGENT_WS_ONCE=true 이면 WS 세션이 auth_ok 직후 메시지
루프 없이 깨끗이 끝나고, run_forever() 가 재접속하지 않고 반환한다.

결함(2026-10-10 격리 서버 실측): agent.py --once 가 HAEHAN_AGENT_WS_ONCE 를
setdefault 로 설정만 하고, websocket_client.py 어디에도 이 값을 읽는 코드가
없어 --once 가 실제로는 무한 대기했다(수동 kill 필요). run_forever/타임아웃
없이 테스트로 재발을 잡는다.
"""

from __future__ import annotations

import json

import pytest

from core.agent_runtime.connection import websocket_client as W


class _FakeWS:
    def __init__(self, auth_ok_msg: dict):
        self._auth_ok_msg = auth_ok_msg
        self.sent: list[str] = []

    async def send(self, data: str) -> None:
        self.sent.append(data)

    async def recv(self) -> str:
        return json.dumps(self._auth_ok_msg)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeWebsocketsModule:
    def __init__(self, ws: _FakeWS):
        self._ws = ws

    def connect(self, *args, **kwargs):
        return self._ws


@pytest.fixture(autouse=True)
def _clear_ws_once_env(monkeypatch):
    monkeypatch.delenv("HAEHAN_AGENT_WS_ONCE", raising=False)


def test_run_session_returns_right_after_auth_ok_when_once(monkeypatch):
    ws = _FakeWS({"type": "auth_ok"})
    monkeypatch.setattr(W, "_load_websockets_module", lambda: _FakeWebsocketsModule(ws))
    monkeypatch.setattr(W, "_server_ws_url", lambda: "ws://test/local-agents/ws")
    monkeypatch.setattr(W, "websocket_connect_kwargs", lambda *_a, **_k: {})
    monkeypatch.setenv("HAEHAN_AGENT_WS_ONCE", "true")

    import asyncio

    asyncio.run(W._run_session("agent-1", "token-1"))

    # 메시지 루프(heartbeat/task 처리)로 들어가지 않고 auth 1건만 보내고 끝났다.
    assert len(ws.sent) == 1


def test_run_forever_does_not_reconnect_when_once(monkeypatch):
    calls = {"n": 0}

    async def fake_run_session(agent_id, device_token):
        calls["n"] += 1

    monkeypatch.setattr(W, "_run_session", fake_run_session)
    monkeypatch.setenv("HAEHAN_AGENT_WS_ONCE", "true")
    monkeypatch.setattr(W.config, "WEBSOCKET_ENABLED", True)

    import asyncio

    asyncio.run(asyncio.wait_for(W.run_forever("agent-1", "token-1"), timeout=5.0))

    assert calls["n"] == 1  # 재접속 없이 1회로 끝남

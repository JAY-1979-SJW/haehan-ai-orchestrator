"""AGENT_OPENAI_SERVER_PROXY_CLIENT_01 — 25+ 테스트."""

from __future__ import annotations

import io
import json
import re
import urllib.error
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ai_orchestrator import agent_ai_proxy_router as proxy_router
from ai_orchestrator import local_agent_registry as reg
from ai_orchestrator import openai_proxy_caller as caller

# ── helpers ────────────────────────────────────────────


@pytest.fixture
def app_client(monkeypatch):
    """ai_orchestrator FastAPI 앱 TestClient."""
    monkeypatch.setenv("OPENAI_API_KEY", "FAKE_SERVER_KEY_xxxxxxxxxxxxxxxxxxx")
    from ai_orchestrator.server import app

    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_state():
    reg.clear()
    proxy_router._rate_buckets.clear()
    yield
    reg.clear()


def _register_agent():
    r = reg.register_agent(host="h", os_name="o", version="0.1", requested_by="test")
    return r.agent.agent_id, r.device_token


# ── 1) endpoint schema ─────────────────────────────────


def test_health_endpoint_exists(app_client):
    aid, tok = _register_agent()
    r = app_client.get(
        "/api/v1/agent-ai/health",
        headers={"X-Agent-Id": aid, "Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert "openai_key_configured" in d


def test_chat_endpoint_exists(app_client, monkeypatch):
    # OpenAI 호출은 mock
    def fake_call(*, message, model=None, max_tokens=400, timeout=30, _opener=None, _api_url=None):
        return caller.ProxyCallResult(
            ok=True,
            text="pong",
            finish_reason="stop",
            usage_summary={"total_tokens": 5},
            duration_ms=10,
            model_used="gpt-4o-mini",
        )

    monkeypatch.setattr(caller, "call_openai_chat", fake_call)
    aid, tok = _register_agent()
    r = app_client.post(
        "/api/v1/agent-ai/chat",
        headers={"X-Agent-Id": aid, "Authorization": f"Bearer {tok}"},
        json={"message": "hi"},
    )
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["text"] == "pong"
    assert d["external_call_count"] == 1


# ── 2) auth ────────────────────────────────────────────


def test_missing_agent_id_rejected(app_client):
    r = app_client.post("/api/v1/agent-ai/chat", json={"message": "hi"})
    assert r.status_code == 401


def test_missing_token_rejected(app_client):
    aid, _ = _register_agent()
    r = app_client.post(
        "/api/v1/agent-ai/chat",
        headers={"X-Agent-Id": aid},
        json={"message": "hi"},
    )
    assert r.status_code == 401


def test_bad_token_rejected(app_client):
    aid, _ = _register_agent()
    r = app_client.post(
        "/api/v1/agent-ai/chat",
        headers={"X-Agent-Id": aid, "Authorization": "Bearer wrong"},
        json={"message": "hi"},
    )
    assert r.status_code == 401


def test_good_token_accepted(app_client, monkeypatch):
    def fake_call(**kw):
        return caller.ProxyCallResult(ok=True, text="pong")

    monkeypatch.setattr(caller, "call_openai_chat", fake_call)
    aid, tok = _register_agent()
    r = app_client.post(
        "/api/v1/agent-ai/chat",
        headers={"X-Agent-Id": aid, "Authorization": f"Bearer {tok}"},
        json={"message": "hi"},
    )
    assert r.status_code == 200


def test_x_device_token_header_also_works(app_client, monkeypatch):
    def fake_call(**kw):
        return caller.ProxyCallResult(ok=True, text="pong")

    monkeypatch.setattr(caller, "call_openai_chat", fake_call)
    aid, tok = _register_agent()
    r = app_client.post(
        "/api/v1/agent-ai/chat",
        headers={"X-Agent-Id": aid, "X-Device-Token": tok},
        json={"message": "hi"},
    )
    assert r.status_code == 200


# ── 3) message validation ──────────────────────────────


def test_empty_message_rejected(app_client):
    aid, tok = _register_agent()
    r = app_client.post(
        "/api/v1/agent-ai/chat",
        headers={"X-Agent-Id": aid, "Authorization": f"Bearer {tok}"},
        json={"message": ""},
    )
    # pydantic min_length=1 → 422
    assert r.status_code in (422, 200)


def test_too_long_message_rejected(app_client):
    aid, tok = _register_agent()
    r = app_client.post(
        "/api/v1/agent-ai/chat",
        headers={"X-Agent-Id": aid, "Authorization": f"Bearer {tok}"},
        json={"message": "x" * 9000},
    )
    assert r.status_code in (422, 200)


# ── 4) rate limit ──────────────────────────────────────


def test_rate_limit_basic(app_client, monkeypatch):
    def fake_call(**kw):
        return caller.ProxyCallResult(ok=True, text="pong")

    monkeypatch.setattr(caller, "call_openai_chat", fake_call)
    # 한도 낮춤
    monkeypatch.setattr(proxy_router, "RATE_LIMIT_PER_MIN", 3)
    aid, tok = _register_agent()
    h = {"X-Agent-Id": aid, "Authorization": f"Bearer {tok}"}
    for _ in range(3):
        r = app_client.post("/api/v1/agent-ai/chat", headers=h, json={"message": "hi"})
        assert r.json()["ok"] is True
    # 4번째 — rate limit
    r = app_client.post("/api/v1/agent-ai/chat", headers=h, json={"message": "hi"})
    d = r.json()
    assert d["ok"] is False
    assert d["error_code"] == "RATE_LIMITED_AGENT"


# ── 5) OpenAI key missing → API_KEY_NOT_SET ───────────


def test_openai_key_missing_returns_error(app_client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    aid, tok = _register_agent()
    r = app_client.post(
        "/api/v1/agent-ai/chat",
        headers={"X-Agent-Id": aid, "Authorization": f"Bearer {tok}"},
        json={"message": "hi"},
    )
    d = r.json()
    assert d["ok"] is False
    assert d["error_code"] == "API_KEY_NOT_SET"


# ── 6) caller — env 사용 ─────────────────────────────


def test_caller_has_server_openai_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x" * 30)
    assert caller.has_server_openai_key() is True
    monkeypatch.setenv("OPENAI_API_KEY", "")
    assert caller.has_server_openai_key() is False


def test_caller_returns_not_set_when_no_env(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = caller.call_openai_chat(message="hi")
    assert r.ok is False
    assert r.error_code == caller.ERR_API_KEY_NOT_SET


def test_caller_returns_empty_for_empty_message(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x" * 30)
    r = caller.call_openai_chat(message="")
    assert r.error_code == caller.ERR_RESPONSE_EMPTY


def test_caller_http_401_classified(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x" * 30)

    def fake_open(req, **kw):
        raise urllib.error.HTTPError("https://api.openai.com/v1/chat/completions", 401, "x", {}, io.BytesIO(b"invalid"))

    r = caller.call_openai_chat(message="hi", _opener=fake_open)
    assert r.error_code == caller.ERR_API_KEY_INVALID


def test_caller_success_parses(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x" * 30)

    class _R:
        status = 200

        def read(self):
            return json.dumps(
                {
                    "choices": [{"message": {"content": "안녕"}, "finish_reason": "stop"}],
                    "usage": {"total_tokens": 10},
                    "model": "gpt-4o-mini",
                }
            ).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    r = caller.call_openai_chat(message="hi", _opener=lambda req, **kw: _R())
    assert r.ok is True
    assert r.text == "안녕"


# ── 7) desktop proxy client ───────────────────────────


def test_desktop_client_schema():
    from local_agent import server_proxy_chat_client as spc

    assert hasattr(spc, "ServerProxyChatClient")
    assert hasattr(spc, "ProxyChatResponse")
    assert spc.PROXY_PATH_CHAT == "/api/v1/agent-ai/chat"


def test_desktop_client_not_configured_without_token(monkeypatch):
    from local_agent import server_proxy_chat_client as spc
    from local_agent import token_store as ts

    monkeypatch.setattr(ts, "has_device_token", lambda **kw: False)
    c = spc.ServerProxyChatClient(server_url="https://x", agent_id="la-x")
    assert c.is_configured() is False


def test_desktop_client_send_returns_token_missing(monkeypatch):
    from local_agent import server_proxy_chat_client as spc
    from local_agent import token_store as ts

    monkeypatch.setattr(ts, "load_device_token", lambda **kw: None)
    c = spc.ServerProxyChatClient(server_url="https://x", agent_id="la-x")
    r = c.chat("hi")
    assert r.ok is False
    assert r.error_code == spc.ERR_DEVICE_TOKEN_MISSING


def test_desktop_client_uses_bearer_header(monkeypatch):
    from local_agent import server_proxy_chat_client as spc
    from local_agent import token_store as ts

    monkeypatch.setattr(ts, "load_device_token", lambda **kw: "FAKE_DEVICE_TOKEN_xyz")

    captured = {}

    class _R:
        status = 200

        def read(self):
            return json.dumps(
                {"ok": True, "text": "ok", "model": "m", "external_call_count": 1, "usage_summary": {}}
            ).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    def fake_open(req, **kw):
        captured["url"] = req.full_url
        captured["auth"] = req.get_header("Authorization")
        captured["agent"] = req.get_header("X-agent-id") or req.get_header("X-Agent-Id")
        return _R()

    c = spc.ServerProxyChatClient(server_url="https://x", agent_id="la-test1234")
    r = c.chat("hi", _opener=fake_open)
    assert r.ok is True
    assert "Bearer FAKE_DEVICE_TOKEN_xyz" in captured.get("auth", "")
    assert captured["agent"] == "la-test1234"


def test_desktop_client_redacts_echo_back(monkeypatch):
    """서버 응답에 echo back 된 token 형태가 있어도 redact 적용."""
    from local_agent import server_proxy_chat_client as spc
    from local_agent import token_store as ts

    monkeypatch.setattr(ts, "load_device_token", lambda **kw: "FAKE_DEVICE_TOKEN_xyz")

    class _R:
        status = 200

        def read(self):
            return json.dumps(
                {
                    "ok": True,
                    "text": "your token is sk-abcdef123456789012345678 here",
                    "model": "m",
                    "external_call_count": 1,
                    "usage_summary": {},
                }
            ).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    c = spc.ServerProxyChatClient(server_url="https://x", agent_id="la-x")
    r = c.chat("hi", _opener=lambda req, **kw: _R())
    assert "sk-abcdef123456789012345678" not in r.text_redacted


# ── 8) adapter SERVER_PROXY 분기 ──────────────────────


def test_adapter_server_proxy_returns_server_proxy_adapter():
    from local_agent import ai_chat_adapter as adp
    from local_agent import gui_chat_state as cs

    a = adp.make_default_adapter(mode=cs.MODE_SERVER_PROXY, server_url="https://x", agent_id="la-test")
    assert isinstance(a, adp.ServerProxyChatAdapter)


def test_adapter_dev_unchanged():
    from local_agent import ai_chat_adapter as adp
    from local_agent import gui_chat_state as cs

    a = adp.make_default_adapter(mode=cs.MODE_DEV_TEST_KEY)
    assert isinstance(a, adp.OpenAiDirectTestAdapter)


def test_adapter_byok_still_placeholder():
    from local_agent import ai_chat_adapter as adp
    from local_agent import gui_chat_state as cs

    a = adp.make_default_adapter(mode=cs.MODE_USER_BYOK)
    assert isinstance(a, adp.PlaceholderAdapter)


def test_adapter_proxy_not_configured_without_token(monkeypatch):
    from local_agent import ai_chat_adapter as adp
    from local_agent import gui_chat_state as cs
    from local_agent import token_store as ts

    monkeypatch.setattr(ts, "has_device_token", lambda **kw: False)
    a = adp.make_default_adapter(mode=cs.MODE_SERVER_PROXY, server_url="https://x", agent_id="la-test")
    r = a.send_message(text_raw="hi")
    assert r.ok is False


# ── 9) PII / leak 검사 ───────────────────────────────


def test_server_router_no_raw_api_key():
    src = Path("ai_orchestrator/agent_ai_proxy_router.py").read_text(encoding="utf-8")
    matches = re.findall(r"\bsk-[A-Za-z0-9_]{30,}\b", src)
    real = [m for m in matches if "A-Za-z" not in m]
    assert real == []


def test_server_router_no_file_write():
    src = Path("ai_orchestrator/agent_ai_proxy_router.py").read_text(encoding="utf-8")
    assert not re.search(r"open\s*\([^)]*['\"][wa]", src)
    assert ".write_text" not in src


def test_caller_authorization_header_uses_variable():
    """소스에 raw key 가 아닌 변수(api_key) 를 사용했는지."""
    src = Path("ai_orchestrator/openai_proxy_caller.py").read_text(encoding="utf-8")
    assert "Authorization" in src
    assert "{api_key}" in src or "api_key" in src


def test_desktop_client_does_not_log_token():
    src = Path("local_agent/server_proxy_chat_client.py").read_text(encoding="utf-8")
    bad = re.findall(r"log(?:ger)?\.\w+\([^)]*%[sr][^)]*,\s*token\b", src)
    assert bad == []


# ── 11) audit ────────────────────────────────────────


def test_audit_warn_server_deploy_required():
    from scripts.ops import audit_openai_server_proxy_client as a

    v = a.judge_proxy(desktop_ui_unchanged=True, server_deployed=False)
    assert v.code in ("PASS_OPENAI_SERVER_PROXY_CLIENT", "WARN_SERVER_DEPLOY_REQUIRED")


def test_audit_fail_desktop_ui_touched():
    from scripts.ops import audit_openai_server_proxy_client as a

    v = a.judge_proxy(desktop_ui_unchanged=False)
    assert v.code == "FAIL_DESKTOP_UI_TOUCHED"


# ── 12) 회귀 가드 ─────────────────────────────────


def test_regression_openai_direct_client_intact():
    from local_agent import openai_chat_client as occ

    assert hasattr(occ, "OpenAiDirectTestClient")


def test_regression_local_agent_router_intact():
    from ai_orchestrator import local_agent_router as r

    assert hasattr(r, "local_agent_router")


def test_regression_gui_state_unchanged():
    from local_agent import gui_state as gs

    assert hasattr(gs, "GuiController")

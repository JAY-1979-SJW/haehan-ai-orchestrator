from __future__ import annotations

from core.agent_runtime.connection import network_bypass as nb


def test_haehan_host_needs_direct():
    assert nb.host_needs_direct("https://haehan-ai.kr/orchestrator")
    assert not nb.host_needs_direct("https://example.com")


def test_extend_no_proxy_preserves_existing_entries():
    value = nb.extend_no_proxy("localhost,127.0.0.1")

    assert "localhost" in value
    assert "127.0.0.1" in value
    assert "haehan-ai.kr" in value


def test_direct_child_env_clears_proxy_env(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("NO_PROXY", "localhost")

    env = nb.direct_child_env()

    assert env["NO_PROXY"] == "localhost,haehan-ai.kr"
    assert "HTTP_PROXY" not in env
    assert "HTTPS_PROXY" not in env
    assert "ALL_PROXY" not in env


def test_websocket_connect_kwargs_disables_proxy_for_haehan():
    assert nb.websocket_connect_kwargs("https://haehan-ai.kr/orchestrator") == {"proxy": None}
    assert nb.websocket_connect_kwargs("https://example.com") == {}

import json

from local_agent.cad import http_agent_client as client
from mcp_server.local_cad_adapter_tools import cad_agent_health_json


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_cad_agent_health_success(monkeypatch):
    monkeypatch.setattr(client, "urlopen", lambda url, timeout=3: FakeResponse({"ok": True, "status": "RUNNING"}))

    result = client.cad_agent_health()

    assert result["ok"] is True
    assert result["transport"] == "local_http_agent"


def test_cad_agent_health_unavailable(monkeypatch):
    def fail(url, timeout=3):
        raise OSError("offline")

    monkeypatch.setattr(client, "urlopen", fail)

    result = client.cad_agent_health()

    assert result["ok"] is False
    assert result["status"] == "AGENT_UNAVAILABLE"


def test_mcp_cad_agent_health_json(monkeypatch):
    monkeypatch.setattr(client, "urlopen", lambda url, timeout=3: FakeResponse({"ok": True, "status": "RUNNING"}))

    payload = json.loads(cad_agent_health_json())

    assert payload["action"] == "cad.agent_health"
    assert payload["success"] is True

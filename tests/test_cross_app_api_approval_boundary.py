import asyncio
import json

from fastapi import Response

from desktop import cad_api_approval
from desktop import cad_bridge_proxy
from desktop import local_agent_service as svc
from local_agent.cad.command_approval import CadCommandApprovalStore


def test_direct_cad_mcp_discovery_disabled(monkeypatch, tmp_path):
    cad_root = tmp_path / "14. CAD sibling"
    server = cad_root / "mcp_server" / "server.py"
    server.parent.mkdir(parents=True)
    server.write_text("print('should not run')", encoding="utf-8")

    monkeypatch.setenv("CAD_REPO_PATH", str(cad_root))

    assert svc._find_mcp_server() is None


def test_explicit_use_mcp_is_blocked_before_subprocess(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-mock-test-key")
    monkeypatch.setattr(svc, "_anthropic_available", lambda: True)
    monkeypatch.setattr(svc.shutil, "which", lambda _name: None)

    result = asyncio.run(svc.run_local_agent({"prompt": "cad work", "use_mcp": True}))

    assert result["ok"] is False
    assert result["error_code"] == "CROSS_APP_API_APPROVAL_REQUIRED"
    assert result["provider"] == "approved_api_bridge"


def test_cad_bridge_api_requires_approval(monkeypatch):
    async def _should_not_proxy(*_args, **_kwargs):
        raise AssertionError("CAD bridge proxy must not run without approval")

    monkeypatch.setattr(cad_bridge_proxy, "proxy_cad_bridge_request", _should_not_proxy)

    result = asyncio.run(
        svc.run_local_agent({
            "prompt": "cad work",
            "api_action": "cad_bridge_api",
            "api_path": "acad/inventory/analyze-drawing-inventory",
        })
    )

    assert result["ok"] is False
    assert result["error_code"] == "CAD_API_APPROVAL_ID_MISSING"


def test_approved_cad_bridge_api_uses_proxy(monkeypatch):
    calls = {}
    store = CadCommandApprovalStore()
    api_path = "acad/inventory/analyze-drawing-inventory"
    approval_id, approval_token = store.create_approval(
        f"POST:{api_path}",
        "cad_bridge_api",
    )
    store.approve(approval_id)

    async def _fake_proxy(method, path, *, query=None, body=None, headers=None, timeout=5.0):
        calls["method"] = method
        calls["path"] = path
        calls["body"] = body
        calls["headers"] = headers
        calls["query"] = query
        calls["timeout"] = timeout
        return Response(
            content=b'{"ok":true,"items":[]}',
            status_code=200,
            media_type="application/json",
        )

    monkeypatch.setattr(cad_bridge_proxy, "proxy_cad_bridge_request", _fake_proxy)
    monkeypatch.setattr(cad_api_approval, "get_default_cad_api_approval_store", lambda: store)

    result = asyncio.run(
        svc.run_local_agent({
            "prompt": "cad work",
            "api_action": "cad_bridge_api",
            "api_path": api_path,
            "api_payload": {"drawing": "sample.dwg"},
            "approval_id": approval_id,
            "approval_token": approval_token,
        })
    )

    assert result["ok"] is True
    assert result["provider"] == "approved_api_bridge"
    assert result["approval_id"] == approval_id
    assert calls["method"] == "POST"
    assert calls["path"] == api_path
    assert json.loads(calls["body"].decode("utf-8")) == {"drawing": "sample.dwg"}
    assert "authorization" not in {k.lower() for k in calls["headers"]}
    assert store.consume(approval_id, approval_token) is False


def test_cad_bridge_api_rejects_scope_mismatch(monkeypatch):
    store = CadCommandApprovalStore()
    approval_id, approval_token = store.create_approval(
        "POST:acad/other/path",
        "cad_bridge_api",
    )
    store.approve(approval_id)

    async def _should_not_proxy(*_args, **_kwargs):
        raise AssertionError("CAD bridge proxy must not run on scope mismatch")

    monkeypatch.setattr(cad_bridge_proxy, "proxy_cad_bridge_request", _should_not_proxy)
    monkeypatch.setattr(cad_api_approval, "get_default_cad_api_approval_store", lambda: store)

    result = asyncio.run(
        svc.run_local_agent({
            "prompt": "cad work",
            "api_action": "cad_bridge_api",
            "api_path": "acad/inventory/analyze-drawing-inventory",
            "approval_id": approval_id,
            "approval_token": approval_token,
        })
    )

    assert result["ok"] is False
    assert result["error_code"] == "CAD_API_APPROVAL_SCOPE_MISMATCH"


def test_preflight_reports_api_bridge_not_mcp_path(monkeypatch):
    monkeypatch.setattr(svc, "_anthropic_available", lambda: False)
    monkeypatch.setattr(svc.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        svc,
        "_cad_bridge_status_summary",
        lambda: {
            "available": False,
            "mode": "approved_api_bridge",
            "status": "STOPPED",
            "host": "127.0.0.1",
            "port": 8766,
        },
    )
    monkeypatch.setattr(svc, "_check_cdp_available", lambda: False)

    data = svc.local_agent_preflight()

    assert data["optional_status"]["cad"]["mode"] == "approved_api_bridge"
    assert "path" not in data["optional_status"]["cad"]
    assert "CAD_API_BRIDGE_NOT_READY" in data["warnings"]

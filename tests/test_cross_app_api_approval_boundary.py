import asyncio

from desktop import local_agent_service as svc


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

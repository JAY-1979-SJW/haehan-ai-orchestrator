from __future__ import annotations

import json
from pathlib import Path

from tools.audits.agent.audit_mcp_gateway_baseline import audit


def test_mcp_gateway_baseline_audit_passes() -> None:
    ok, findings = audit()

    assert ok, findings


def test_mcp_registry_template_defaults_to_disabled_and_no_inline_secrets() -> None:
    registry = Path("configs/external_mcp_registry.template.json")
    text = registry.read_text(encoding="utf-8")
    data = json.loads(text)

    assert "Bearer " not in text
    assert "sk-" not in text
    assert data["status"] == "template"
    assert data["servers"]
    assert all(server["enabled"] is False for server in data["servers"])
    assert all(server["allowed_tools"] for server in data["servers"])
    assert all(server["blocked_tools"] for server in data["servers"])


def test_app_structure_baseline_keeps_mcp_gateway_but_home_surface_is_retired() -> None:
    # 2026-10-05 정책: 홈 재작성(855d595a 단일 AI 콘솔) 후 MCP Gateway 화면 표면은 폐기.
    baseline = Path("docs/baseline/AI_AGENT_APP_STRUCTURE_DESIGN_BASELINE.md").read_text(encoding="utf-8")
    home = Path("admin-web/src/app/page.tsx").read_text(encoding="utf-8")

    assert "External MCP / Tool Gateway" in baseline
    assert "MCP Gateway readiness" in baseline
    assert "External MCP Gateway" not in home
    assert "Registered MCP servers and owned app adapters" not in home
    assert "MCP Gateway readiness" not in home

from __future__ import annotations

from pathlib import Path

from scripts.ops.audit_ai_agent_ui_structure_blueprint import audit


def test_ai_agent_ui_structure_blueprint_audit_passes() -> None:
    ok, findings = audit()

    assert ok, findings


def test_ui_blueprint_defines_result_first_tool_template() -> None:
    text = Path("docs/baseline/AI_AGENT_UI_STRUCTURE_BLUEPRINT.md").read_text(encoding="utf-8")

    assert "Tool Surface Template" in text
    assert "Result Panel" in text
    assert "Approval Panel" in text
    assert "Work Record Panel" in text
    assert "MCP And External Tool Catalog" in text
    assert "Blank natural-language prompts are not the default" in text


def test_home_links_ui_blueprint_artifact() -> None:
    text = Path("admin-web/src/app/page.tsx").read_text(encoding="utf-8")

    assert "AI agent UI structure blueprint" in text
    assert "docs/baseline/AI_AGENT_UI_STRUCTURE_BLUEPRINT.md" in text

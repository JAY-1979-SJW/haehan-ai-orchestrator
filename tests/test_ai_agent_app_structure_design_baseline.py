from __future__ import annotations

from pathlib import Path

from scripts.ops.audit_ai_agent_app_structure_design_baseline import audit


def test_ai_agent_app_structure_design_baseline_audit_passes() -> None:
    ok, findings = audit()

    assert ok, findings


def test_ai_agent_app_baseline_locks_internal_module_default() -> None:
    baseline = Path("docs/baseline/AI_AGENT_APP_STRUCTURE_DESIGN_BASELINE.md").read_text(encoding="utf-8")

    assert "Do not create a separate domain for a tool by default." in baseline
    assert "admin-web" in baseline
    assert "Execution And Gate Rules" in baseline
    assert "AI Integration Contract" in baseline
    assert "Low-Input Immediate-Result UX Contract" in baseline
    assert "preset/button first" in baseline
    assert "Natural-language input is an override path" in baseline
    assert "compact chat/input panel" in baseline
    assert "persistent result panel" in baseline
    assert "Chat must not be the only way" in baseline
    assert "User instruction" in baseline
    assert "approval gate before final state-changing action" in baseline


def test_market_research_nav_not_registered_while_page_missing() -> None:
    # 2026-09-30: /market-research 페이지가 없어 클릭 시 404 → nav 항목 제거됨(b769231d).
    nav = Path("admin-web/src/lib/nav.ts").read_text(encoding="utf-8")
    page_exists = Path("admin-web/src/app/market-research").exists()

    assert ('href: "/market-research"' in nav) == page_exists


def test_home_dashboard_exposes_ai_runtime_contract() -> None:
    page = Path("admin-web/src/app/page.tsx").read_text(encoding="utf-8")

    assert 'data-testid="ai-agent-app-dashboard"' in page
    assert "Server, local agent, app UI, and AI orchestration" in page
    assert "Quick Actions And Immediate Results" in page
    assert "Chat And Result Workspace" in page
    assert 'data-testid="ai-agent-chat-input"' in page
    assert 'data-testid="ai-agent-result-panel"' in page
    assert "Latest result panel" in page
    assert "Button-first action" in page
    assert "Runtime Integration Flow" in page
    assert "Current App Tool Surfaces" in page
    assert "approval gate" in page
    assert "natural-language input is the fallback" in page

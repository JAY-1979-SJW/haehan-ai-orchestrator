from __future__ import annotations

from pathlib import Path

from tools.audits.app.audit_ai_agent_app_structure_design_baseline import audit


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
    # 2026-09-30 홈 재작성(855d595a 단일 AI 콘솔): 대시보드형 홈 -> UniversalChat 단일 콘솔.
    page = Path("admin-web/src/app/page.tsx").read_text(encoding="utf-8")

    assert 'data-testid="ai-agent-console"' in page
    assert "단일 AI 작업 콘솔" in page
    assert 'import { UniversalChat } from "@/components/chat/UniversalChat"' in page
    assert '<UniversalChat domain="default" title="AI 작업 콘솔"' in page
    assert "실제 작업은 브라우저(CDP)에서 수행됩니다" in page

from __future__ import annotations

from pathlib import Path

from scripts.site_engine.command_router import is_service_cmd
from tools.audits.app.audit_site_work_function_baseline import audit


def test_site_work_function_baseline_audit_passes() -> None:
    ok, findings = audit()

    assert ok, findings


def test_gabia_is_routed_as_site_work_command() -> None:
    assert is_service_cmd("gabia") is True


def test_site_work_service_commands_are_routed() -> None:
    for command in ("google", "gmail", "naver", "smartstore", "hiworks", "gabia", "youtube"):
        assert is_service_cmd(command) is True


def test_market_research_is_locked_as_internal_module() -> None:
    baseline = Path("docs/baseline/MARKET_RESEARCH_MODULE_BASELINE.md").read_text(encoding="utf-8")

    assert "Status: LOCKED" in baseline
    assert "current app" in baseline
    assert "separate public domain" in baseline
    assert "YouTube Research" in baseline

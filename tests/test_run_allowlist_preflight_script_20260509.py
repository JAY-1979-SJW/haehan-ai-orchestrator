"""run_allowlist_preflight 스크립트 단위 테스트."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pytest
from build_discovery_candidates_from_fixture import build_candidates, load_fixture
from run_allowlist_preflight import run_preflight, summarize

from ai_orchestrator.local_agent.browser_allowlist_expansion_preflight import (
    VERDICT_ALLOW,
)
from ai_orchestrator.local_agent.browser_site_registry import SitePolicy, clear_all, register_site


@pytest.fixture(autouse=True)
def _setup():
    clear_all()
    register_site(
        SitePolicy(
            site_id="g2b",
            label="조달청",
            allowed_hosts=("www.g2b.go.kr",),
        )
    )
    yield
    clear_all()


def _make_candidates_data(site_id: str) -> dict:
    items = load_fixture(site_id, None)
    results = build_candidates(site_id, items)
    return {"site_id": site_id, "candidates": results}


def test_preflight_returns_results(tmp_path):
    data = _make_candidates_data("g2b")
    candidates_file = tmp_path / "c.json"
    import json

    candidates_file.write_text(json.dumps(data), encoding="utf-8")
    results = run_preflight("g2b", candidates_file)
    assert len(results) > 0


def test_preflight_allow_register_exists(tmp_path):
    data = _make_candidates_data("g2b")
    candidates_file = tmp_path / "c.json"
    import json

    candidates_file.write_text(json.dumps(data), encoding="utf-8")
    results = run_preflight("g2b", candidates_file)
    allowed = [r for r in results if r["verdict"] == VERDICT_ALLOW]
    assert len(allowed) > 0


def test_preflight_summary_counts_match(tmp_path):
    data = _make_candidates_data("g2b")
    candidates_file = tmp_path / "c.json"
    import json

    candidates_file.write_text(json.dumps(data), encoding="utf-8")
    results = run_preflight("g2b", candidates_file)
    summary = summarize(results)
    assert summary["total"] == len(results)
    assert summary["allow"] + summary["review"] + summary["blocked"] == summary["total"]

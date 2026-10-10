"""tests/test_universal_ai_real_site_smoke_contract_20260508.py"""

from core.agent_runtime.runtime.universal.real_site_smoke_runner import (
    _SMOKE_SCENARIOS,
    is_safe_readonly_target,
    run_all_smoke_scenarios,
    run_smoke_scenario,
)


def _dummy(action, domain="", **kwargs):
    return {"ok": True, "action": action}


def test_smoke_scenarios_count():
    assert len(_SMOKE_SCENARIOS) >= 7


def test_each_scenario_has_required_keys():
    required = {"scenario_id", "description", "instruction", "mock_page", "expected_status"}
    for sc in _SMOKE_SCENARIOS:
        missing = required - set(sc.keys())
        assert not missing, f"{sc['scenario_id']} 누락 키: {missing}"


def test_mock_page_has_required_fields():
    page_fields = {"url", "title", "text_content", "buttons", "links", "form_labels", "heading_texts"}
    for sc in _SMOKE_SCENARIOS:
        missing = page_fields - set(sc["mock_page"].keys())
        assert not missing, f"{sc['scenario_id']} mock_page 누락: {missing}"


def test_run_all_returns_summary_structure():
    summary = run_all_smoke_scenarios(runner_fn=_dummy, dry_run=True)
    assert "total" in summary
    assert "passed" in summary
    assert "failed" in summary
    assert "all_passed" in summary
    assert "results" in summary
    assert summary["server_browser_used"] is False


def test_run_all_total_matches_scenarios():
    summary = run_all_smoke_scenarios(runner_fn=_dummy, dry_run=True)
    assert summary["total"] == len(_SMOKE_SCENARIOS)


def test_run_all_all_passed():
    summary = run_all_smoke_scenarios(runner_fn=_dummy, dry_run=True)
    assert summary["all_passed"], f"실패 시나리오: {[r for r in summary['results'] if not r['passed']]}"


def test_run_all_server_browser_used_false():
    summary = run_all_smoke_scenarios(runner_fn=_dummy, dry_run=True)
    assert summary["server_browser_used"] is False


def test_each_result_has_scenario_id():
    summary = run_all_smoke_scenarios(runner_fn=_dummy, dry_run=True)
    for r in summary["results"]:
        assert "scenario_id" in r
        assert "passed" in r
        assert "violations" in r


def test_each_result_no_violations():
    summary = run_all_smoke_scenarios(runner_fn=_dummy, dry_run=True)
    for r in summary["results"]:
        assert r["violations"] == [], f"{r['scenario_id']} 위반: {r['violations']}"


def test_run_smoke_scenario_single():
    sc = _SMOKE_SCENARIOS[0]
    result = run_smoke_scenario(sc, runner_fn=_dummy, dry_run=True)
    assert result.scenario_id == sc["scenario_id"]
    assert result.passed is True


def test_is_safe_readonly_target_allowed():
    assert is_safe_readonly_target("https://quotes.toscrape.com/") is True
    assert is_safe_readonly_target("https://example.com/page") is True


def test_is_safe_readonly_target_blocked_gov():
    assert is_safe_readonly_target("https://www.go.kr/") is False


def test_is_safe_readonly_target_blocked_g2b():
    assert is_safe_readonly_target("https://www.g2b.go.kr/") is False


def test_is_safe_readonly_target_blocked_bank():
    assert is_safe_readonly_target("https://mybank.co.kr/login") is False

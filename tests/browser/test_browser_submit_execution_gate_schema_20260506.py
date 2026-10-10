"""
Browser Submit Execution Gate - Schema / Design Tests
BROWSER_SUBMIT_EXECUTION_GATE_DESIGN_1 (정정: ALIGNMENT_1)

Tests verify:
- ExecutionGateInput schema contracts
- ExecutionGateResult schema contracts (controlled_submit_allowed / production_submit_allowed 분리)
- BlockReason taxonomy completeness
- Fixture consistency
- GATE_ALLOW_CONTROLLED vs GATE_BLOCK 분리 원칙

Design-phase tests only.
No actual gate module imported. No network, DB, or file I/O outside fixture loading.
"""

import json
from pathlib import Path

import pytest

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "browser_submit_execution_gate_fixture_20260506.json"


@pytest.fixture(scope="module")
def fixture_data():
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _all_gate_cases(fixture_data):
    return [k for k in fixture_data if k.startswith("gate_")]


# ---------------------------------------------------------------------------
# ExecutionGateInput schema
# ---------------------------------------------------------------------------


class TestExecutionGateInputSchema:
    REQUIRED_FIELDS = [
        "policy_verdict",
        "preview_hash",
        "validation_id",
        "risk_level",
        "approval_status",
        "controlled_submit_result",
        "audit_logged",
        "production_submit_enabled",
    ]

    OPTIONAL_FIELDS = ["submitted_by", "site_id", "form_id"]

    def test_gate_pass_case_has_all_required_fields(self, fixture_data):
        inp = fixture_data["gate_pass_case"]["input"]
        for field in self.REQUIRED_FIELDS:
            assert field in inp, f"Required field missing: {field}"

    def test_policy_verdict_is_string(self, fixture_data):
        assert isinstance(fixture_data["gate_pass_case"]["input"]["policy_verdict"], str)

    def test_preview_hash_is_string(self, fixture_data):
        assert isinstance(fixture_data["gate_pass_case"]["input"]["preview_hash"], str)

    def test_validation_id_is_string(self, fixture_data):
        assert isinstance(fixture_data["gate_pass_case"]["input"]["validation_id"], str)

    def test_risk_level_is_string(self, fixture_data):
        assert isinstance(fixture_data["gate_pass_case"]["input"]["risk_level"], str)

    def test_approval_status_is_string(self, fixture_data):
        assert isinstance(fixture_data["gate_pass_case"]["input"]["approval_status"], str)

    def test_controlled_submit_result_is_string(self, fixture_data):
        assert isinstance(fixture_data["gate_pass_case"]["input"]["controlled_submit_result"], str)

    def test_audit_logged_is_bool(self, fixture_data):
        assert isinstance(fixture_data["gate_pass_case"]["input"]["audit_logged"], bool)

    def test_production_submit_enabled_is_bool(self, fixture_data):
        assert isinstance(fixture_data["gate_pass_case"]["input"]["production_submit_enabled"], bool)

    def test_optional_fields_are_strings_when_present(self, fixture_data):
        inp = fixture_data["gate_pass_case"]["input"]
        for field in self.OPTIONAL_FIELDS:
            if field in inp:
                assert isinstance(inp[field], str)


# ---------------------------------------------------------------------------
# ExecutionGateResult schema
# ---------------------------------------------------------------------------


class TestExecutionGateResultSchema:
    REQUIRED_FIELDS = [
        "gate_verdict",
        "controlled_submit_allowed",
        "production_submit_allowed",
        "block_reasons",
        "production_submit_enabled",
    ]

    def test_all_cases_have_required_output_fields(self, fixture_data):
        for case_key in _all_gate_cases(fixture_data):
            output = fixture_data[case_key]["expected_output"]
            for field in self.REQUIRED_FIELDS:
                assert field in output, f"{case_key}.expected_output missing: {field}"

    def test_gate_verdict_values_are_valid(self, fixture_data):
        valid_verdicts = {"GATE_PASS", "GATE_ALLOW_CONTROLLED", "GATE_BLOCK"}
        for case_key in _all_gate_cases(fixture_data):
            verdict = fixture_data[case_key]["expected_output"]["gate_verdict"]
            assert verdict in valid_verdicts, f"{case_key}: invalid gate_verdict={verdict!r}"

    def test_controlled_submit_allowed_is_bool(self, fixture_data):
        for case_key in _all_gate_cases(fixture_data):
            val = fixture_data[case_key]["expected_output"]["controlled_submit_allowed"]
            assert isinstance(val, bool), f"{case_key}: controlled_submit_allowed must be bool"

    def test_production_submit_allowed_is_bool(self, fixture_data):
        for case_key in _all_gate_cases(fixture_data):
            val = fixture_data[case_key]["expected_output"]["production_submit_allowed"]
            assert isinstance(val, bool), f"{case_key}: production_submit_allowed must be bool"

    def test_block_reasons_is_list(self, fixture_data):
        for case_key in _all_gate_cases(fixture_data):
            assert isinstance(fixture_data[case_key]["expected_output"]["block_reasons"], list)

    def test_production_submit_enabled_is_bool_in_output(self, fixture_data):
        for case_key in _all_gate_cases(fixture_data):
            val = fixture_data[case_key]["expected_output"]["production_submit_enabled"]
            assert isinstance(val, bool)

    def test_gate_pass_flags(self, fixture_data):
        out = fixture_data["gate_pass_case"]["expected_output"]
        assert out["gate_verdict"] == "GATE_PASS"
        assert out["controlled_submit_allowed"] is True
        assert out["production_submit_allowed"] is True
        assert out["block_reasons"] == []

    def test_gate_allow_controlled_flags(self, fixture_data):
        out = fixture_data["gate_allow_controlled_case"]["expected_output"]
        assert out["gate_verdict"] == "GATE_ALLOW_CONTROLLED"
        assert out["controlled_submit_allowed"] is True
        assert out["production_submit_allowed"] is False
        assert out["block_reasons"] == []

    def test_gate_block_flags(self, fixture_data):
        block_cases = [k for k in fixture_data if k.startswith("gate_block")]
        for case_key in block_cases:
            out = fixture_data[case_key]["expected_output"]
            assert out["gate_verdict"] == "GATE_BLOCK", f"{case_key}: expected GATE_BLOCK"
            assert out["controlled_submit_allowed"] is False
            assert out["production_submit_allowed"] is False
            assert len(out["block_reasons"]) > 0


# ---------------------------------------------------------------------------
# Separation principle: production_submit_enabled does NOT cause GATE_BLOCK
# ---------------------------------------------------------------------------


class TestProductionSubmitSeparation:
    def test_production_disabled_does_not_cause_gate_block(self, fixture_data):
        """production_submit_enabled=false → GATE_ALLOW_CONTROLLED (not GATE_BLOCK) when core conditions pass."""
        out = fixture_data["gate_allow_controlled_case"]["expected_output"]
        assert out["gate_verdict"] == "GATE_ALLOW_CONTROLLED"
        assert "PRODUCTION_DISABLED" not in out["block_reasons"]

    def test_production_disabled_blocks_production_only(self, fixture_data):
        out = fixture_data["gate_allow_controlled_case"]["expected_output"]
        assert out["production_submit_allowed"] is False
        assert out["controlled_submit_allowed"] is True

    def test_multiple_block_does_not_include_production_disabled(self, fixture_data):
        """복합 GATE_BLOCK 케이스: block_reasons에 PRODUCTION_DISABLED 없음 (핵심 6개 조건만)."""
        reasons = fixture_data["gate_block_multiple"]["expected_output"]["block_reasons"]
        assert "PRODUCTION_DISABLED" not in reasons

    def test_gate_block_sets_both_allowed_to_false(self, fixture_data):
        """GATE_BLOCK이면 controlled와 production 모두 False."""
        block_cases = [k for k in fixture_data if k.startswith("gate_block")]
        for case_key in block_cases:
            out = fixture_data[case_key]["expected_output"]
            assert out["controlled_submit_allowed"] is False
            assert out["production_submit_allowed"] is False


# ---------------------------------------------------------------------------
# BlockReason taxonomy (핵심 6종 — PRODUCTION_DISABLED는 block_reasons에 없음)
# ---------------------------------------------------------------------------


class TestBlockReasonTaxonomy:
    CORE_BLOCK_REASONS = [
        "POLICY_NOT_ALLOW",
        "PREVIEW_HASH_MISSING",
        "VALIDATION_ID_MISSING",
        "APPROVAL_NOT_APPROVED",
        "CONTROLLED_SUBMIT_NOT_SUCCESS",
        "AUDIT_NOT_LOGGED",
    ]

    def test_all_core_block_reasons_present_in_multiple_case(self, fixture_data):
        reasons = fixture_data["gate_block_multiple"]["expected_output"]["block_reasons"]
        for reason in self.CORE_BLOCK_REASONS:
            assert reason in reasons, f"Core BlockReason missing from multiple case: {reason}"

    def test_each_core_reason_has_dedicated_fixture_case(self, fixture_data):
        reason_to_case = {
            "POLICY_NOT_ALLOW": "gate_block_policy_not_allow",
            "PREVIEW_HASH_MISSING": "gate_block_preview_hash_missing",
            "VALIDATION_ID_MISSING": "gate_block_validation_id_missing",
            "APPROVAL_NOT_APPROVED": "gate_block_approval_pending",
            "CONTROLLED_SUBMIT_NOT_SUCCESS": "gate_block_controlled_submit_not_success",
            "AUDIT_NOT_LOGGED": "gate_block_audit_not_logged",
        }
        for reason, case_key in reason_to_case.items():
            assert case_key in fixture_data, f"Missing fixture case for {reason}: {case_key}"
            reasons = fixture_data[case_key]["expected_output"]["block_reasons"]
            assert reason in reasons, f"{reason} not in {case_key}.block_reasons"

    def test_block_reasons_are_strings(self, fixture_data):
        block_cases = [k for k in fixture_data if k.startswith("gate_block")]
        for case_key in block_cases:
            for reason in fixture_data[case_key]["expected_output"]["block_reasons"]:
                assert isinstance(reason, str)

    def test_no_production_disabled_in_any_block_reasons(self, fixture_data):
        """PRODUCTION_DISABLED는 block_reasons에 포함되지 않는다 — gate_verdict 결정 경로와 분리."""
        for case_key in _all_gate_cases(fixture_data):
            reasons = fixture_data[case_key]["expected_output"]["block_reasons"]
            assert "PRODUCTION_DISABLED" not in reasons, (
                f"{case_key}: PRODUCTION_DISABLED must not appear in block_reasons"
            )

    def test_no_unknown_block_reasons_in_fixture(self, fixture_data):
        known = set(self.CORE_BLOCK_REASONS)
        block_cases = [k for k in fixture_data if k.startswith("gate_block")]
        for case_key in block_cases:
            for reason in fixture_data[case_key]["expected_output"]["block_reasons"]:
                assert reason in known, f"Unknown BlockReason in {case_key}: {reason!r}"


# ---------------------------------------------------------------------------
# Fixture consistency
# ---------------------------------------------------------------------------


class TestFixtureConsistency:
    def test_fixture_version(self, fixture_data):
        assert fixture_data["version"] == "1.1"

    def test_production_submit_enabled_input_matches_output(self, fixture_data):
        for case_key in _all_gate_cases(fixture_data):
            inp = fixture_data[case_key]["input"]
            out = fixture_data[case_key]["expected_output"]
            assert inp["production_submit_enabled"] == out["production_submit_enabled"], (
                f"{case_key}: production_submit_enabled mismatch"
            )

    def test_gate_pass_requires_production_enabled_true(self, fixture_data):
        inp = fixture_data["gate_pass_case"]["input"]
        assert inp["production_submit_enabled"] is True

    def test_gate_allow_controlled_requires_production_enabled_false(self, fixture_data):
        for case_key in [k for k in fixture_data if k.startswith("gate_allow_controlled")]:
            inp = fixture_data[case_key]["input"]
            assert inp["production_submit_enabled"] is False, (
                f"{case_key}: GATE_ALLOW_CONTROLLED should have production_submit_enabled=false"
            )

    def test_multiple_block_has_six_core_reasons(self, fixture_data):
        reasons = fixture_data["gate_block_multiple"]["expected_output"]["block_reasons"]
        assert len(reasons) == 6

    def test_fixture_gate_cases_count(self, fixture_data):
        gate_cases = [k for k in fixture_data if k.startswith("gate_")]
        assert len(gate_cases) == 11, f"Expected 11 gate cases, found {len(gate_cases)}"

    def test_allow_controlled_high_risk_case_present(self, fixture_data):
        assert "gate_allow_controlled_high_risk" in fixture_data
        out = fixture_data["gate_allow_controlled_high_risk"]["expected_output"]
        assert out["gate_verdict"] == "GATE_ALLOW_CONTROLLED"
        assert out["controlled_submit_allowed"] is True

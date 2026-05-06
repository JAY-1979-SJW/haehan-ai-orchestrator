"""
Browser Submit Execution Gate - Schema / Design Tests
BROWSER_SUBMIT_EXECUTION_GATE_DESIGN_1

Tests verify:
- ExecutionGateInput schema contracts
- ExecutionGateResult schema contracts
- BlockReason taxonomy completeness
- Fixture consistency

These are design-phase tests only.
No actual gate module is imported; all assertions use fixture data and schema rules.
No network, DB, or file I/O outside of fixture loading.
"""

import json
import pytest
from pathlib import Path


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "browser_submit_execution_gate_fixture_20260506.json"


@pytest.fixture(scope="module")
def fixture_data():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


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
        inp = fixture_data["gate_pass_case"]["input"]
        assert isinstance(inp["policy_verdict"], str)

    def test_preview_hash_is_string(self, fixture_data):
        inp = fixture_data["gate_pass_case"]["input"]
        assert isinstance(inp["preview_hash"], str)

    def test_validation_id_is_string(self, fixture_data):
        inp = fixture_data["gate_pass_case"]["input"]
        assert isinstance(inp["validation_id"], str)

    def test_risk_level_is_string(self, fixture_data):
        inp = fixture_data["gate_pass_case"]["input"]
        assert isinstance(inp["risk_level"], str)

    def test_approval_status_is_string(self, fixture_data):
        inp = fixture_data["gate_pass_case"]["input"]
        assert isinstance(inp["approval_status"], str)

    def test_controlled_submit_result_is_string(self, fixture_data):
        inp = fixture_data["gate_pass_case"]["input"]
        assert isinstance(inp["controlled_submit_result"], str)

    def test_audit_logged_is_bool(self, fixture_data):
        inp = fixture_data["gate_pass_case"]["input"]
        assert isinstance(inp["audit_logged"], bool)

    def test_production_submit_enabled_is_bool(self, fixture_data):
        inp = fixture_data["gate_pass_case"]["input"]
        assert isinstance(inp["production_submit_enabled"], bool)

    def test_optional_fields_are_strings(self, fixture_data):
        inp = fixture_data["gate_pass_case"]["input"]
        for field in self.OPTIONAL_FIELDS:
            if field in inp:
                assert isinstance(inp[field], str), f"{field} should be string"


# ---------------------------------------------------------------------------
# ExecutionGateResult schema
# ---------------------------------------------------------------------------

class TestExecutionGateResultSchema:

    REQUIRED_FIELDS = [
        "gate_verdict",
        "block_reasons",
        "production_submit_enabled",
    ]

    def _get_all_outputs(self, fixture_data):
        cases = [k for k in fixture_data if k not in ("version", "description", "created_at", "note")]
        return [fixture_data[case]["expected_output"] for case in cases]

    def test_all_cases_have_required_output_fields(self, fixture_data):
        for output in self._get_all_outputs(fixture_data):
            for field in self.REQUIRED_FIELDS:
                assert field in output, f"Output missing required field: {field}"

    def test_gate_verdict_values_are_valid(self, fixture_data):
        valid_verdicts = {"GATE_PASS", "GATE_BLOCK"}
        for output in self._get_all_outputs(fixture_data):
            assert output["gate_verdict"] in valid_verdicts

    def test_block_reasons_is_list(self, fixture_data):
        for output in self._get_all_outputs(fixture_data):
            assert isinstance(output["block_reasons"], list)

    def test_production_submit_enabled_is_bool_in_output(self, fixture_data):
        for output in self._get_all_outputs(fixture_data):
            assert isinstance(output["production_submit_enabled"], bool)

    def test_gate_pass_has_empty_block_reasons(self, fixture_data):
        output = fixture_data["gate_pass_case"]["expected_output"]
        assert output["gate_verdict"] == "GATE_PASS"
        assert output["block_reasons"] == []

    def test_gate_block_has_nonempty_block_reasons(self, fixture_data):
        block_cases = [k for k in fixture_data if k.startswith("gate_block")]
        for case_key in block_cases:
            output = fixture_data[case_key]["expected_output"]
            assert output["gate_verdict"] == "GATE_BLOCK"
            assert len(output["block_reasons"]) > 0, f"GATE_BLOCK case {case_key} has empty block_reasons"


# ---------------------------------------------------------------------------
# BlockReason taxonomy
# ---------------------------------------------------------------------------

class TestBlockReasonTaxonomy:

    EXPECTED_BLOCK_REASONS = [
        "POLICY_NOT_ALLOW",
        "PREVIEW_HASH_MISSING",
        "VALIDATION_ID_MISSING",
        "APPROVAL_NOT_APPROVED",
        "CONTROLLED_SUBMIT_NOT_SUCCESS",
        "AUDIT_NOT_LOGGED",
        "PRODUCTION_DISABLED",
    ]

    def test_all_block_reasons_present_in_multiple_case(self, fixture_data):
        all_reasons = fixture_data["gate_block_multiple"]["expected_output"]["block_reasons"]
        for reason in self.EXPECTED_BLOCK_REASONS:
            assert reason in all_reasons, f"BlockReason not in multiple case: {reason}"

    def test_each_block_reason_has_dedicated_fixture_case(self, fixture_data):
        reason_to_case = {
            "POLICY_NOT_ALLOW": "gate_block_policy_not_allow",
            "PREVIEW_HASH_MISSING": "gate_block_preview_hash_missing",
            "VALIDATION_ID_MISSING": "gate_block_validation_id_missing",
            "APPROVAL_NOT_APPROVED": "gate_block_approval_pending",
            "CONTROLLED_SUBMIT_NOT_SUCCESS": "gate_block_controlled_submit_not_success",
            "AUDIT_NOT_LOGGED": "gate_block_audit_not_logged",
            "PRODUCTION_DISABLED": "gate_block_production_disabled",
        }
        for reason, case_key in reason_to_case.items():
            assert case_key in fixture_data, f"Missing fixture case for {reason}: {case_key}"
            block_reasons = fixture_data[case_key]["expected_output"]["block_reasons"]
            assert reason in block_reasons, f"{reason} not in {case_key}.block_reasons"

    def test_block_reasons_are_strings(self, fixture_data):
        block_cases = [k for k in fixture_data if k.startswith("gate_block")]
        for case_key in block_cases:
            for reason in fixture_data[case_key]["expected_output"]["block_reasons"]:
                assert isinstance(reason, str), f"BlockReason is not str in {case_key}: {reason!r}"

    def test_no_unknown_block_reasons_in_fixture(self, fixture_data):
        known = set(self.EXPECTED_BLOCK_REASONS)
        block_cases = [k for k in fixture_data if k.startswith("gate_block")]
        for case_key in block_cases:
            for reason in fixture_data[case_key]["expected_output"]["block_reasons"]:
                assert reason in known, f"Unknown BlockReason in {case_key}: {reason!r}"


# ---------------------------------------------------------------------------
# Fixture consistency
# ---------------------------------------------------------------------------

class TestFixtureConsistency:

    def test_fixture_has_version_field(self, fixture_data):
        assert "version" in fixture_data
        assert fixture_data["version"] == "1.0"

    def test_production_disabled_input_matches_output(self, fixture_data):
        for case_key in [k for k in fixture_data if k.startswith("gate_")]:
            inp = fixture_data[case_key]["input"]
            out = fixture_data[case_key]["expected_output"]
            assert inp["production_submit_enabled"] == out["production_submit_enabled"], (
                f"production_submit_enabled mismatch in {case_key}"
            )

    def test_gate_pass_requires_production_enabled(self, fixture_data):
        out = fixture_data["gate_pass_case"]["expected_output"]
        inp = fixture_data["gate_pass_case"]["input"]
        assert out["gate_verdict"] == "GATE_PASS"
        assert inp["production_submit_enabled"] is True

    def test_all_block_cases_have_production_disabled_or_other_reason(self, fixture_data):
        block_cases = [k for k in fixture_data if k.startswith("gate_block")]
        for case_key in block_cases:
            output = fixture_data[case_key]["expected_output"]
            assert len(output["block_reasons"]) >= 1

    def test_multiple_block_case_has_all_seven_reasons(self, fixture_data):
        reasons = fixture_data["gate_block_multiple"]["expected_output"]["block_reasons"]
        assert len(reasons) == 7

    def test_production_disabled_is_first_reason_in_multiple_block(self, fixture_data):
        reasons = fixture_data["gate_block_multiple"]["expected_output"]["block_reasons"]
        assert reasons[0] == "PRODUCTION_DISABLED"

    def test_fixture_gate_cases_count(self, fixture_data):
        gate_cases = [k for k in fixture_data if k.startswith("gate_")]
        assert len(gate_cases) == 10, f"Expected 10 gate cases, found {len(gate_cases)}"

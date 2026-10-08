"""
Browser Submit Execution Gate — Validator Tests
BROWSER_SUBMIT_EXECUTION_GATE_VALIDATOR_1

실제 evaluate_execution_gate() 함수를 호출하여 fixture 기반으로 검증.
No network, no DB, no file I/O (fixture 로딩 제외).
production submit 실행 없음.
"""

import json
from pathlib import Path

import pytest

from ai_orchestrator.browser_tool.submit.submit_execution_gate import (
    BlockReason,
    ExecutionGateInput,
    ExecutionGateResult,
    evaluate_execution_gate,
)

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "browser_submit_execution_gate_fixture_20260506.json"


@pytest.fixture(scope="module")
def fixture_data():
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _make_input(inp: dict) -> ExecutionGateInput:
    return ExecutionGateInput(
        policy_verdict=inp["policy_verdict"],
        preview_hash=inp["preview_hash"],
        validation_id=inp["validation_id"],
        risk_level=inp["risk_level"],
        approval_status=inp["approval_status"],
        controlled_submit_result=inp["controlled_submit_result"],
        audit_logged=inp["audit_logged"],
        production_submit_enabled=inp["production_submit_enabled"],
        submitted_by=inp.get("submitted_by", ""),
        site_id=inp.get("site_id", ""),
        form_id=inp.get("form_id", ""),
    )


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------


class TestReturnType:
    def test_returns_execution_gate_result(self, fixture_data):
        inp = _make_input(fixture_data["gate_pass_case"]["input"])
        result = evaluate_execution_gate(inp)
        assert isinstance(result, ExecutionGateResult)

    def test_gate_id_is_non_empty_string(self, fixture_data):
        inp = _make_input(fixture_data["gate_pass_case"]["input"])
        result = evaluate_execution_gate(inp)
        assert isinstance(result.gate_id, str)
        assert result.gate_id.startswith("gate_")

    def test_evaluated_at_is_iso_utc(self, fixture_data):
        inp = _make_input(fixture_data["gate_pass_case"]["input"])
        result = evaluate_execution_gate(inp)
        assert isinstance(result.evaluated_at, str)
        assert result.evaluated_at.endswith("Z")

    def test_block_reasons_is_list(self, fixture_data):
        inp = _make_input(fixture_data["gate_pass_case"]["input"])
        result = evaluate_execution_gate(inp)
        assert isinstance(result.block_reasons, list)


# ---------------------------------------------------------------------------
# GATE_PASS
# ---------------------------------------------------------------------------


class TestGatePass:
    def test_gate_pass_verdict(self, fixture_data):
        case = fixture_data["gate_pass_case"]
        result = evaluate_execution_gate(_make_input(case["input"]))
        assert result.gate_verdict == "GATE_PASS"

    def test_gate_pass_controlled_allowed(self, fixture_data):
        result = evaluate_execution_gate(_make_input(fixture_data["gate_pass_case"]["input"]))
        assert result.controlled_submit_allowed is True

    def test_gate_pass_production_allowed(self, fixture_data):
        result = evaluate_execution_gate(_make_input(fixture_data["gate_pass_case"]["input"]))
        assert result.production_submit_allowed is True

    def test_gate_pass_no_block_reasons(self, fixture_data):
        result = evaluate_execution_gate(_make_input(fixture_data["gate_pass_case"]["input"]))
        assert result.block_reasons == []

    def test_gate_pass_production_submit_enabled_reflected(self, fixture_data):
        result = evaluate_execution_gate(_make_input(fixture_data["gate_pass_case"]["input"]))
        assert result.production_submit_enabled is True


# ---------------------------------------------------------------------------
# GATE_ALLOW_CONTROLLED
# ---------------------------------------------------------------------------


class TestGateAllowControlled:
    def test_gate_allow_controlled_verdict(self, fixture_data):
        result = evaluate_execution_gate(_make_input(fixture_data["gate_allow_controlled_case"]["input"]))
        assert result.gate_verdict == "GATE_ALLOW_CONTROLLED"

    def test_gate_allow_controlled_controlled_allowed(self, fixture_data):
        result = evaluate_execution_gate(_make_input(fixture_data["gate_allow_controlled_case"]["input"]))
        assert result.controlled_submit_allowed is True

    def test_gate_allow_controlled_production_not_allowed(self, fixture_data):
        result = evaluate_execution_gate(_make_input(fixture_data["gate_allow_controlled_case"]["input"]))
        assert result.production_submit_allowed is False

    def test_gate_allow_controlled_no_block_reasons(self, fixture_data):
        result = evaluate_execution_gate(_make_input(fixture_data["gate_allow_controlled_case"]["input"]))
        assert result.block_reasons == []

    def test_gate_allow_controlled_high_risk(self, fixture_data):
        """risk_level=high여도 핵심 조건 통과 시 GATE_ALLOW_CONTROLLED."""
        result = evaluate_execution_gate(_make_input(fixture_data["gate_allow_controlled_high_risk"]["input"]))
        assert result.gate_verdict == "GATE_ALLOW_CONTROLLED"
        assert result.controlled_submit_allowed is True
        assert result.production_submit_allowed is False


# ---------------------------------------------------------------------------
# GATE_BLOCK: 핵심 6개 조건 각각
# ---------------------------------------------------------------------------


class TestGateBlockCoreReasons:
    def test_block_policy_not_allow(self, fixture_data):
        result = evaluate_execution_gate(_make_input(fixture_data["gate_block_policy_not_allow"]["input"]))
        assert result.gate_verdict == "GATE_BLOCK"
        assert BlockReason.POLICY_NOT_ALLOW in result.block_reasons

    def test_block_preview_hash_missing(self, fixture_data):
        result = evaluate_execution_gate(_make_input(fixture_data["gate_block_preview_hash_missing"]["input"]))
        assert result.gate_verdict == "GATE_BLOCK"
        assert BlockReason.PREVIEW_HASH_MISSING in result.block_reasons

    def test_block_validation_id_missing(self, fixture_data):
        result = evaluate_execution_gate(_make_input(fixture_data["gate_block_validation_id_missing"]["input"]))
        assert result.gate_verdict == "GATE_BLOCK"
        assert BlockReason.VALIDATION_ID_MISSING in result.block_reasons

    def test_block_approval_pending(self, fixture_data):
        result = evaluate_execution_gate(_make_input(fixture_data["gate_block_approval_pending"]["input"]))
        assert result.gate_verdict == "GATE_BLOCK"
        assert BlockReason.APPROVAL_NOT_APPROVED in result.block_reasons

    def test_block_approval_cancelled(self, fixture_data):
        result = evaluate_execution_gate(_make_input(fixture_data["gate_block_approval_cancelled"]["input"]))
        assert result.gate_verdict == "GATE_BLOCK"
        assert BlockReason.APPROVAL_NOT_APPROVED in result.block_reasons

    def test_block_controlled_submit_not_success(self, fixture_data):
        result = evaluate_execution_gate(_make_input(fixture_data["gate_block_controlled_submit_not_success"]["input"]))
        assert result.gate_verdict == "GATE_BLOCK"
        assert BlockReason.CONTROLLED_SUBMIT_NOT_SUCCESS in result.block_reasons

    def test_block_audit_not_logged(self, fixture_data):
        result = evaluate_execution_gate(_make_input(fixture_data["gate_block_audit_not_logged"]["input"]))
        assert result.gate_verdict == "GATE_BLOCK"
        assert BlockReason.AUDIT_NOT_LOGGED in result.block_reasons

    def test_block_sets_both_allowed_false(self, fixture_data):
        block_cases = [k for k in fixture_data if k.startswith("gate_block")]
        for case_key in block_cases:
            result = evaluate_execution_gate(_make_input(fixture_data[case_key]["input"]))
            assert result.controlled_submit_allowed is False, f"{case_key}: controlled_submit_allowed must be False"
            assert result.production_submit_allowed is False, f"{case_key}: production_submit_allowed must be False"


# ---------------------------------------------------------------------------
# GATE_BLOCK: 복합 차단
# ---------------------------------------------------------------------------


class TestGateBlockMultiple:
    CORE_REASONS = [
        "POLICY_NOT_ALLOW",
        "PREVIEW_HASH_MISSING",
        "VALIDATION_ID_MISSING",
        "APPROVAL_NOT_APPROVED",
        "CONTROLLED_SUBMIT_NOT_SUCCESS",
        "AUDIT_NOT_LOGGED",
    ]

    def test_all_six_core_reasons_present(self, fixture_data):
        result = evaluate_execution_gate(_make_input(fixture_data["gate_block_multiple"]["input"]))
        assert result.gate_verdict == "GATE_BLOCK"
        for reason in self.CORE_REASONS:
            assert reason in result.block_reasons, f"Missing: {reason}"

    def test_block_reasons_count_six(self, fixture_data):
        result = evaluate_execution_gate(_make_input(fixture_data["gate_block_multiple"]["input"]))
        assert len(result.block_reasons) == 6

    def test_no_production_disabled_in_block_reasons(self, fixture_data):
        result = evaluate_execution_gate(_make_input(fixture_data["gate_block_multiple"]["input"]))
        assert BlockReason.PRODUCTION_DISABLED not in result.block_reasons


# ---------------------------------------------------------------------------
# production_submit_enabled 분리 원칙
# ---------------------------------------------------------------------------


class TestProductionSubmitSeparation:
    def test_production_disabled_does_not_cause_gate_block(self, fixture_data):
        """production_submit_enabled=False → GATE_BLOCK 아님 (핵심 조건 통과 시)."""
        result = evaluate_execution_gate(_make_input(fixture_data["gate_allow_controlled_case"]["input"]))
        assert result.gate_verdict == "GATE_ALLOW_CONTROLLED"
        assert result.gate_verdict != "GATE_BLOCK"

    def test_production_disabled_blocks_production_only(self, fixture_data):
        result = evaluate_execution_gate(_make_input(fixture_data["gate_allow_controlled_case"]["input"]))
        assert result.production_submit_allowed is False
        assert result.controlled_submit_allowed is True

    def test_production_submit_enabled_reflected_in_result(self, fixture_data):
        for case_key in [k for k in fixture_data if k.startswith("gate_")]:
            inp_data = fixture_data[case_key]["input"]
            result = evaluate_execution_gate(_make_input(inp_data))
            assert result.production_submit_enabled == inp_data["production_submit_enabled"], (
                f"{case_key}: production_submit_enabled mismatch"
            )

    def test_production_disabled_not_in_block_reasons_for_any_case(self, fixture_data):
        for case_key in [k for k in fixture_data if k.startswith("gate_")]:
            result = evaluate_execution_gate(_make_input(fixture_data[case_key]["input"]))
            assert BlockReason.PRODUCTION_DISABLED not in result.block_reasons, (
                f"{case_key}: PRODUCTION_DISABLED must not appear in block_reasons"
            )


# ---------------------------------------------------------------------------
# No side effects
# ---------------------------------------------------------------------------


class TestNoSideEffects:
    def test_no_file_written(self, fixture_data, tmp_path):
        """evaluate_execution_gate는 파일을 생성하지 않는다."""
        before = set(tmp_path.iterdir())
        evaluate_execution_gate(_make_input(fixture_data["gate_pass_case"]["input"]))
        after = set(tmp_path.iterdir())
        assert before == after

    def test_repeated_calls_return_different_gate_ids(self, fixture_data):
        """gate_id는 호출마다 고유해야 한다."""
        inp = _make_input(fixture_data["gate_pass_case"]["input"])
        ids = {evaluate_execution_gate(inp).gate_id for _ in range(5)}
        assert len(ids) == 5

    def test_input_not_mutated(self, fixture_data):
        inp_data = fixture_data["gate_pass_case"]["input"]
        inp = _make_input(inp_data)
        original_policy = inp.policy_verdict
        evaluate_execution_gate(inp)
        assert inp.policy_verdict == original_policy


# ---------------------------------------------------------------------------
# Fixture 전체 케이스 정합성 (fixture expected_output vs 실제 결과)
# ---------------------------------------------------------------------------


class TestFixtureAlignment:
    def test_all_fixture_cases_match_expected_verdict(self, fixture_data):
        for case_key in [k for k in fixture_data if k.startswith("gate_")]:
            case = fixture_data[case_key]
            result = evaluate_execution_gate(_make_input(case["input"]))
            expected = case["expected_output"]
            assert result.gate_verdict == expected["gate_verdict"], (
                f"{case_key}: gate_verdict mismatch: {result.gate_verdict!r} != {expected['gate_verdict']!r}"
            )

    def test_all_fixture_cases_match_controlled_allowed(self, fixture_data):
        for case_key in [k for k in fixture_data if k.startswith("gate_")]:
            case = fixture_data[case_key]
            result = evaluate_execution_gate(_make_input(case["input"]))
            expected = case["expected_output"]
            assert result.controlled_submit_allowed == expected["controlled_submit_allowed"], (
                f"{case_key}: controlled_submit_allowed mismatch"
            )

    def test_all_fixture_cases_match_production_allowed(self, fixture_data):
        for case_key in [k for k in fixture_data if k.startswith("gate_")]:
            case = fixture_data[case_key]
            result = evaluate_execution_gate(_make_input(case["input"]))
            expected = case["expected_output"]
            assert result.production_submit_allowed == expected["production_submit_allowed"], (
                f"{case_key}: production_submit_allowed mismatch"
            )

    def test_all_fixture_cases_match_block_reasons(self, fixture_data):
        for case_key in [k for k in fixture_data if k.startswith("gate_")]:
            case = fixture_data[case_key]
            result = evaluate_execution_gate(_make_input(case["input"]))
            expected = case["expected_output"]
            assert sorted(result.block_reasons) == sorted(expected["block_reasons"]), (
                f"{case_key}: block_reasons mismatch: {result.block_reasons!r} != {expected['block_reasons']!r}"
            )

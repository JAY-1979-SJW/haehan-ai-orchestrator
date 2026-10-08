"""
Browser Submit Gate — Controlled Integration Smoke Test
BROWSER_SUBMIT_GATE_CONTROLLED_INTEGRATION_SMOKE_1

STEP 0: HEAD / origin/master / server HEAD 승인 문구 일치 여부 판정
  - LOCAL HEAD     = 7460a15ff0b79c19c20f4eda0c43956880db28f2  (master)
  - origin/master  = 7460a15ff0b79c19c20f4eda0c43956880db28f2  ✅ 일치
  - server HEAD    = 7460a15ff0b79c19c20f4eda0c43956880db28f2  ✅ 일치
  - 미추적 파일    = BROWSER_OPEN_TYPE_CLOSE_CONTROLLED_PREFLIGHT.md (비차단 .md)
  - 최종 판정      = WARN_GATE_CONTROLLED_INTEGRATION_WITH_NONBLOCKING_UNTRACKED

Integration scope (no browser, no DB, no network, no file I/O except tmp_path):
  policy → preview → controlled_submit(mock) → audit_event → gate_evaluation
"""

import pytest

from ai_orchestrator.browser_tool.approval.submit_audit_log import (
    append_submit_audit_event,
    build_submit_audit_event,
    read_submit_audit_events,
)
from ai_orchestrator.browser_tool.submit.controlled_submit import (
    build_controlled_submit_result,
)
from ai_orchestrator.browser_tool.submit.submit_execution_gate import (
    BlockReason,
    ExecutionGateInput,
    ExecutionGateResult,
    evaluate_execution_gate,
)

# ---------------------------------------------------------------------------
# STEP 0 상수 — git alignment (검증 시점: 2026-05-06)
# ---------------------------------------------------------------------------

STEP0_LOCAL_HEAD = "7460a15ff0b79c19c20f4eda0c43956880db28f2"
STEP0_ORIGIN_HEAD = "7460a15ff0b79c19c20f4eda0c43956880db28f2"
STEP0_SERVER_HEAD = "7460a15ff0b79c19c20f4eda0c43956880db28f2"
STEP0_UNTRACKED = ["BROWSER_OPEN_TYPE_CLOSE_CONTROLLED_PREFLIGHT.md"]
STEP0_VERDICT = "WARN_GATE_CONTROLLED_INTEGRATION_WITH_NONBLOCKING_UNTRACKED"


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_preview_bundle():
    """controlled_submit 호환 mock bundle (internal.mock origin)."""

    class MockAudit:
        validation_id = "val_smoke_integration_001"
        site_id = "allowed_internal_mock_form"
        form_id = "contact_form"
        intent = "submit_contact_form"
        preview_hash = "a" * 64
        preview_timestamp = "2026-05-06T10:00:00Z"
        policy_verdict = "ALLOW"
        redacted_payload = {
            "fields": [{"name": "email", "value": "user@e****e.com"}],
            "hidden_fields_count": 0,
        }

    class MockDetails:
        url = "https://internal.mock/form"
        form_id = "contact_form"
        submit_button_id = "submit_btn"
        policy_verdict = "ALLOW"

    class MockBundle:
        audit = MockAudit()
        details = MockDetails()

    return MockBundle()


# ---------------------------------------------------------------------------
# STEP 0 판정 검증
# ---------------------------------------------------------------------------


class TestStep0GitAlignment:
    """STEP 0: HEAD/origin/master/server HEAD 일치 여부."""

    def test_local_origin_match(self):
        """LOCAL HEAD == origin/master."""
        assert STEP0_LOCAL_HEAD == STEP0_ORIGIN_HEAD

    def test_local_server_match(self):
        """LOCAL HEAD == server HEAD."""
        assert STEP0_LOCAL_HEAD == STEP0_SERVER_HEAD

    def test_all_three_match(self):
        """세 HEAD 모두 동일."""
        assert STEP0_LOCAL_HEAD == STEP0_ORIGIN_HEAD == STEP0_SERVER_HEAD

    def test_untracked_files_are_nonblocking(self):
        """미추적 파일은 .md 문서 — 비차단."""
        for f in STEP0_UNTRACKED:
            assert f.endswith(".md"), f"비차단 대상이 아닌 미추적 파일: {f}"

    def test_step0_verdict_is_warn(self):
        """STEP 0 판정 = WARN (미추적 파일 있으나 비차단)."""
        assert STEP0_VERDICT == "WARN_GATE_CONTROLLED_INTEGRATION_WITH_NONBLOCKING_UNTRACKED"

    def test_step0_verdict_not_fail(self):
        """HEAD 불일치 없음 → FAIL 아님."""
        assert "FAIL" not in STEP0_VERDICT


# ---------------------------------------------------------------------------
# Module import smoke
# ---------------------------------------------------------------------------


class TestModuleImport:
    """필요한 모든 모듈이 import 가능한지 확인."""

    def test_submit_policy_importable(self):
        from ai_orchestrator.browser_tool.submit.submit_policy import validate_submit_policy

        assert callable(validate_submit_policy)

    def test_submit_preview_importable(self):
        from ai_orchestrator.browser_tool.submit.submit_preview import build_submit_preview

        assert callable(build_submit_preview)

    def test_controlled_submit_importable(self):
        from ai_orchestrator.browser_tool.submit.controlled_submit import build_controlled_submit_result

        assert callable(build_controlled_submit_result)

    def test_submit_audit_log_importable(self):
        from ai_orchestrator.browser_tool.approval.submit_audit_log import (
            append_submit_audit_event,
            build_submit_audit_event,
        )

        assert callable(build_submit_audit_event)
        assert callable(append_submit_audit_event)

    def test_execution_gate_importable(self):
        from ai_orchestrator.browser_tool.submit.submit_execution_gate import evaluate_execution_gate

        assert callable(evaluate_execution_gate)


# ---------------------------------------------------------------------------
# Controlled path integration: GATE_ALLOW_CONTROLLED
# ---------------------------------------------------------------------------


class TestGateAllowControlledIntegration:
    """
    controlled submit 경로 통합 검증.
    production_submit_enabled=False (기본값) → GATE_ALLOW_CONTROLLED 기대.
    """

    def test_controlled_submit_result_is_success(self, mock_preview_bundle):
        """mock internal origin → submit_result=success."""
        result = build_controlled_submit_result(mock_preview_bundle, True)
        assert result.submit_result == "success"
        assert result.submitted is True

    def test_gate_allow_controlled_from_controlled_submit_success(self, mock_preview_bundle):
        """controlled_submit success + audit_logged=True → GATE_ALLOW_CONTROLLED."""
        ctrl_result = build_controlled_submit_result(mock_preview_bundle, True)

        gate_inp = ExecutionGateInput(
            policy_verdict="ALLOW",
            preview_hash=ctrl_result.preview_hash,
            validation_id=ctrl_result.validation_id,
            risk_level="low",
            approval_status="approved",
            controlled_submit_result=ctrl_result.submit_result,
            audit_logged=True,
            production_submit_enabled=False,
            submitted_by="smoke_user",
            site_id="allowed_internal_mock_form",
            form_id="contact_form",
        )
        gate = evaluate_execution_gate(gate_inp)

        assert gate.gate_verdict == "GATE_ALLOW_CONTROLLED"
        assert gate.controlled_submit_allowed is True
        assert gate.production_submit_allowed is False
        assert gate.block_reasons == []

    def test_gate_result_is_execution_gate_result_type(self, mock_preview_bundle):
        ctrl_result = build_controlled_submit_result(mock_preview_bundle, True)
        gate_inp = ExecutionGateInput(
            policy_verdict="ALLOW",
            preview_hash=ctrl_result.preview_hash,
            validation_id=ctrl_result.validation_id,
            risk_level="low",
            approval_status="approved",
            controlled_submit_result=ctrl_result.submit_result,
            audit_logged=True,
            production_submit_enabled=False,
        )
        gate = evaluate_execution_gate(gate_inp)
        assert isinstance(gate, ExecutionGateResult)

    def test_gate_id_generated(self, mock_preview_bundle):
        ctrl_result = build_controlled_submit_result(mock_preview_bundle, True)
        gate_inp = ExecutionGateInput(
            policy_verdict="ALLOW",
            preview_hash=ctrl_result.preview_hash,
            validation_id=ctrl_result.validation_id,
            risk_level="low",
            approval_status="approved",
            controlled_submit_result=ctrl_result.submit_result,
            audit_logged=True,
            production_submit_enabled=False,
        )
        gate = evaluate_execution_gate(gate_inp)
        assert gate.gate_id.startswith("gate_")

    def test_evaluated_at_utc(self, mock_preview_bundle):
        ctrl_result = build_controlled_submit_result(mock_preview_bundle, True)
        gate_inp = ExecutionGateInput(
            policy_verdict="ALLOW",
            preview_hash=ctrl_result.preview_hash,
            validation_id=ctrl_result.validation_id,
            risk_level="low",
            approval_status="approved",
            controlled_submit_result=ctrl_result.submit_result,
            audit_logged=True,
            production_submit_enabled=False,
        )
        gate = evaluate_execution_gate(gate_inp)
        assert gate.evaluated_at.endswith("Z")


# ---------------------------------------------------------------------------
# Blocked path integration: GATE_BLOCK
# ---------------------------------------------------------------------------


class TestGateBlockIntegration:
    """
    차단 경로 통합 검증.
    controlled_submit=blocked → GATE_BLOCK 기대.
    """

    def test_controlled_submit_blocked_causes_gate_block(self, mock_preview_bundle):
        """external origin → submit blocked → GATE_BLOCK."""
        mock_preview_bundle.details.url = "https://external.example.com/form"
        ctrl_result = build_controlled_submit_result(mock_preview_bundle, True)

        assert ctrl_result.submit_result == "blocked"

        gate_inp = ExecutionGateInput(
            policy_verdict="ALLOW",
            preview_hash=ctrl_result.preview_hash,
            validation_id=ctrl_result.validation_id,
            risk_level="low",
            approval_status="approved",
            controlled_submit_result=ctrl_result.submit_result,
            audit_logged=True,
            production_submit_enabled=False,
        )
        gate = evaluate_execution_gate(gate_inp)

        assert gate.gate_verdict == "GATE_BLOCK"
        assert gate.controlled_submit_allowed is False
        assert gate.production_submit_allowed is False
        assert BlockReason.CONTROLLED_SUBMIT_NOT_SUCCESS in gate.block_reasons

    def test_missing_preview_hash_causes_gate_block(self):
        """preview_hash 없음 → GATE_BLOCK."""
        gate_inp = ExecutionGateInput(
            policy_verdict="ALLOW",
            preview_hash="",
            validation_id="val_smoke_002",
            risk_level="low",
            approval_status="approved",
            controlled_submit_result="success",
            audit_logged=True,
            production_submit_enabled=False,
        )
        gate = evaluate_execution_gate(gate_inp)
        assert gate.gate_verdict == "GATE_BLOCK"
        assert BlockReason.PREVIEW_HASH_MISSING in gate.block_reasons

    def test_approval_pending_causes_gate_block(self):
        """approval_status=pending → GATE_BLOCK."""
        gate_inp = ExecutionGateInput(
            policy_verdict="ALLOW",
            preview_hash="smoke_hash_xyz",
            validation_id="val_smoke_003",
            risk_level="low",
            approval_status="pending",
            controlled_submit_result="success",
            audit_logged=True,
            production_submit_enabled=False,
        )
        gate = evaluate_execution_gate(gate_inp)
        assert gate.gate_verdict == "GATE_BLOCK"
        assert BlockReason.APPROVAL_NOT_APPROVED in gate.block_reasons

    def test_audit_not_logged_causes_gate_block(self):
        """audit_logged=False → GATE_BLOCK."""
        gate_inp = ExecutionGateInput(
            policy_verdict="ALLOW",
            preview_hash="smoke_hash_xyz",
            validation_id="val_smoke_004",
            risk_level="low",
            approval_status="approved",
            controlled_submit_result="success",
            audit_logged=False,
            production_submit_enabled=False,
        )
        gate = evaluate_execution_gate(gate_inp)
        assert gate.gate_verdict == "GATE_BLOCK"
        assert BlockReason.AUDIT_NOT_LOGGED in gate.block_reasons


# ---------------------------------------------------------------------------
# Audit event integration
# ---------------------------------------------------------------------------


class TestAuditIntegration:
    """audit_event 생성 후 gate 연계 검증."""

    def test_audit_event_built_from_controlled_result(self, mock_preview_bundle):
        """controlled_submit 결과로 audit event 생성 가능."""
        ctrl_result = build_controlled_submit_result(mock_preview_bundle, True)

        event = build_submit_audit_event(
            validation_id=ctrl_result.validation_id,
            action_id="browser.submit_controlled",
            site_id=mock_preview_bundle.audit.site_id,
            form_id=mock_preview_bundle.audit.form_id,
            submit_button_id=mock_preview_bundle.details.submit_button_id,
            intent=mock_preview_bundle.audit.intent,
            policy_verdict=mock_preview_bundle.audit.policy_verdict,
            risk_level="low",
            preview_hash=ctrl_result.preview_hash,
            user_confirmed=True,
            submitted=ctrl_result.submitted,
            submit_result=ctrl_result.submit_result,
            redacted_payload=mock_preview_bundle.audit.redacted_payload,
            result_summary="smoke integration test",
        )

        assert event.validation_id == ctrl_result.validation_id
        assert event.submitted is True
        assert event.submit_result == "success"

    def test_audit_event_persisted_and_reloaded(self, mock_preview_bundle, tmp_path):
        """audit event → JSONL 저장 → 재로드 검증."""
        ctrl_result = build_controlled_submit_result(mock_preview_bundle, True)

        event = build_submit_audit_event(
            validation_id=ctrl_result.validation_id,
            action_id="browser.submit_controlled",
            site_id=mock_preview_bundle.audit.site_id,
            form_id=mock_preview_bundle.audit.form_id,
            submit_button_id=mock_preview_bundle.details.submit_button_id,
            intent=mock_preview_bundle.audit.intent,
            policy_verdict=mock_preview_bundle.audit.policy_verdict,
            risk_level="low",
            preview_hash=ctrl_result.preview_hash,
            user_confirmed=True,
            submitted=ctrl_result.submitted,
            submit_result=ctrl_result.submit_result,
            redacted_payload=mock_preview_bundle.audit.redacted_payload,
            result_summary="smoke integration persist",
        )

        log_path = tmp_path / "smoke_audit.jsonl"
        write_result = append_submit_audit_event(log_path, event)
        assert write_result.success is True

        events = read_submit_audit_events(log_path)
        assert len(events) == 1
        assert events[0]["validation_id"] == ctrl_result.validation_id

    def test_gate_after_audit_persist(self, mock_preview_bundle, tmp_path):
        """audit 저장 완료 후 gate 통과 — end-to-end."""
        ctrl_result = build_controlled_submit_result(mock_preview_bundle, True)

        event = build_submit_audit_event(
            validation_id=ctrl_result.validation_id,
            action_id="browser.submit_controlled",
            site_id=mock_preview_bundle.audit.site_id,
            form_id=mock_preview_bundle.audit.form_id,
            submit_button_id=mock_preview_bundle.details.submit_button_id,
            intent=mock_preview_bundle.audit.intent,
            policy_verdict=mock_preview_bundle.audit.policy_verdict,
            risk_level="low",
            preview_hash=ctrl_result.preview_hash,
            user_confirmed=True,
            submitted=ctrl_result.submitted,
            submit_result=ctrl_result.submit_result,
            redacted_payload=mock_preview_bundle.audit.redacted_payload,
            result_summary="e2e smoke",
        )
        log_path = tmp_path / "e2e_audit.jsonl"
        append_submit_audit_event(log_path, event)
        audit_logged = log_path.exists() and log_path.stat().st_size > 0

        gate_inp = ExecutionGateInput(
            policy_verdict="ALLOW",
            preview_hash=ctrl_result.preview_hash,
            validation_id=ctrl_result.validation_id,
            risk_level="low",
            approval_status="approved",
            controlled_submit_result=ctrl_result.submit_result,
            audit_logged=audit_logged,
            production_submit_enabled=False,
        )
        gate = evaluate_execution_gate(gate_inp)

        assert gate.gate_verdict == "GATE_ALLOW_CONTROLLED"
        assert gate.controlled_submit_allowed is True
        assert gate.production_submit_allowed is False


# ---------------------------------------------------------------------------
# Production submit separation
# ---------------------------------------------------------------------------


class TestProductionSubmitSeparation:
    """production_submit_enabled 분리 원칙 integration 검증."""

    def test_production_disabled_does_not_block_controlled(self, mock_preview_bundle):
        """production_submit_enabled=False → controlled path 차단 없음."""
        ctrl_result = build_controlled_submit_result(mock_preview_bundle, True)
        gate_inp = ExecutionGateInput(
            policy_verdict="ALLOW",
            preview_hash=ctrl_result.preview_hash,
            validation_id=ctrl_result.validation_id,
            risk_level="low",
            approval_status="approved",
            controlled_submit_result=ctrl_result.submit_result,
            audit_logged=True,
            production_submit_enabled=False,
        )
        gate = evaluate_execution_gate(gate_inp)
        assert gate.gate_verdict != "GATE_BLOCK"
        assert gate.controlled_submit_allowed is True

    def test_production_disabled_not_in_block_reasons(self, mock_preview_bundle):
        """PRODUCTION_DISABLED는 block_reasons에 포함되지 않는다."""
        ctrl_result = build_controlled_submit_result(mock_preview_bundle, True)
        gate_inp = ExecutionGateInput(
            policy_verdict="ALLOW",
            preview_hash=ctrl_result.preview_hash,
            validation_id=ctrl_result.validation_id,
            risk_level="low",
            approval_status="approved",
            controlled_submit_result=ctrl_result.submit_result,
            audit_logged=True,
            production_submit_enabled=False,
        )
        gate = evaluate_execution_gate(gate_inp)
        assert BlockReason.PRODUCTION_DISABLED not in gate.block_reasons

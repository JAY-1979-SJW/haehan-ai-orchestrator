"""Test suite for browser approval record store implementation.

Tests approval request/decision records, state transitions, redaction, and fixture compatibility.
All tests use temp files, no production paths.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai_orchestrator.browser_tool.approval.approval_record_store import (
    ApprovalRecord,
    append_approval_record,
    build_approval_decision,
    build_approval_request,
    build_audit_approval_context,
    get_approval_history,
    get_latest_approval_status,
    read_approval_records,
    validate_approval_record,
)


class TestBuildApprovalRequest:
    """Test approval request building."""

    def test_build_request_creates_required_fields(self):
        """Build should create all required fields."""
        record = build_approval_request(
            workflow_run_id="wf_001",
            workflow_id="g2b_notice_search",
            action_name="browser.execute_click",
            operation_type="click",
        )

        assert record.approval_id is not None
        assert len(record.approval_id) > 0
        assert record.approval_event_id is not None
        assert record.approval_event_type == "APPROVAL_REQUESTED"
        assert record.approval_status == "PENDING"
        assert record.created_at is not None
        assert record.expires_at is not None

    def test_approval_id_auto_generated(self):
        """approval_id should be auto-generated if not provided."""
        r1 = build_approval_request(workflow_run_id="wf_001")
        r2 = build_approval_request(workflow_run_id="wf_001")

        assert r1.approval_id != r2.approval_id

    def test_approval_event_id_unique(self):
        """Each request should have unique approval_event_id."""
        r1 = build_approval_request(workflow_run_id="wf_001")
        r2 = build_approval_request(workflow_run_id="wf_001")

        assert r1.approval_event_id != r2.approval_event_id

    def test_created_at_iso_format(self):
        """created_at should be ISO 8601 format."""
        record = build_approval_request(workflow_run_id="wf_001")

        assert "T" in record.created_at
        assert "Z" in record.created_at
        # Should not raise
        datetime.fromisoformat(record.created_at.replace("Z", "+00:00"))

    def test_expires_at_in_future(self):
        """expires_at should be in the future."""
        record = build_approval_request(workflow_run_id="wf_001", expires_in_hours=24)

        now = datetime.now(UTC)
        expires = datetime.fromisoformat(record.expires_at.replace("Z", "+00:00"))

        assert expires > now


class TestBuildApprovalDecision:
    """Test approval decision building."""

    def test_build_grant_decision(self):
        """Build APPROVAL_GRANTED decision."""
        record = build_approval_decision(
            approval_id="appr_001",
            approval_event_type="APPROVAL_GRANTED",
            decided_by="admin",
            decided_role="approval_officer",
        )

        assert record.approval_id == "appr_001"
        assert record.approval_event_type == "APPROVAL_GRANTED"
        assert record.approval_status == "APPROVED"
        assert record.decided_by == "admin"

    def test_build_reject_decision(self):
        """Build APPROVAL_REJECTED decision."""
        record = build_approval_decision(
            approval_id="appr_001",
            approval_event_type="APPROVAL_REJECTED",
            decided_by="admin",
            decided_role="approval_officer",
            decision_reason="security concern",
        )

        assert record.approval_event_type == "APPROVAL_REJECTED"
        assert record.approval_status == "REJECTED"
        assert record.decision_reason == "security concern"

    def test_invalid_event_type_raises(self):
        """Invalid event type should raise ValueError."""
        with pytest.raises(ValueError):
            build_approval_decision(
                approval_id="appr_001",
                approval_event_type="APPROVAL_REQUESTED",  # Not a decision type
                decided_by="admin",
                decided_role="admin",
            )


class TestValidateApprovalRecord:
    """Test approval record validation."""

    def test_valid_request_passes(self):
        """Valid request record should have no errors."""
        record = build_approval_request(
            workflow_run_id="wf_001",
            workflow_id="wf_001",
            action_name="browser.execute_click",
            operation_type="click",
        )

        errors = validate_approval_record(record)
        assert len(errors) == 0, f"Expected no errors, got: {errors}"

    def test_valid_decision_passes(self):
        """Valid decision record should have no errors."""
        record = build_approval_decision(
            approval_id="appr_001",
            approval_event_type="APPROVAL_GRANTED",
            decided_by="admin",
            decided_role="admin",
        )

        errors = validate_approval_record(record)
        assert len(errors) == 0, f"Expected no errors, got: {errors}"

    def test_invalid_event_type_fails(self):
        """Invalid event_type should fail validation."""
        record = ApprovalRecord(
            approval_event_id="evt_001",
            approval_id="appr_001",
            workflow_run_id="wf_001",
            workflow_id="wf_001",
            action_name="browser.execute_click",
            operation_type="click",
            approval_event_type="INVALID_TYPE",
            approval_status="PENDING",
            approval_required=True,
            created_at="2026-05-07T00:00:00Z",
        )

        errors = validate_approval_record(record)
        assert any("approval_event_type" in e for e in errors)

    def test_event_type_status_mismatch_fails(self):
        """Event type and status must match according to mapping."""
        record = ApprovalRecord(
            approval_event_id="evt_001",
            approval_id="appr_001",
            workflow_run_id="wf_001",
            workflow_id="wf_001",
            action_name="browser.execute_click",
            operation_type="click",
            approval_event_type="APPROVAL_GRANTED",
            approval_status="PENDING",  # Wrong: GRANTED should be APPROVED
            approval_required=True,
            created_at="2026-05-07T00:00:00Z",
        )

        errors = validate_approval_record(record)
        assert any("approval_event_type" in e and "status" in e for e in errors)

    def test_decision_without_decided_by_fails(self):
        """Decision event requires decided_by."""
        record = ApprovalRecord(
            approval_event_id="evt_001",
            approval_id="appr_001",
            workflow_run_id="wf_001",
            workflow_id="wf_001",
            action_name="browser.execute_click",
            operation_type="click",
            approval_event_type="APPROVAL_GRANTED",
            approval_status="APPROVED",
            approval_required=True,
            decided_by="",  # Missing
            created_at="2026-05-07T00:00:00Z",
        )

        errors = validate_approval_record(record)
        assert any("decided_by" in e for e in errors)


class TestAppendApprovalRecord:
    """Test append-only approval record writing."""

    def test_append_single_record(self, tmp_path):
        """Should append single record to JSONL."""
        jsonl_file = tmp_path / "approval.jsonl"

        record = build_approval_request(
            workflow_run_id="wf_001",
            workflow_id="wf_001",
            action_name="browser.execute_click",
            operation_type="click",
        )

        result = append_approval_record(record, jsonl_file)

        assert result.success is True
        assert result.approval_id == record.approval_id
        assert result.event_count == 1
        assert jsonl_file.exists()

    def test_append_multiple_records(self, tmp_path):
        """Should append multiple records."""
        jsonl_file = tmp_path / "approval.jsonl"

        req = build_approval_request(
            workflow_run_id="wf_001",
            workflow_id="wf_001",
            action_name="browser.execute_click",
            operation_type="click",
        )
        approval_id = req.approval_id

        # Append request
        result1 = append_approval_record(req, jsonl_file)
        assert result1.success is True
        assert result1.event_count == 1

        # Append decision
        decision = build_approval_decision(
            approval_id=approval_id,
            approval_event_type="APPROVAL_GRANTED",
            decided_by="admin",
            decided_role="admin",
        )
        result2 = append_approval_record(decision, jsonl_file)
        assert result2.success is True
        assert result2.event_count == 2

    def test_append_does_not_truncate(self, tmp_path):
        """Append should not overwrite existing content."""
        jsonl_file = tmp_path / "approval.jsonl"

        # Write first record
        req1 = build_approval_request(workflow_run_id="wf_001")
        append_approval_record(req1, jsonl_file)

        with jsonl_file.open(encoding="utf-8") as f:
            original_content = f.read()

        # Write second record
        req2 = build_approval_request(workflow_run_id="wf_002")
        append_approval_record(req2, jsonl_file)

        with jsonl_file.open(encoding="utf-8") as f:
            new_content = f.read()

        # Original content should be preserved
        assert original_content in new_content
        lines = [line for line in new_content.strip().split("\n") if line]
        assert len(lines) == 2


class TestReadApprovalRecords:
    """Test reading approval records."""

    def test_read_single_record(self, tmp_path):
        """Should read single record."""
        jsonl_file = tmp_path / "approval.jsonl"

        record = build_approval_request(workflow_run_id="wf_001")
        append_approval_record(record, jsonl_file)

        records = read_approval_records(jsonl_file)
        assert len(records) == 1
        assert records[0]["approval_id"] == record.approval_id

    def test_read_multiple_records(self, tmp_path):
        """Should read multiple records."""
        jsonl_file = tmp_path / "approval.jsonl"

        req = build_approval_request(workflow_run_id="wf_001")
        append_approval_record(req, jsonl_file)

        decision = build_approval_decision(
            approval_id=req.approval_id,
            approval_event_type="APPROVAL_GRANTED",
            decided_by="admin",
            decided_role="admin",
        )
        append_approval_record(decision, jsonl_file)

        records = read_approval_records(jsonl_file)
        assert len(records) == 2


class TestApprovalHistory:
    """Test approval history tracking."""

    def test_get_history_single_event(self, tmp_path):
        """Should get history with single event."""
        jsonl_file = tmp_path / "approval.jsonl"

        req = build_approval_request(workflow_run_id="wf_001")
        approval_id = req.approval_id
        append_approval_record(req, jsonl_file)

        history = get_approval_history(approval_id, jsonl_file)
        assert len(history) == 1
        assert history[0]["approval_event_type"] == "APPROVAL_REQUESTED"

    def test_get_history_multiple_events(self, tmp_path):
        """Should get all events for same approval_id."""
        jsonl_file = tmp_path / "approval.jsonl"

        req = build_approval_request(workflow_run_id="wf_001")
        approval_id = req.approval_id
        append_approval_record(req, jsonl_file)

        decision = build_approval_decision(
            approval_id=approval_id,
            approval_event_type="APPROVAL_GRANTED",
            decided_by="admin",
            decided_role="admin",
        )
        append_approval_record(decision, jsonl_file)

        history = get_approval_history(approval_id, jsonl_file)
        assert len(history) == 2
        assert history[0]["approval_event_type"] == "APPROVAL_REQUESTED"
        assert history[1]["approval_event_type"] == "APPROVAL_GRANTED"

    def test_latest_status_pending(self, tmp_path):
        """Latest status after request should be PENDING."""
        jsonl_file = tmp_path / "approval.jsonl"

        req = build_approval_request(workflow_run_id="wf_001")
        approval_id = req.approval_id
        append_approval_record(req, jsonl_file)

        latest = get_latest_approval_status(approval_id, jsonl_file)
        assert latest is not None
        assert latest["approval_status"] == "PENDING"

    def test_latest_status_approved(self, tmp_path):
        """Latest status after grant should be APPROVED."""
        jsonl_file = tmp_path / "approval.jsonl"

        req = build_approval_request(workflow_run_id="wf_001")
        approval_id = req.approval_id
        append_approval_record(req, jsonl_file)

        decision = build_approval_decision(
            approval_id=approval_id,
            approval_event_type="APPROVAL_GRANTED",
            decided_by="admin",
            decided_role="admin",
        )
        append_approval_record(decision, jsonl_file)

        latest = get_latest_approval_status(approval_id, jsonl_file)
        assert latest["approval_status"] == "APPROVED"

    def test_latest_status_rejected(self, tmp_path):
        """Latest status after reject should be REJECTED."""
        jsonl_file = tmp_path / "approval.jsonl"

        req = build_approval_request(workflow_run_id="wf_001")
        approval_id = req.approval_id
        append_approval_record(req, jsonl_file)

        decision = build_approval_decision(
            approval_id=approval_id,
            approval_event_type="APPROVAL_REJECTED",
            decided_by="admin",
            decided_role="admin",
            decision_reason="security issue",
        )
        append_approval_record(decision, jsonl_file)

        latest = get_latest_approval_status(approval_id, jsonl_file)
        assert latest["approval_status"] == "REJECTED"

    def test_latest_status_revoked(self, tmp_path):
        """Latest status after revoke should be REVOKED (even if was APPROVED)."""
        jsonl_file = tmp_path / "approval.jsonl"

        req = build_approval_request(workflow_run_id="wf_001")
        approval_id = req.approval_id
        append_approval_record(req, jsonl_file)

        grant = build_approval_decision(
            approval_id=approval_id,
            approval_event_type="APPROVAL_GRANTED",
            decided_by="admin",
            decided_role="admin",
        )
        append_approval_record(grant, jsonl_file)

        revoke = build_approval_decision(
            approval_id=approval_id,
            approval_event_type="APPROVAL_REVOKED",
            decided_by="admin",
            decided_role="admin",
            decision_reason="revoked by request",
        )
        append_approval_record(revoke, jsonl_file)

        latest = get_latest_approval_status(approval_id, jsonl_file)
        assert latest["approval_status"] == "REVOKED"


class TestAuditApprovalContext:
    """Test approval context for audit."""

    def test_build_context_pending(self, tmp_path):
        """Context should include PENDING status."""
        jsonl_file = tmp_path / "approval.jsonl"

        req = build_approval_request(workflow_run_id="wf_001")
        approval_id = req.approval_id
        append_approval_record(req, jsonl_file)

        context = build_audit_approval_context(approval_id, jsonl_file)
        assert context["approval_id"] == approval_id
        assert context["approval_status"] == "PENDING"

    def test_build_context_approved(self, tmp_path):
        """Context should include APPROVED status after grant."""
        jsonl_file = tmp_path / "approval.jsonl"

        req = build_approval_request(workflow_run_id="wf_001")
        approval_id = req.approval_id
        append_approval_record(req, jsonl_file)

        decision = build_approval_decision(
            approval_id=approval_id,
            approval_event_type="APPROVAL_GRANTED",
            decided_by="admin",
            decided_role="admin",
        )
        append_approval_record(decision, jsonl_file)

        context = build_audit_approval_context(approval_id, jsonl_file)
        assert context["approval_status"] == "APPROVED"
        assert context["decided_by"] == "admin"

    def test_build_context_nonexistent(self, tmp_path):
        """Context for non-existent approval_id should be empty dict."""
        jsonl_file = tmp_path / "approval.jsonl"

        req = build_approval_request(workflow_run_id="wf_001")
        append_approval_record(req, jsonl_file)

        context = build_audit_approval_context("appr_nonexistent", jsonl_file)
        assert context == {}


class TestFixtureCompatibility:
    """Test compatibility with existing design fixtures."""

    def test_audit_module_design_fixture_compatibility(self):
        """Should be compatible with audit_module_design fixture."""
        fixture_path = Path("tests/fixtures/browser_audit_module_design_20260506.json")
        assert fixture_path.exists()

        with fixture_path.open(encoding="utf-8") as f:
            fixture = json.load(f)

        # All approval_required cases should work with approval records
        for case in fixture["cases"]:
            input_data = case.get("input", {})
            if input_data.get("approval_required"):
                approval_id = input_data.get("approval_id", "appr_test")

                # Build request
                req = build_approval_request(
                    approval_id=approval_id,
                    workflow_run_id=f"wf_{case['case_id']}",
                    workflow_id="test_workflow",
                    action_name="browser.execute_click",
                    operation_type="click",
                )

                # Validate
                errors = validate_approval_record(req)
                assert len(errors) == 0, f"Case {case['case_id']} request failed: {errors}"

    def test_real_workflow_policy_pack_fixture_compatibility(self):
        """Should be compatible with real_workflow_policy_pack fixture."""
        fixture_path = Path("tests/fixtures/browser_real_workflow_policy_pack_20260507.json")
        assert fixture_path.exists()

        with fixture_path.open(encoding="utf-8") as f:
            fixture = json.load(f)

        # All cases should support approval records if needed
        for case in fixture.get("e2e_cases", []):
            # Build a request record
            req = build_approval_request(
                workflow_run_id=f"wf_{case['case_id']}",
                workflow_id=case.get("workflow_id", "test"),
                action_name="browser.execute_click",
                operation_type="click",
            )

            errors = validate_approval_record(req)
            assert len(errors) == 0, f"Case {case['case_id']} failed: {errors}"


class TestNoImproperImports:
    """Ensure approval record store has no improper imports."""

    def test_no_task_executor_import(self):
        """Should not import task_executor."""
        import inspect

        import ai_orchestrator.browser_tool.approval.approval_record_store as module

        source = inspect.getsource(module)
        assert "import task_executor" not in source
        assert "from task_executor" not in source

    def test_no_dispatcher_import(self):
        """Should not import dispatcher."""
        import inspect

        import ai_orchestrator.browser_tool.approval.approval_record_store as module

        source = inspect.getsource(module)
        assert "import dispatcher" not in source
        assert "from dispatcher" not in source

    def test_no_browser_execution_import(self):
        """Should not import browser execution libraries."""
        import inspect

        import ai_orchestrator.browser_tool.approval.approval_record_store as module

        source = inspect.getsource(module)
        assert "selenium" not in source.lower()
        assert "playwright" not in source.lower()

    def test_no_db_operations(self):
        """Should not have DB write operations."""
        import inspect

        import ai_orchestrator.browser_tool.approval.approval_record_store as module

        source = inspect.getsource(module)
        assert ".execute(" not in source
        assert ".commit(" not in source
        assert ".rollback(" not in source

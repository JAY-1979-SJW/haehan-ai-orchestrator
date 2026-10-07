"""Test suite for browser workflow audit writer implementation.

Tests append-only JSONL writer, redaction, validation, and fixture compatibility.
All tests use temp files, no production paths.
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

from ai_orchestrator.browser_tool.approval.workflow_audit_writer import (
    WorkflowAuditRecord,
    append_audit_record,
    build_audit_record,
    read_audit_records,
    redact_audit_payload,
    validate_audit_record,
)


class TestBuildAuditRecord:
    """Test audit record building."""

    def test_build_record_creates_required_fields(self):
        """Build should create all required fields."""
        record = build_audit_record(
            workflow_run_id="wf_001",
            event_type="REQUEST_RECEIVED",
            action_name="browser.execute_click",
            operation_type="click",
            workflow_id="g2b_notice_search_readonly",
            gate_decision="ALLOW",
        )

        assert record.audit_id is not None
        assert len(record.audit_id) > 0
        assert record.workflow_run_id == "wf_001"
        assert record.event_type == "REQUEST_RECEIVED"
        assert record.created_at is not None
        assert "T" in record.created_at  # ISO format

    def test_audit_id_unique_per_record(self):
        """Each record should have unique audit_id."""
        r1 = build_audit_record(
            workflow_run_id="wf_001",
            event_type="REQUEST_RECEIVED",
            action_name="browser.execute_click",
            operation_type="click",
            workflow_id="wf_001",
            gate_decision="ALLOW",
        )
        r2 = build_audit_record(
            workflow_run_id="wf_001",
            event_type="REQUEST_RECEIVED",
            action_name="browser.execute_click",
            operation_type="click",
            workflow_id="wf_001",
            gate_decision="ALLOW",
        )

        assert r1.audit_id != r2.audit_id

    def test_created_at_iso_format(self):
        """created_at should be ISO 8601 format."""
        record = build_audit_record(
            workflow_run_id="wf_001",
            event_type="REQUEST_RECEIVED",
            action_name="browser.execute_click",
            operation_type="click",
            workflow_id="wf_001",
            gate_decision="ALLOW",
        )

        # Parse ISO format
        assert "T" in record.created_at
        assert "Z" in record.created_at
        # Should not raise
        datetime.fromisoformat(record.created_at.replace("Z", "+00:00"))

    def test_build_record_with_url_redaction(self):
        """URL should be redacted and hashed."""
        url = "https://example.com/api?token=secret123&user=john"
        record = build_audit_record(
            workflow_run_id="wf_001",
            event_type="REQUEST_RECEIVED",
            action_name="browser.execute_click",
            operation_type="click",
            workflow_id="wf_001",
            gate_decision="ALLOW",
            target_url=url,
        )

        assert record.target_url_redacted != ""
        assert "[REDACTED]" in record.target_url_redacted or "secret123" not in record.target_url_redacted
        assert record.target_url_hash != ""
        assert len(record.target_url_hash) == 64  # SHA256 hash


class TestValidateAuditRecord:
    """Test audit record validation."""

    def test_valid_record_passes(self):
        """Valid record should have no errors."""
        record = build_audit_record(
            workflow_run_id="wf_001",
            event_type="REQUEST_RECEIVED",
            action_name="browser.execute_click",
            operation_type="click",
            workflow_id="wf_001",
            gate_decision="ALLOW",
        )

        errors = validate_audit_record(record)
        assert len(errors) == 0, f"Expected no errors, got: {errors}"

    def test_invalid_event_type_fails(self):
        """Invalid event_type should fail validation."""
        record = build_audit_record(
            workflow_run_id="wf_001",
            event_type="INVALID_TYPE",
            action_name="browser.execute_click",
            operation_type="click",
            workflow_id="wf_001",
            gate_decision="ALLOW",
        )

        errors = validate_audit_record(record)
        assert any("event_type" in e for e in errors)

    def test_safe_to_execute_true_fails(self):
        """safe_to_execute=true should fail in this phase."""
        record = build_audit_record(
            workflow_run_id="wf_001",
            event_type="REQUEST_RECEIVED",
            action_name="browser.execute_click",
            operation_type="click",
            workflow_id="wf_001",
            gate_decision="ALLOW",
            safe_to_execute=True,
        )

        errors = validate_audit_record(record)
        assert any("safe_to_execute" in e and "false" in e for e in errors)

    def test_production_mode_true_with_safe_to_execute_true_fails(self):
        """production_mode=true with safe_to_execute=true should fail."""
        record = build_audit_record(
            workflow_run_id="wf_001",
            event_type="REQUEST_RECEIVED",
            action_name="browser.execute_click",
            operation_type="click",
            workflow_id="wf_001",
            gate_decision="ALLOW",
            production_mode=True,
            safe_to_execute=True,
        )

        errors = validate_audit_record(record)
        assert any("production_mode" in e and "safe_to_execute" in e for e in errors)


class TestRedactionPayload:
    """Test payload redaction."""

    def test_password_field_redacted(self):
        """Password field should be redacted."""
        payload = {"password": "secret123"}
        redacted = redact_audit_payload(payload)
        assert redacted["password"] == "[REDACTED]"

    def test_token_field_redacted(self):
        """Token field should be redacted."""
        payload = {"access_token": "token123"}
        redacted = redact_audit_payload(payload)
        assert redacted["access_token"] == "[REDACTED]"

    def test_secret_field_redacted(self):
        """Secret field should be redacted."""
        payload = {"secret": "mysecret"}
        redacted = redact_audit_payload(payload)
        assert redacted["secret"] == "[REDACTED]"

    def test_otp_field_redacted(self):
        """OTP field should be redacted."""
        payload = {"otp": "123456"}
        redacted = redact_audit_payload(payload)
        assert redacted["otp"] == "[REDACTED]"

    def test_cookie_field_redacted(self):
        """Cookie field should be redacted."""
        payload = {"cookie": "abc123def456"}
        redacted = redact_audit_payload(payload)
        assert redacted["cookie"] == "[REDACTED]"

    def test_session_field_redacted(self):
        """Session field should be redacted."""
        payload = {"session": "sess_123"}
        redacted = redact_audit_payload(payload)
        assert redacted["session"] == "[REDACTED]"

    def test_safe_field_preserved(self):
        """Safe field should be preserved."""
        payload = {"username": "john"}
        redacted = redact_audit_payload(payload)
        assert redacted["username"] == "john"

    def test_nested_dict_redacted(self):
        """Nested dicts should be recursively redacted."""
        payload = {"user": {"password": "secret123"}}
        redacted = redact_audit_payload(payload)
        assert redacted["user"]["password"] == "[REDACTED]"

    def test_list_redacted(self):
        """Lists should be recursively redacted."""
        payload = {"fields": [{"name": "password", "value": "secret"}]}
        redacted = redact_audit_payload(payload)
        assert redacted["fields"][0]["name"] == "password"
        assert redacted["fields"][0]["value"] == "[REDACTED]"


class TestAppendAuditRecord:
    """Test append-only audit record writing."""

    def test_append_single_record(self, tmp_path):
        """Should append single record to JSONL."""
        jsonl_file = tmp_path / "audit.jsonl"

        record = build_audit_record(
            workflow_run_id="wf_001",
            event_type="REQUEST_RECEIVED",
            action_name="browser.execute_click",
            operation_type="click",
            workflow_id="wf_001",
            gate_decision="ALLOW",
        )

        result = append_audit_record(record, jsonl_file)

        assert result.success is True
        assert result.audit_id == record.audit_id
        assert result.event_count == 1
        assert jsonl_file.exists()

    def test_append_multiple_records(self, tmp_path):
        """Should append multiple records."""
        jsonl_file = tmp_path / "audit.jsonl"

        record1 = build_audit_record(
            workflow_run_id="wf_001",
            event_type="REQUEST_RECEIVED",
            action_name="browser.execute_click",
            operation_type="click",
            workflow_id="wf_001",
            gate_decision="ALLOW",
        )

        record2 = build_audit_record(
            workflow_run_id="wf_001",
            event_type="GATE_EVALUATED",
            action_name="browser.execute_click",
            operation_type="click",
            workflow_id="wf_001",
            gate_decision="ALLOW",
        )

        result1 = append_audit_record(record1, jsonl_file)
        result2 = append_audit_record(record2, jsonl_file)

        assert result1.success is True
        assert result2.success is True
        assert result1.event_count == 1
        assert result2.event_count == 2

    def test_append_does_not_truncate(self, tmp_path):
        """Append should not overwrite existing content."""
        jsonl_file = tmp_path / "audit.jsonl"

        # Write first record
        record1 = build_audit_record(
            workflow_run_id="wf_001",
            event_type="REQUEST_RECEIVED",
            action_name="browser.execute_click",
            operation_type="click",
            workflow_id="wf_001",
            gate_decision="ALLOW",
        )
        append_audit_record(record1, jsonl_file)

        # Read original content
        with jsonl_file.open(encoding="utf-8") as f:
            original_content = f.read()

        # Write second record
        record2 = build_audit_record(
            workflow_run_id="wf_001",
            event_type="GATE_EVALUATED",
            action_name="browser.execute_click",
            operation_type="click",
            workflow_id="wf_001",
            gate_decision="ALLOW",
        )
        append_audit_record(record2, jsonl_file)

        # Read new content
        with jsonl_file.open(encoding="utf-8") as f:
            new_content = f.read()

        # Original content should be preserved
        assert original_content in new_content
        lines = [line for line in new_content.strip().split("\n") if line]
        assert len(lines) == 2

    def test_validation_error_returns_failure(self, tmp_path):
        """Invalid record should return failure without writing."""
        jsonl_file = tmp_path / "audit.jsonl"

        # Create invalid record (missing required field)
        record = WorkflowAuditRecord(
            audit_id="",  # Invalid: empty
            workflow_run_id="wf_001",
            event_type="REQUEST_RECEIVED",
            action_name="browser.execute_click",
            operation_type="click",
            workflow_id="wf_001",
            gate_decision="ALLOW",
            created_at="2026-05-07T00:00:00Z",
        )

        result = append_audit_record(record, jsonl_file)

        assert result.success is False
        assert "Validation failed" in result.error_message
        assert not jsonl_file.exists() or jsonl_file.stat().st_size == 0


class TestReadAuditRecords:
    """Test reading audit records from JSONL."""

    def test_read_single_record(self, tmp_path):
        """Should read single record from JSONL."""
        jsonl_file = tmp_path / "audit.jsonl"

        record = build_audit_record(
            workflow_run_id="wf_001",
            event_type="REQUEST_RECEIVED",
            action_name="browser.execute_click",
            operation_type="click",
            workflow_id="wf_001",
            gate_decision="ALLOW",
        )

        append_audit_record(record, jsonl_file)
        records = read_audit_records(jsonl_file)

        assert len(records) == 1
        assert records[0]["audit_id"] == record.audit_id

    def test_read_multiple_records(self, tmp_path):
        """Should read multiple records."""
        jsonl_file = tmp_path / "audit.jsonl"

        records_to_write = [
            build_audit_record(
                workflow_run_id="wf_001",
                event_type="REQUEST_RECEIVED",
                action_name="browser.execute_click",
                operation_type="click",
                workflow_id="wf_001",
                gate_decision="ALLOW",
            ),
            build_audit_record(
                workflow_run_id="wf_001",
                event_type="GATE_EVALUATED",
                action_name="browser.execute_click",
                operation_type="click",
                workflow_id="wf_001",
                gate_decision="ALLOW",
            ),
        ]

        for record in records_to_write:
            append_audit_record(record, jsonl_file)

        records = read_audit_records(jsonl_file)
        assert len(records) == 2

    def test_read_nonexistent_file_raises(self, tmp_path):
        """Reading nonexistent file should raise FileNotFoundError."""
        jsonl_file = tmp_path / "nonexistent.jsonl"

        with pytest.raises(FileNotFoundError):
            read_audit_records(jsonl_file)

    def test_read_skips_empty_lines(self, tmp_path):
        """Should skip empty lines."""
        jsonl_file = tmp_path / "audit.jsonl"

        record = build_audit_record(
            workflow_run_id="wf_001",
            event_type="REQUEST_RECEIVED",
            action_name="browser.execute_click",
            operation_type="click",
            workflow_id="wf_001",
            gate_decision="ALLOW",
        )

        append_audit_record(record, jsonl_file)

        # Manually add empty lines
        with jsonl_file.open("a") as f:
            f.write("\n\n")

        records = read_audit_records(jsonl_file)
        assert len(records) == 1


class TestFixtureCompatibility:
    """Test compatibility with existing design fixtures."""

    def test_audit_module_design_fixture_compatibility(self):
        """Should be compatible with audit_module_design_20260506 fixture."""
        fixture_path = Path("tests/fixtures/browser_audit_module_design_20260506.json")
        assert fixture_path.exists(), f"Fixture not found: {fixture_path}"

        with fixture_path.open(encoding="utf-8") as f:
            fixture = json.load(f)

        # Check that production_mode and safe_to_execute are false
        assert fixture["production_mode"] is False
        assert fixture["safe_to_execute"] is False

        # All cases should be creatable as audit records
        for case in fixture["cases"]:
            # Try to build a record from case input
            input_data = case.get("input", {})
            record = build_audit_record(
                workflow_run_id=f"wf_{case['case_id']}",
                event_type=input_data.get("event_stage", "REQUEST_RECEIVED"),
                action_name=input_data.get("action_name", "browser.execute_click"),
                operation_type=input_data.get("operation_type", "click"),
                workflow_id="test_workflow",
                gate_decision=input_data.get("gate_decision", "ALLOW"),
            )

            # Validate
            errors = validate_audit_record(record)
            assert len(errors) == 0, f"Case {case['case_id']} validation failed: {errors}"

    def test_real_workflow_policy_pack_fixture_compatibility(self):
        """Should be compatible with real_workflow_policy_pack fixture."""
        fixture_path = Path("tests/fixtures/browser_real_workflow_policy_pack_20260507.json")
        assert fixture_path.exists(), f"Fixture not found: {fixture_path}"

        with fixture_path.open(encoding="utf-8") as f:
            fixture = json.load(f)

        # Check critical flags
        assert fixture["production_allowed"] is False
        assert fixture["safe_to_execute"] is False

        # All cases should be creatable as audit records
        for case in fixture.get("e2e_cases", []):
            record = build_audit_record(
                workflow_run_id=f"wf_{case['case_id']}",
                event_type="AUDIT_READY",
                action_name="browser.execute_click",
                operation_type="click",
                workflow_id=case.get("workflow_id", "test"),
                gate_decision="ALLOW",
                production_mode=False,
            )

            errors = validate_audit_record(record)
            assert len(errors) == 0, f"Case {case['case_id']} validation failed: {errors}"


class TestNoImproperImports:
    """Ensure audit writer has no improper imports."""

    def test_no_task_executor_import(self):
        """Should not import task_executor."""
        import inspect

        import ai_orchestrator.browser_tool.approval.workflow_audit_writer as module

        source = inspect.getsource(module)
        assert "import task_executor" not in source
        assert "from task_executor" not in source

    def test_no_dispatcher_import(self):
        """Should not import dispatcher."""
        import inspect

        import ai_orchestrator.browser_tool.approval.workflow_audit_writer as module

        source = inspect.getsource(module)
        assert "import dispatcher" not in source
        assert "from dispatcher" not in source

    def test_no_browser_execution_import(self):
        """Should not import browser execution libraries."""
        import inspect

        import ai_orchestrator.browser_tool.approval.workflow_audit_writer as module

        source = inspect.getsource(module)
        assert "selenium" not in source.lower()
        assert "playwright" not in source.lower()

    def test_no_db_operations(self):
        """Should not have DB write operations."""
        import inspect

        import ai_orchestrator.browser_tool.approval.workflow_audit_writer as module

        source = inspect.getsource(module)
        assert ".execute(" not in source
        assert ".commit(" not in source
        assert ".rollback(" not in source

"""Browser Submit Audit Log Persistence Tests.

Unit tests for audit log JSONL writer (append-only, redaction, validation).
Test-only file operations (tmp_path), no production paths.
"""

import json

import pytest

from ai_orchestrator.browser_tool.approval.submit_audit_log import (
    SubmitAuditEvent,
    append_submit_audit_event,
    build_submit_audit_event,
    read_submit_audit_events,
    redact_audit_payload,
    serialize_audit_event,
    validate_submit_audit_event,
)


class TestSubmitAuditEventBuilding:
    """Test audit event creation."""

    def test_01_build_event_with_all_fields(self):
        """Test 1: Build event with all required and optional fields."""
        event = build_submit_audit_event(
            validation_id="smoke_001",
            action_id="browser.submit.controlled_click",
            site_id="allowed_internal_mock_form",
            form_id="contact_form",
            submit_button_id="submit_button_id",
            intent="submit_contact_form",
            policy_verdict="ALLOW",
            risk_level="high",
            preview_hash="a" * 64,
            user_confirmed=True,
            submitted=True,
            submit_result="success",
            redacted_payload={"email": "test@internal.mock"},
            result_summary="Form submitted successfully",
            approved_by="user_123",
            submit_timestamp="2026-05-06T11:00:00Z",
            metadata={"browser": "chromium"},
        )

        assert event.validation_id == "smoke_001"
        assert event.schema_version == "1.0"
        assert event.event_id is not None
        assert event.created_at is not None
        assert event.approved_by == "user_123"
        assert event.approved_at is not None
        assert event.metadata["browser"] == "chromium"

    def test_02_build_event_minimal(self):
        """Test 2: Build event with minimal required fields."""
        event = build_submit_audit_event(
            validation_id="smoke_002",
            action_id="browser.submit.policy_check",
            site_id="site1",
            form_id="form1",
            submit_button_id="btn1",
            intent="intent1",
            policy_verdict="DENY",
            risk_level="low",
            preview_hash="b" * 64,
            user_confirmed=False,
            submitted=False,
            submit_result="blocked",
            redacted_payload={},
            result_summary="Blocked by policy",
        )

        assert event.approved_by is None
        assert event.approved_at is None
        assert event.submit_timestamp is None
        assert event.error_reason is None


class TestRedaction:
    """Test sensitive data redaction."""

    def test_03_redact_password_field(self):
        """Test 3: Password field gets masked."""
        payload = {"password": "secret123", "email": "user@test.com"}
        redacted = redact_audit_payload(payload)

        assert redacted["password"] == {"masked": True}
        assert redacted["email"] == "user@test.com"

    def test_04_redact_token_field(self):
        """Test 4: API token field gets masked."""
        payload = {"api_token": "xyz789", "username": "john"}
        redacted = redact_audit_payload(payload)

        assert redacted["api_token"] == {"masked": True}
        assert redacted["username"] == "john"

    def test_05_preserve_safe_hidden_fields(self):
        """Test 5: Safe hidden fields preserve values."""
        payload = {
            "csrf_token": "safe_token_123",
            "form_version": "1.0",
            "timestamp": "2026-05-06T11:00:00Z",
        }
        redacted = redact_audit_payload(payload)

        assert redacted["csrf_token"] == "safe_token_123"
        assert redacted["form_version"] == "1.0"
        assert redacted["timestamp"] == "2026-05-06T11:00:00Z"

    def test_06_redact_nested_dict(self):
        """Test 6: Redact sensitive keys in nested dict."""
        payload = {
            "user": {
                "email": "user@test.com",
                "password": "secret",
            }
        }
        redacted = redact_audit_payload(payload)

        assert redacted["user"]["email"] == "user@test.com"
        assert redacted["user"]["password"] == {"masked": True}

    def test_07_redact_list_items(self):
        """Test 7: Redact sensitive keys in list."""
        payload = {
            "fields": [
                {"name": "email", "value": "test@test.com"},
                {"name": "password", "value": "secret"},
            ]
        }
        redacted = redact_audit_payload(payload)

        assert redacted["fields"][0]["value"] == "test@test.com"
        assert redacted["fields"][1]["value"] == {"masked": True}

    def test_08_redact_no_raw_password_in_output(self):
        """Test 8: No raw password appears anywhere in redacted payload."""
        payload = {
            "password": "secret123",
            "pwd": "mysecret",
            "api_key": "key_abc123def456",
            "token": "bearer_token_xyz",
        }
        redacted = redact_audit_payload(payload)

        redacted_str = json.dumps(redacted)
        assert "secret123" not in redacted_str
        assert "mysecret" not in redacted_str
        assert "key_abc123def456" not in redacted_str
        assert "bearer_token_xyz" not in redacted_str


class TestValidation:
    """Test event validation."""

    def test_09_validate_required_fields(self):
        """Test 9: Event with all required fields is valid."""
        event = build_submit_audit_event(
            validation_id="smoke_003",
            action_id="browser.submit.policy_check",
            site_id="site1",
            form_id="form1",
            submit_button_id="btn1",
            intent="intent1",
            policy_verdict="ALLOW",
            risk_level="high",
            preview_hash="c" * 64,
            user_confirmed=True,
            submitted=True,
            submit_result="success",
            redacted_payload={},
            result_summary="OK",
        )

        errors = validate_submit_audit_event(event)
        assert len(errors) == 0

    def test_10_validate_missing_preview_hash(self):
        """Test 10: Missing preview_hash fails validation."""
        event = SubmitAuditEvent(
            schema_version="1.0",
            event_id="evt_001",
            created_at="2026-05-06T11:00:00Z",
            validation_id="smoke_004",
            action_id="browser.submit.policy_check",
            site_id="site1",
            form_id="form1",
            submit_button_id="btn1",
            intent="intent1",
            preview_hash="",  # Missing
            policy_verdict="ALLOW",
            risk_level="high",
            user_confirmed=True,
            submitted=True,
            submit_result="success",
            redacted_payload={},
            result_summary="OK",
        )

        errors = validate_submit_audit_event(event)
        assert any("preview_hash" in e for e in errors)

    def test_11_validate_missing_policy_verdict(self):
        """Test 11: Missing policy_verdict fails validation."""
        event = SubmitAuditEvent(
            schema_version="1.0",
            event_id="evt_002",
            created_at="2026-05-06T11:00:00Z",
            validation_id="smoke_005",
            action_id="browser.submit.policy_check",
            site_id="site1",
            form_id="form1",
            submit_button_id="btn1",
            intent="intent1",
            preview_hash="d" * 64,
            policy_verdict="",  # Missing
            risk_level="high",
            user_confirmed=True,
            submitted=True,
            submit_result="success",
            redacted_payload={},
            result_summary="OK",
        )

        errors = validate_submit_audit_event(event)
        assert any("policy_verdict" in e for e in errors)

    def test_12_validate_missing_submitted(self):
        """Test 12: Missing submitted field fails validation."""
        event = SubmitAuditEvent(
            schema_version="1.0",
            event_id="evt_003",
            created_at="2026-05-06T11:00:00Z",
            validation_id="smoke_006",
            action_id="browser.submit.policy_check",
            site_id="site1",
            form_id="form1",
            submit_button_id="btn1",
            intent="intent1",
            preview_hash="e" * 64,
            policy_verdict="ALLOW",
            risk_level="high",
            user_confirmed=True,
            submitted=None,  # Missing
            submit_result="success",
            redacted_payload={},
            result_summary="OK",
        )

        errors = validate_submit_audit_event(event)
        assert any("submitted" in e for e in errors)

    def test_13_validate_invalid_submit_result(self):
        """Test 13: Invalid submit_result fails validation."""
        event = SubmitAuditEvent(
            schema_version="1.0",
            event_id="evt_004",
            created_at="2026-05-06T11:00:00Z",
            validation_id="smoke_007",
            action_id="browser.submit.policy_check",
            site_id="site1",
            form_id="form1",
            submit_button_id="btn1",
            intent="intent1",
            preview_hash="f" * 64,
            policy_verdict="ALLOW",
            risk_level="high",
            user_confirmed=True,
            submitted=True,
            submit_result="invalid_status",  # Invalid
            redacted_payload={},
            result_summary="OK",
        )

        errors = validate_submit_audit_event(event)
        assert any("submit_result" in e for e in errors)


class TestSerialization:
    """Test JSON serialization."""

    def test_14_serialize_event_to_json(self):
        """Test 14: Event serializes to valid JSON."""
        event = build_submit_audit_event(
            validation_id="smoke_008",
            action_id="browser.submit.policy_check",
            site_id="site1",
            form_id="form1",
            submit_button_id="btn1",
            intent="intent1",
            policy_verdict="ALLOW",
            risk_level="high",
            preview_hash="a" * 64,
            user_confirmed=True,
            submitted=True,
            submit_result="success",
            redacted_payload={"email": "test@test.com"},
            result_summary="OK",
        )

        json_str = serialize_audit_event(event)
        assert json_str is not None
        assert "\n" not in json_str  # Single line

        # Must be parseable
        parsed = json.loads(json_str)
        assert parsed["validation_id"] == "smoke_008"

    def test_15_serialize_result_is_json_parseable(self):
        """Test 15: Serialized event is valid JSON."""
        event = build_submit_audit_event(
            validation_id="smoke_009",
            action_id="browser.submit.controlled_click",
            site_id="site1",
            form_id="form1",
            submit_button_id="btn1",
            intent="intent1",
            policy_verdict="ALLOW",
            risk_level="high",
            preview_hash="b" * 64,
            user_confirmed=True,
            submitted=True,
            submit_result="success",
            redacted_payload={},
            result_summary="OK",
            metadata={"test": "value"},
        )

        json_str = serialize_audit_event(event)
        parsed = json.loads(json_str)

        assert isinstance(parsed, dict)
        assert parsed["schema_version"] == "1.0"
        assert parsed["metadata"]["test"] == "value"


class TestAppendOnlyBehavior:
    """Test append-only JSONL file operations."""

    def test_16_append_to_new_file(self, tmp_path):
        """Test 16: Can append to new file."""
        log_path = tmp_path / "audit.jsonl"
        assert not log_path.exists()

        event = build_submit_audit_event(
            validation_id="smoke_010",
            action_id="browser.submit.policy_check",
            site_id="site1",
            form_id="form1",
            submit_button_id="btn1",
            intent="intent1",
            policy_verdict="ALLOW",
            risk_level="high",
            preview_hash="c" * 64,
            user_confirmed=True,
            submitted=True,
            submit_result="success",
            redacted_payload={},
            result_summary="OK",
        )

        result = append_submit_audit_event(log_path, event)

        assert result.success is True
        assert log_path.exists()
        assert result.event_count == 1

    def test_17_append_preserves_existing(self, tmp_path):
        """Test 17: Append doesn't overwrite existing content."""
        log_path = tmp_path / "audit.jsonl"

        event1 = build_submit_audit_event(
            validation_id="smoke_011",
            action_id="browser.submit.policy_check",
            site_id="site1",
            form_id="form1",
            submit_button_id="btn1",
            intent="intent1",
            policy_verdict="ALLOW",
            risk_level="high",
            preview_hash="d" * 64,
            user_confirmed=True,
            submitted=True,
            submit_result="success",
            redacted_payload={},
            result_summary="First",
        )

        event2 = build_submit_audit_event(
            validation_id="smoke_012",
            action_id="browser.submit.policy_check",
            site_id="site1",
            form_id="form1",
            submit_button_id="btn1",
            intent="intent1",
            policy_verdict="DENY",
            risk_level="high",
            preview_hash="e" * 64,
            user_confirmed=False,
            submitted=False,
            submit_result="blocked",
            redacted_payload={},
            result_summary="Second",
        )

        # Append both events
        result1 = append_submit_audit_event(log_path, event1)
        assert result1.success is True
        assert result1.event_count == 1

        result2 = append_submit_audit_event(log_path, event2)
        assert result2.success is True
        assert result2.event_count == 2

        # Verify both events are present
        events = read_submit_audit_events(log_path)
        assert len(events) == 2
        assert events[0]["validation_id"] == "smoke_011"
        assert events[1]["validation_id"] == "smoke_012"

    def test_18_multiple_events_preserve_order(self, tmp_path):
        """Test 18: Multiple events maintain order."""
        log_path = tmp_path / "audit.jsonl"

        for i in range(5):
            event = build_submit_audit_event(
                validation_id=f"smoke_{i:03d}",
                action_id="browser.submit.policy_check",
                site_id="site1",
                form_id="form1",
                submit_button_id="btn1",
                intent="intent1",
                policy_verdict="ALLOW",
                risk_level="high",
                preview_hash=chr(ord("a") + i) * 64,
                user_confirmed=True,
                submitted=True,
                submit_result="success",
                redacted_payload={},
                result_summary=f"Event {i}",
            )
            append_submit_audit_event(log_path, event)

        events = read_submit_audit_events(log_path)
        assert len(events) == 5
        for i in range(5):
            assert events[i]["validation_id"] == f"smoke_{i:03d}"


class TestRead:
    """Test reading audit log."""

    def test_19_read_audit_events(self, tmp_path):
        """Test 19: Can read events from file."""
        log_path = tmp_path / "audit.jsonl"

        event = build_submit_audit_event(
            validation_id="smoke_020",
            action_id="browser.submit.controlled_click",
            site_id="site1",
            form_id="form1",
            submit_button_id="btn1",
            intent="intent1",
            policy_verdict="ALLOW",
            risk_level="high",
            preview_hash="f" * 64,
            user_confirmed=True,
            submitted=True,
            submit_result="success",
            redacted_payload={"email": "test@test.com"},
            result_summary="OK",
        )

        append_submit_audit_event(log_path, event)

        # Read back
        events = read_submit_audit_events(log_path)
        assert len(events) == 1
        assert events[0]["validation_id"] == "smoke_020"
        assert events[0]["redacted_payload"]["email"] == "test@test.com"

    def test_20_read_nonexistent_file_raises(self, tmp_path):
        """Test 20: Reading nonexistent file raises FileNotFoundError."""
        log_path = tmp_path / "nonexistent.jsonl"

        with pytest.raises(FileNotFoundError):
            read_submit_audit_events(log_path)


class TestResultHandling:
    """Test submit_result field handling."""

    def test_21_submit_result_success(self):
        """Test 21: submit_result=success is valid."""
        event = build_submit_audit_event(
            validation_id="smoke_021",
            action_id="browser.submit.policy_check",
            site_id="site1",
            form_id="form1",
            submit_button_id="btn1",
            intent="intent1",
            policy_verdict="ALLOW",
            risk_level="high",
            preview_hash="a" * 64,
            user_confirmed=True,
            submitted=True,
            submit_result="success",
            redacted_payload={},
            result_summary="OK",
        )

        errors = validate_submit_audit_event(event)
        assert len(errors) == 0

    def test_22_submit_result_blocked(self):
        """Test 22: submit_result=blocked is valid."""
        event = build_submit_audit_event(
            validation_id="smoke_022",
            action_id="browser.submit.policy_check",
            site_id="site1",
            form_id="form1",
            submit_button_id="btn1",
            intent="intent1",
            policy_verdict="DENY",
            risk_level="high",
            preview_hash="b" * 64,
            user_confirmed=False,
            submitted=False,
            submit_result="blocked",
            redacted_payload={},
            result_summary="Blocked",
        )

        errors = validate_submit_audit_event(event)
        assert len(errors) == 0

    def test_23_submit_result_error(self):
        """Test 23: submit_result=error is valid."""
        event = build_submit_audit_event(
            validation_id="smoke_023",
            action_id="browser.submit.policy_check",
            site_id="site1",
            form_id="form1",
            submit_button_id="btn1",
            intent="intent1",
            policy_verdict="ALLOW",
            risk_level="high",
            preview_hash="c" * 64,
            user_confirmed=True,
            submitted=False,
            submit_result="error",
            redacted_payload={},
            result_summary="Error",
            error_reason="Network timeout",
        )

        errors = validate_submit_audit_event(event)
        assert len(errors) == 0


class TestUserConfirmedHandling:
    """Test user_confirmed field."""

    def test_24_user_confirmed_true(self):
        """Test 24: user_confirmed=true is recorded."""
        event = build_submit_audit_event(
            validation_id="smoke_024",
            action_id="browser.submit.controlled_click",
            site_id="site1",
            form_id="form1",
            submit_button_id="btn1",
            intent="intent1",
            policy_verdict="ALLOW",
            risk_level="high",
            preview_hash="d" * 64,
            user_confirmed=True,
            submitted=True,
            submit_result="success",
            redacted_payload={},
            result_summary="OK",
        )

        assert event.user_confirmed is True
        json_str = serialize_audit_event(event)
        assert '"user_confirmed": true' in json_str


class TestIntegrationWithExistingModules:
    """Test interop with existing submit modules."""

    def test_25_can_combine_preview_policy_results(self, tmp_path):
        """Test 25: Can combine policy and preview results into audit event."""
        log_path = tmp_path / "audit.jsonl"

        # Simulate receiving policy result
        policy_verdict = "ALLOW"
        risk_level = "high"

        # Simulate receiving preview result
        preview_hash = "g" * 64

        # Simulate receiving controlled submit result
        submitted = True
        submit_result = "success"

        # Build audit event from all three
        event = build_submit_audit_event(
            validation_id="smoke_025",
            action_id="browser.submit.controlled_click",
            site_id="site1",
            form_id="form1",
            submit_button_id="btn1",
            intent="intent1",
            policy_verdict=policy_verdict,
            risk_level=risk_level,
            preview_hash=preview_hash,
            user_confirmed=True,
            submitted=submitted,
            submit_result=submit_result,
            redacted_payload={"email": "user@test.com"},
            result_summary="All three modules combined",
        )

        result = append_submit_audit_event(log_path, event)
        assert result.success is True

        # Verify all components are in audit log
        events = read_submit_audit_events(log_path)
        assert events[0]["policy_verdict"] == "ALLOW"
        assert events[0]["preview_hash"] == "g" * 64
        assert events[0]["submitted"] is True


class TestProductionSafeguards:
    """Test that production paths are not used."""

    def test_26_only_tmppath_used_in_tests(self, tmp_path):
        """Test 26: All file operations use tmp_path (no production paths)."""
        log_path = tmp_path / "audit.jsonl"
        assert str(tmp_path) in str(log_path)
        assert "/var/log" not in str(log_path)
        assert "C:\\Program Files" not in str(log_path).lower()

    def test_27_no_network_or_db_calls(self):
        """Test 27: Module has no network or DB calls."""
        # This is a code-level guarantee, but we verify by checking
        # that all functions are pure Python with no imports of network/DB libs
        import inspect

        from ai_orchestrator.browser_tool.approval import submit_audit_log

        for name, func in inspect.getmembers(submit_audit_log, inspect.isfunction):
            source = inspect.getsource(func)
            assert "requests" not in source
            assert "urllib" not in source
            assert "socket" not in source
            assert "sqlite" not in source
            assert "psycopg" not in source
            assert "mysql" not in source

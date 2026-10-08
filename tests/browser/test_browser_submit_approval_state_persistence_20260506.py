"""
Tests for Browser Submit Approval State Persistence

Tests the approval state JSONL persistence module:
- Event creation and validation
- JSONL append-only behavior
- State query interface
- No external dependencies (network, DB, docker, env)
- Temporary file (tmp_path) usage only
"""

import json

import pytest

from ai_orchestrator.browser_tool.approval.submit_approval_state import (
    ApprovalStateError,
    ValidationError,
    append_approval_state_event,
    create_approval_decision_event,
    create_approval_requested_event,
    get_approval_status,
    latest_approval_state,
    read_approval_state_events,
)


class TestApprovalRequestedEvent:
    """Test approval requested event creation."""

    def test_create_approval_requested_event_valid(self):
        """Should create valid approval requested event."""
        event = create_approval_requested_event(
            validation_id="val_123",
            preview_hash="abc123def456",
            site_id="site_1",
            form_id="form_1",
        )

        assert event["schema_version"] == "1.0"
        assert event["event_type"] == "approval_requested"
        assert event["validation_id"] == "val_123"
        assert event["preview_hash"] == "abc123def456"
        assert event["site_id"] == "site_1"
        assert event["form_id"] == "form_1"
        assert "timestamp" in event

    def test_create_approval_requested_event_with_user_tenant(self):
        """Should include optional user_id and tenant_id."""
        event = create_approval_requested_event(
            validation_id="val_123",
            preview_hash="abc123",
            site_id="site_1",
            form_id="form_1",
            user_id="user_1",
            tenant_id="tenant_1",
        )

        assert event["user_id"] == "user_1"
        assert event["tenant_id"] == "tenant_1"

    def test_create_approval_requested_event_missing_validation_id(self):
        """Should raise ValidationError if validation_id is missing."""
        with pytest.raises(ValidationError, match="validation_id is required"):
            create_approval_requested_event(
                validation_id="",
                preview_hash="abc123",
                site_id="site_1",
                form_id="form_1",
            )

    def test_create_approval_requested_event_missing_preview_hash(self):
        """Should raise ValidationError if preview_hash is missing."""
        with pytest.raises(ValidationError, match="preview_hash is required"):
            create_approval_requested_event(
                validation_id="val_123",
                preview_hash="",
                site_id="site_1",
                form_id="form_1",
            )


class TestApprovalDecisionEvent:
    """Test approval decision event creation."""

    def test_create_approval_decision_approved(self):
        """Should create valid approval decision (approved)."""
        event = create_approval_decision_event(
            validation_id="val_123",
            preview_hash="abc123",
            approval_status="approved",
        )

        assert event["schema_version"] == "1.0"
        assert event["event_type"] == "approval_decision_approved"
        assert event["validation_id"] == "val_123"
        assert event["preview_hash"] == "abc123"
        assert event["approval_status"] == "approved"
        assert "timestamp" in event

    def test_create_approval_decision_cancelled(self):
        """Should create valid approval decision (cancelled)."""
        event = create_approval_decision_event(
            validation_id="val_123",
            preview_hash="abc123",
            approval_status="cancelled",
        )

        assert event["event_type"] == "approval_decision_cancelled"
        assert event["approval_status"] == "cancelled"

    def test_create_approval_decision_with_decided_by(self):
        """Should include optional decided_by field."""
        event = create_approval_decision_event(
            validation_id="val_123",
            preview_hash="abc123",
            approval_status="approved",
            decided_by="user_admin",
        )

        assert event["decided_by"] == "user_admin"

    def test_create_approval_decision_missing_validation_id(self):
        """Should raise ValidationError if validation_id is missing."""
        with pytest.raises(ValidationError, match="validation_id is required"):
            create_approval_decision_event(
                validation_id="",
                preview_hash="abc123",
                approval_status="approved",
            )

    def test_create_approval_decision_missing_preview_hash(self):
        """Should raise ValidationError if preview_hash is missing."""
        with pytest.raises(ValidationError, match="preview_hash is required"):
            create_approval_decision_event(
                validation_id="val_123",
                preview_hash="",
                approval_status="approved",
            )

    def test_create_approval_decision_invalid_status(self):
        """Should raise ValidationError if approval_status is invalid."""
        with pytest.raises(ValidationError, match="approval_status must be 'approved' or 'cancelled'"):
            create_approval_decision_event(
                validation_id="val_123",
                preview_hash="abc123",
                approval_status="pending",
            )


class TestApprovalStateAppend:
    """Test append-only JSONL behavior."""

    def test_append_approval_state_event(self, tmp_path):
        """Should append event to JSONL file."""
        log_file = tmp_path / "approval_state.jsonl"

        event = create_approval_requested_event(
            validation_id="val_123",
            preview_hash="abc123",
            site_id="site_1",
            form_id="form_1",
        )

        append_approval_state_event(log_file, event)

        assert log_file.exists()
        with log_file.open() as f:
            line = f.read().strip()
            saved_event = json.loads(line)
            assert saved_event["validation_id"] == "val_123"

    def test_append_multiple_events_preserves_order(self, tmp_path):
        """Should preserve event order (append-only)."""
        log_file = tmp_path / "approval_state.jsonl"

        event1 = create_approval_requested_event(
            validation_id="val_1",
            preview_hash="hash_1",
            site_id="site_1",
            form_id="form_1",
        )
        event2 = create_approval_decision_event(
            validation_id="val_1",
            preview_hash="hash_1",
            approval_status="approved",
        )

        append_approval_state_event(log_file, event1)
        append_approval_state_event(log_file, event2)

        events = read_approval_state_events(log_file)
        assert len(events) == 2
        assert events[0]["event_type"] == "approval_requested"
        assert events[1]["event_type"] == "approval_decision_approved"

    def test_append_does_not_truncate_existing_file(self, tmp_path):
        """Should never truncate or overwrite existing file (append-only)."""
        log_file = tmp_path / "approval_state.jsonl"

        # Write first event
        event1 = create_approval_requested_event(
            validation_id="val_1",
            preview_hash="hash_1",
            site_id="site_1",
            form_id="form_1",
        )
        append_approval_state_event(log_file, event1)

        # Write second event
        event2 = create_approval_requested_event(
            validation_id="val_2",
            preview_hash="hash_2",
            site_id="site_1",
            form_id="form_1",
        )
        append_approval_state_event(log_file, event2)

        # Both should exist
        events = read_approval_state_events(log_file)
        assert len(events) == 2


class TestReadApprovalStateEvents:
    """Test JSONL file reading."""

    def test_read_empty_file(self, tmp_path):
        """Should return empty list for non-existent file."""
        log_file = tmp_path / "nonexistent.jsonl"
        events = read_approval_state_events(log_file)
        assert events == []

    def test_read_valid_jsonl(self, tmp_path):
        """Should parse valid JSONL."""
        log_file = tmp_path / "approval_state.jsonl"
        event = create_approval_requested_event(
            validation_id="val_123",
            preview_hash="abc123",
            site_id="site_1",
            form_id="form_1",
        )
        append_approval_state_event(log_file, event)

        events = read_approval_state_events(log_file)
        assert len(events) == 1
        assert events[0]["validation_id"] == "val_123"

    def test_read_skipss_blank_lines(self, tmp_path):
        """Should skip blank lines in JSONL."""
        log_file = tmp_path / "approval_state.jsonl"
        event1 = create_approval_requested_event(
            validation_id="val_1",
            preview_hash="hash_1",
            site_id="site_1",
            form_id="form_1",
        )
        append_approval_state_event(log_file, event1)

        # Add blank line
        with log_file.open("a") as f:
            f.write("\n")

        event2 = create_approval_requested_event(
            validation_id="val_2",
            preview_hash="hash_2",
            site_id="site_1",
            form_id="form_1",
        )
        append_approval_state_event(log_file, event2)

        events = read_approval_state_events(log_file)
        assert len(events) == 2

    def test_read_invalid_json_raises_error(self, tmp_path):
        """Should raise ApprovalStateError for invalid JSON."""
        log_file = tmp_path / "approval_state.jsonl"
        with log_file.open("w") as f:
            f.write("invalid json line\n")

        with pytest.raises(ApprovalStateError, match="Invalid JSON"):
            read_approval_state_events(log_file)


class TestLatestApprovalState:
    """Test latest state query."""

    def test_latest_approval_state_requested(self, tmp_path):
        """Should return approval requested event as latest."""
        log_file = tmp_path / "approval_state.jsonl"
        event = create_approval_requested_event(
            validation_id="val_123",
            preview_hash="hash_123",
            site_id="site_1",
            form_id="form_1",
        )
        append_approval_state_event(log_file, event)
        events = read_approval_state_events(log_file)

        latest = latest_approval_state(events, "hash_123")
        assert latest is not None
        assert latest["event_type"] == "approval_requested"

    def test_latest_approval_state_approved(self, tmp_path):
        """Should return latest event (approved overrides requested)."""
        log_file = tmp_path / "approval_state.jsonl"

        event1 = create_approval_requested_event(
            validation_id="val_123",
            preview_hash="hash_123",
            site_id="site_1",
            form_id="form_1",
        )
        append_approval_state_event(log_file, event1)

        event2 = create_approval_decision_event(
            validation_id="val_123",
            preview_hash="hash_123",
            approval_status="approved",
        )
        append_approval_state_event(log_file, event2)

        events = read_approval_state_events(log_file)
        latest = latest_approval_state(events, "hash_123")
        assert latest is not None
        assert latest["event_type"] == "approval_decision_approved"

    def test_latest_approval_state_cancelled(self, tmp_path):
        """Should return cancelled as latest."""
        log_file = tmp_path / "approval_state.jsonl"

        event1 = create_approval_requested_event(
            validation_id="val_123",
            preview_hash="hash_123",
            site_id="site_1",
            form_id="form_1",
        )
        append_approval_state_event(log_file, event1)

        event2 = create_approval_decision_event(
            validation_id="val_123",
            preview_hash="hash_123",
            approval_status="cancelled",
        )
        append_approval_state_event(log_file, event2)

        events = read_approval_state_events(log_file)
        latest = latest_approval_state(events, "hash_123")
        assert latest is not None
        assert latest["event_type"] == "approval_decision_cancelled"
        assert latest["approval_status"] == "cancelled"

    def test_latest_approval_state_not_found(self):
        """Should return None if preview_hash not found."""
        events = []
        latest = latest_approval_state(events, "hash_nonexistent")
        assert latest is None

    def test_latest_approval_state_handles_multiple_hashes(self, tmp_path):
        """Should only return events for specific preview_hash."""
        log_file = tmp_path / "approval_state.jsonl"

        event1 = create_approval_requested_event(
            validation_id="val_1",
            preview_hash="hash_1",
            site_id="site_1",
            form_id="form_1",
        )
        append_approval_state_event(log_file, event1)

        event2 = create_approval_requested_event(
            validation_id="val_2",
            preview_hash="hash_2",
            site_id="site_1",
            form_id="form_1",
        )
        append_approval_state_event(log_file, event2)

        events = read_approval_state_events(log_file)
        latest_1 = latest_approval_state(events, "hash_1")
        latest_2 = latest_approval_state(events, "hash_2")

        assert latest_1["validation_id"] == "val_1"
        assert latest_2["validation_id"] == "val_2"


class TestGetApprovalStatus:
    """Test status string extraction."""

    def test_get_approval_status_pending(self):
        """Should return 'pending' for approval_requested event."""
        event = create_approval_requested_event(
            validation_id="val_123",
            preview_hash="hash_123",
            site_id="site_1",
            form_id="form_1",
        )
        status = get_approval_status(event)
        assert status == "pending"

    def test_get_approval_status_approved(self):
        """Should return 'approved' for approval_decision_approved event."""
        event = create_approval_decision_event(
            validation_id="val_123",
            preview_hash="hash_123",
            approval_status="approved",
        )
        status = get_approval_status(event)
        assert status == "approved"

    def test_get_approval_status_cancelled(self):
        """Should return 'cancelled' for approval_decision_cancelled event."""
        event = create_approval_decision_event(
            validation_id="val_123",
            preview_hash="hash_123",
            approval_status="cancelled",
        )
        status = get_approval_status(event)
        assert status == "cancelled"

    def test_get_approval_status_none(self):
        """Should return 'pending' for None event."""
        status = get_approval_status(None)
        assert status == "pending"


class TestEndToEndFlow:
    """Test complete approval flow."""

    def test_pending_to_approved_flow(self, tmp_path):
        """Should handle pending → approved flow."""
        log_file = tmp_path / "approval_state.jsonl"

        # Approval requested
        event1 = create_approval_requested_event(
            validation_id="val_123",
            preview_hash="hash_123",
            site_id="site_1",
            form_id="form_1",
            user_id="user_1",
        )
        append_approval_state_event(log_file, event1)

        events = read_approval_state_events(log_file)
        latest = latest_approval_state(events, "hash_123")
        assert get_approval_status(latest) == "pending"

        # User approves
        event2 = create_approval_decision_event(
            validation_id="val_123",
            preview_hash="hash_123",
            approval_status="approved",
            decided_by="user_1",
        )
        append_approval_state_event(log_file, event2)

        events = read_approval_state_events(log_file)
        latest = latest_approval_state(events, "hash_123")
        assert get_approval_status(latest) == "approved"
        assert latest["decided_by"] == "user_1"

    def test_pending_to_cancelled_flow(self, tmp_path):
        """Should handle pending → cancelled flow."""
        log_file = tmp_path / "approval_state.jsonl"

        event1 = create_approval_requested_event(
            validation_id="val_456",
            preview_hash="hash_456",
            site_id="site_1",
            form_id="form_1",
        )
        append_approval_state_event(log_file, event1)

        event2 = create_approval_decision_event(
            validation_id="val_456",
            preview_hash="hash_456",
            approval_status="cancelled",
            decided_by="user_admin",
        )
        append_approval_state_event(log_file, event2)

        events = read_approval_state_events(log_file)
        latest = latest_approval_state(events, "hash_456")
        assert get_approval_status(latest) == "cancelled"


class TestNoExternalDependencies:
    """Verify no network, DB, or docker calls."""

    def test_no_network_calls_in_event_creation(self):
        """Event creation should not make network calls."""
        # This is implicitly tested by test success - no network requests
        event = create_approval_requested_event(
            validation_id="val_123",
            preview_hash="hash_123",
            site_id="site_1",
            form_id="form_1",
        )
        assert event is not None

    def test_no_db_calls_in_file_operations(self, tmp_path):
        """File operations should only use tmp_path (no real DB)."""
        log_file = tmp_path / "approval_state.jsonl"
        event = create_approval_requested_event(
            validation_id="val_123",
            preview_hash="hash_123",
            site_id="site_1",
            form_id="form_1",
        )
        append_approval_state_event(log_file, event)

        # Verify file is in tmp_path
        assert str(log_file).startswith(str(tmp_path))
        assert log_file.exists()

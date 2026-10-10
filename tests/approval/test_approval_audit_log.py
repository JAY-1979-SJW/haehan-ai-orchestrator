"""Unit tests for approval audit log integration.

Validates that approval token lifecycle events are recorded in audit log.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from ai_orchestrator.core.models import RiskAssessment, TaskRequest
from tools.gates import approval


def test_issue_token_logs_audit_event(tmp_path, monkeypatch):
    """Verify that issue_token calls log_event with APPROVAL_ISSUED event."""
    # Mock audit log path
    mock_log_path = tmp_path / "audit.log"  # noqa: F841

    with patch("tools.gates.approval.log_event") as mock_log:
        req = TaskRequest(
            task_id="test-task-001",
            source="server",
            action_type="capture_screenshot",
            target="/",
            description="Test action",
            requested_by="test_user",
        )
        risk = RiskAssessment(
            risk_level="high",
            requires_approval=True,
            reasons=["High-risk action"],
        )

        token = approval.issue_token(req, risk)  # noqa: F841

        # Verify log_event was called
        mock_log.assert_called_once()
        call_args = mock_log.call_args

        assert call_args[1]["event_type"] == "APPROVAL_ISSUED"
        assert call_args[1]["task_id"] == "test-task-001"
        assert call_args[1]["risk_level"] == "high"
        assert call_args[1]["actor"] == "test_user"
        # public_id should be in note, not token_id
        assert "public_id" in call_args[1]["note"]
        # token_id should NOT be recorded
        assert "token_id" not in call_args[1] or call_args[1].get("token_id") == ""


def test_approve_token_logs_audit_event(monkeypatch):
    """Verify that approve_token calls log_event with APPROVAL_GRANTED event."""
    # Create a token first
    req = TaskRequest(
        task_id="test-task-002",
        source="server",
        action_type="capture_screenshot",
        target="/",
        description="Test action",
        requested_by="test_user",
    )
    risk = RiskAssessment(
        risk_level="high",
        requires_approval=True,
        reasons=["High-risk action"],
    )

    with patch("tools.gates.approval.log_event") as mock_log:
        token = approval.issue_token(req, risk)
        mock_log.reset_mock()

        # Now approve
        _approved_token, _status = approval.approve_token(
            token.token_id,
            token.task_id,
            "approver_user",
            "admin",
        )

        # Verify log_event was called for approval
        # It should be called once for successful approval
        calls = [c for c in mock_log.call_args_list if c[1].get("event_type") == "APPROVAL_GRANTED"]
        assert len(calls) >= 1, "APPROVAL_GRANTED event should be logged"

        call = calls[0]
        assert call[1]["task_id"] == "test-task-002"
        assert call[1]["decision"] == "approved"
        assert call[1]["actor"] == "approver_user"


def test_reject_token_logs_audit_event(monkeypatch):
    """Verify that reject_token calls log_event with APPROVAL_REJECTED event."""
    req = TaskRequest(
        task_id="test-task-003",
        source="server",
        action_type="capture_screenshot",
        target="/",
        description="Test action",
        requested_by="test_user",
    )
    risk = RiskAssessment(
        risk_level="high",
        requires_approval=True,
        reasons=["High-risk action"],
    )

    with patch("tools.gates.approval.log_event") as mock_log:
        token = approval.issue_token(req, risk)
        mock_log.reset_mock()

        # Reject
        _rejected_token, _status = approval.reject_token(
            token.token_id,
            token.task_id,
            "reviewer_user",
            "admin",
            reason="Not approved",
        )

        # Verify log_event was called for rejection
        calls = [c for c in mock_log.call_args_list if c[1].get("event_type") == "APPROVAL_REJECTED"]
        assert len(calls) >= 1, "APPROVAL_REJECTED event should be logged"

        call = calls[0]
        assert call[1]["task_id"] == "test-task-003"
        assert call[1]["decision"] == "rejected"
        assert call[1]["actor"] == "reviewer_user"


def test_token_expiry_logs_audit_event(monkeypatch):
    """Verify that token expiry is logged with APPROVAL_EXPIRED event."""
    req = TaskRequest(
        task_id="test-task-004",
        source="server",
        action_type="capture_screenshot",
        target="/",
        description="Test action",
        requested_by="test_user",
    )
    risk = RiskAssessment(
        risk_level="high",
        requires_approval=True,
        reasons=["High-risk action"],
    )

    with patch("tools.gates.approval.log_event") as mock_log:
        # Issue token with very short TTL
        token = approval.issue_token(req, risk, ttl_minutes=0)

        # Simulate time passing
        with patch("tools.gates.approval._now") as mock_now:
            mock_now.return_value = datetime.now(UTC) + timedelta(minutes=1)

            # Try to approve - should detect expiry
            _approved_token, status = approval.approve_token(
                token.token_id,
                token.task_id,
                "approver_user",
                "admin",
            )

            assert status == "expired"

            # Verify expiry was logged
            expired_calls = [c for c in mock_log.call_args_list if c[1].get("event_type") == "APPROVAL_EXPIRED"]
            assert len(expired_calls) >= 1, "APPROVAL_EXPIRED event should be logged"


def test_audit_log_no_token_id_original(monkeypatch):
    """Verify that token_id original value is never recorded in audit log."""
    req = TaskRequest(
        task_id="test-task-005",
        source="server",
        action_type="capture_screenshot",
        target="/",
        description="Test action",
        requested_by="test_user",
    )
    risk = RiskAssessment(
        risk_level="high",
        requires_approval=True,
        reasons=["High-risk action"],
    )

    with patch("tools.gates.approval.log_event") as mock_log:
        token = approval.issue_token(req, risk)

        # Check all log_event calls
        for call in mock_log.call_args_list:
            call_kwargs = call[1]
            # token_id parameter should be empty or not contain actual token
            token_id_value = call_kwargs.get("token_id", "")
            assert token_id_value != token.token_id, "Token ID should not be recorded in audit log"
            # Note should not contain token_id original
            note = call_kwargs.get("note", "")
            assert token.token_id not in note, "Token ID should not appear in audit note"


def test_audit_log_includes_public_id(monkeypatch):
    """Verify that public_id is recorded in audit log."""
    req = TaskRequest(
        task_id="test-task-006",
        source="server",
        action_type="capture_screenshot",
        target="/",
        description="Test action",
        requested_by="test_user",
    )
    risk = RiskAssessment(
        risk_level="high",
        requires_approval=True,
        reasons=["High-risk action"],
    )

    with patch("tools.gates.approval.log_event") as mock_log:
        token = approval.issue_token(req, risk)

        # First call should be for APPROVAL_ISSUED with public_id in note
        assert mock_log.call_count >= 1
        call = mock_log.call_args_list[0]
        call_kwargs = call[1]

        assert call_kwargs.get("event_type") == "APPROVAL_ISSUED"
        note = call_kwargs.get("note", "")
        assert token.public_id in note, f"Public ID {token.public_id} should be in audit log note"


def test_audit_log_no_sensitive_fields(monkeypatch):
    """Verify that sensitive fields are not recorded in audit log."""
    # Sensitive field patterns to avoid
    sensitive_patterns = ["password", "secret", "token", "cookie", "session", "api_key", "auth", "credential"]

    req = TaskRequest(
        task_id="test-task-007",
        source="server",
        action_type="capture_screenshot",
        target="/",
        description="Test action",
        requested_by="test_user",
    )
    risk = RiskAssessment(
        risk_level="high",
        requires_approval=True,
        reasons=["High-risk action"],
    )

    with patch("tools.gates.approval.log_event") as mock_log:
        token = approval.issue_token(req, risk)  # noqa: F841

        # Check all log_event calls
        for call in mock_log.call_args_list:
            call_kwargs = call[1]
            for field_name, field_value in call_kwargs.items():
                if isinstance(field_value, str):
                    field_lower = field_value.lower()
                    for pattern in sensitive_patterns:
                        # Check that sensitive values don't appear
                        # (field names like "token_id" are OK, but not values)
                        if field_name not in ("event_type", "note"):
                            assert pattern not in field_lower or field_value in (
                                "",
                                "approved",
                                "rejected",
                                "issued",
                                "expired",
                            ), f"Sensitive pattern '{pattern}' found in {field_name}={field_value}"

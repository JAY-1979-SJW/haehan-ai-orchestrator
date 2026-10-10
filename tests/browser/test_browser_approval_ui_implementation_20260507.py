"""Test suite for browser approval UI/API implementation.

Tests cover:
- FastAPI router endpoints
- Approval request creation and retrieval
- Approval decision (approve/reject)
- Approval history tracking
- Real API responses (no mock data)
- Response schema validation
- Integration with approval_record_store

Tests are read-only (test-only JSONL store, no DB write).
"""

import json

import pytest
from fastapi.testclient import TestClient

from ai_orchestrator.asgi import app
from ai_orchestrator.browser_tool.approval.approval_record_store import (
    read_approval_records,
)
from ai_orchestrator.core.config import APPROVAL_RECORD_STORE_PATH


@pytest.fixture
def client(monkeypatch):
    """FastAPI test client."""
    import ai_orchestrator.core.config as config

    monkeypatch.setattr(config, "AUTH_ENABLED", False)
    return TestClient(app)


@pytest.fixture(autouse=True)
def cleanup_store():
    """Clean up test JSONL file before and after each test."""
    if APPROVAL_RECORD_STORE_PATH.exists():
        APPROVAL_RECORD_STORE_PATH.unlink()
    yield
    if APPROVAL_RECORD_STORE_PATH.exists():
        APPROVAL_RECORD_STORE_PATH.unlink()


class TestApprovalListEndpoint:
    """Test GET /api/v1/browser-approvals/requests"""

    def test_list_approvals_empty(self, client):
        """Test listing approvals when none exist."""
        response = client.get("/api/v1/browser-approvals/requests")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["count"] == 0
        assert data["approvals"] == []

    def test_list_approvals_with_records(self, client):
        """Test listing approvals after creating one."""
        # Create approval
        create_response = client.post(
            "/api/v1/browser-approvals/requests",
            json={
                "workflow_run_id": "run_001",
                "workflow_id": "workflow_001",
                "action_name": "browser.execute_click",
                "operation_type": "click",
                "approval_scope": "click_action",
                "requested_by": "user001",
                "requested_role": "user",
                "tenant_id": "tenant_001",
                "user_id": "user_001",
                "site_id": "site_001",
                "target_domain": "example.com",
                "target_url": "https://example.com/form?password=secret",
                "request_reason": "Automated form filling",
                "expires_in_hours": 24,
            },
        )
        assert create_response.status_code == 200
        assert create_response.json()["approval_id"]

        # List approvals
        list_response = client.get("/api/v1/browser-approvals/requests")
        assert list_response.status_code == 200
        data = list_response.json()
        assert data["ok"] is True
        assert data["count"] == 1
        assert len(data["approvals"]) == 1
        assert data["approvals"][0]["approval_status"] == "PENDING"

    def test_list_approvals_filter_by_status(self, client):
        """Test filtering approvals by status."""
        # Create and approve one
        create_response = client.post(
            "/api/v1/browser-approvals/requests",
            json={
                "workflow_run_id": "run_001",
                "workflow_id": "workflow_001",
                "action_name": "browser.execute_click",
                "operation_type": "click",
                "requested_by": "user001",
                "requested_role": "user",
                "tenant_id": "tenant_001",
                "user_id": "user_001",
                "site_id": "site_001",
                "target_domain": "example.com",
                "target_url": "https://example.com",
                "request_reason": "Test",
            },
        )
        approval_id = create_response.json()["approval_id"]

        # Approve it
        approve_response = client.post(
            f"/api/v1/browser-approvals/requests/{approval_id}/approve",
            json={
                "decided_by": "admin",
                "decided_role": "admin",
                "decision_reason": "Approved",
            },
        )
        assert approve_response.status_code == 200

        # Filter by APPROVED status
        list_response = client.get("/api/v1/browser-approvals/requests?status=APPROVED")
        data = list_response.json()
        assert data["count"] == 1
        assert data["approvals"][0]["approval_status"] == "APPROVED"


class TestCreateApprovalEndpoint:
    """Test POST /api/v1/browser-approvals/requests"""

    def test_create_approval_minimal(self, client):
        """Test creating approval with minimal fields."""
        response = client.post(
            "/api/v1/browser-approvals/requests",
            json={
                "workflow_run_id": "run_001",
                "workflow_id": "workflow_001",
                "action_name": "browser.execute_click",
                "operation_type": "click",
                "requested_by": "user001",
                "requested_role": "user",
                "tenant_id": "tenant_001",
                "user_id": "user_001",
                "site_id": "site_001",
                "target_domain": "example.com",
                "target_url": "https://example.com",
                "request_reason": "Test action",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["approval_id"]
        assert data["approval_event_id"]
        assert data["approval_status"] == "PENDING"
        assert data["approval_event_type"] == "APPROVAL_REQUESTED"
        assert data["safe_to_execute"] is False
        assert data["created_at"]
        assert data["expires_at"]

    def test_create_approval_url_redaction(self, client):
        """Test URL redaction in approval creation."""
        response = client.post(
            "/api/v1/browser-approvals/requests",
            json={
                "workflow_run_id": "run_001",
                "workflow_id": "workflow_001",
                "action_name": "browser.execute_type",
                "operation_type": "type",
                "requested_by": "user001",
                "requested_role": "user",
                "tenant_id": "tenant_001",
                "user_id": "user_001",
                "site_id": "site_001",
                "target_domain": "api.example.com",
                "target_url": "https://api.example.com/login?username=admin&password=secret123&token=abc123xyz",
                "request_reason": "Login form",
            },
        )
        assert response.status_code == 200
        data = response.json()

        # Check URL is redacted (either literal or URL-encoded brackets)
        url_redacted = data["target_url_redacted"]
        assert "REDACTED" in url_redacted, f"Expected REDACTED in {url_redacted}"
        assert "secret123" not in url_redacted
        assert "abc123xyz" not in url_redacted

        # Check hash is present
        assert data["target_url_hash"]
        assert len(data["target_url_hash"]) == 64  # SHA256 hex

    def test_create_approval_safe_to_execute_always_false(self, client):
        """Test that safe_to_execute is always false."""
        response = client.post(
            "/api/v1/browser-approvals/requests",
            json={
                "workflow_run_id": "run_001",
                "workflow_id": "workflow_001",
                "action_name": "browser.execute_submit",
                "operation_type": "submit",
                "requested_by": "user001",
                "requested_role": "user",
                "tenant_id": "tenant_001",
                "user_id": "user_001",
                "site_id": "site_001",
                "target_domain": "example.com",
                "target_url": "https://example.com/submit",
                "request_reason": "Form submission",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["safe_to_execute"] is False


class TestGetApprovalEndpoint:
    """Test GET /api/v1/browser-approvals/requests/{approval_id}"""

    def test_get_approval_not_found(self, client):
        """Test getting non-existent approval."""
        response = client.get("/api/v1/browser-approvals/requests/nonexistent")
        assert response.status_code == 404

    def test_get_approval_success(self, client):
        """Test getting existing approval."""
        # Create approval
        create_response = client.post(
            "/api/v1/browser-approvals/requests",
            json={
                "workflow_run_id": "run_001",
                "workflow_id": "workflow_001",
                "action_name": "browser.execute_click",
                "operation_type": "click",
                "requested_by": "user001",
                "requested_role": "user",
                "tenant_id": "tenant_001",
                "user_id": "user_001",
                "site_id": "site_001",
                "target_domain": "example.com",
                "target_url": "https://example.com",
                "request_reason": "Test",
            },
        )
        approval_id = create_response.json()["approval_id"]

        # Get approval
        get_response = client.get(f"/api/v1/browser-approvals/requests/{approval_id}")
        assert get_response.status_code == 200
        data = get_response.json()
        assert data["approval_id"] == approval_id
        assert data["approval_status"] == "PENDING"


class TestApproveEndpoint:
    """Test POST /api/v1/browser-approvals/requests/{approval_id}/approve"""

    def test_approve_success(self, client):
        """Test approving a request."""
        # Create approval
        create_response = client.post(
            "/api/v1/browser-approvals/requests",
            json={
                "workflow_run_id": "run_001",
                "workflow_id": "workflow_001",
                "action_name": "browser.execute_click",
                "operation_type": "click",
                "requested_by": "user001",
                "requested_role": "user",
                "tenant_id": "tenant_001",
                "user_id": "user_001",
                "site_id": "site_001",
                "target_domain": "example.com",
                "target_url": "https://example.com",
                "request_reason": "Test",
            },
        )
        approval_id = create_response.json()["approval_id"]

        # Approve
        approve_response = client.post(
            f"/api/v1/browser-approvals/requests/{approval_id}/approve",
            json={
                "decided_by": "admin",
                "decided_role": "admin",
                "decision_reason": "Approved for test",
            },
        )
        assert approve_response.status_code == 200
        data = approve_response.json()
        assert data["approval_status"] == "APPROVED"
        assert data["approval_event_type"] == "APPROVAL_GRANTED"
        assert data["decided_by"] == "admin"
        assert data["safe_to_execute"] is False  # Still false even after approval

    def test_approve_maintains_safe_to_execute_false(self, client):
        """Test that approval doesn't change safe_to_execute to true."""
        # Create and approve
        create_response = client.post(
            "/api/v1/browser-approvals/requests",
            json={
                "workflow_run_id": "run_001",
                "workflow_id": "workflow_001",
                "action_name": "browser.execute_submit",
                "operation_type": "submit",
                "requested_by": "user001",
                "requested_role": "user",
                "tenant_id": "tenant_001",
                "user_id": "user_001",
                "site_id": "site_001",
                "target_domain": "example.com",
                "target_url": "https://example.com/submit",
                "request_reason": "Form submission",
            },
        )
        approval_id = create_response.json()["approval_id"]

        approve_response = client.post(
            f"/api/v1/browser-approvals/requests/{approval_id}/approve",
            json={
                "decided_by": "admin",
                "decided_role": "admin",
                "decision_reason": "Approved",
            },
        )
        assert approve_response.json()["safe_to_execute"] is False


class TestRejectEndpoint:
    """Test POST /api/v1/browser-approvals/requests/{approval_id}/reject"""

    def test_reject_success(self, client):
        """Test rejecting a request."""
        # Create approval
        create_response = client.post(
            "/api/v1/browser-approvals/requests",
            json={
                "workflow_run_id": "run_001",
                "workflow_id": "workflow_001",
                "action_name": "browser.execute_click",
                "operation_type": "click",
                "requested_by": "user001",
                "requested_role": "user",
                "tenant_id": "tenant_001",
                "user_id": "user_001",
                "site_id": "site_001",
                "target_domain": "example.com",
                "target_url": "https://example.com",
                "request_reason": "Test",
            },
        )
        approval_id = create_response.json()["approval_id"]

        # Reject
        reject_response = client.post(
            f"/api/v1/browser-approvals/requests/{approval_id}/reject",
            json={
                "decided_by": "admin",
                "decided_role": "admin",
                "decision_reason": "Suspicious activity",
            },
        )
        assert reject_response.status_code == 200
        data = reject_response.json()
        assert data["approval_status"] == "REJECTED"
        assert data["approval_event_type"] == "APPROVAL_REJECTED"
        assert data["decided_by"] == "admin"


class TestHistoryEndpoint:
    """Test GET /api/v1/browser-approvals/requests/{approval_id}/history"""

    def test_history_single_event(self, client):
        """Test history with single request event."""
        # Create approval
        create_response = client.post(
            "/api/v1/browser-approvals/requests",
            json={
                "workflow_run_id": "run_001",
                "workflow_id": "workflow_001",
                "action_name": "browser.execute_click",
                "operation_type": "click",
                "requested_by": "user001",
                "requested_role": "user",
                "tenant_id": "tenant_001",
                "user_id": "user_001",
                "site_id": "site_001",
                "target_domain": "example.com",
                "target_url": "https://example.com",
                "request_reason": "Test",
            },
        )
        approval_id = create_response.json()["approval_id"]

        # Get history
        history_response = client.get(f"/api/v1/browser-approvals/requests/{approval_id}/history")
        assert history_response.status_code == 200
        data = history_response.json()
        assert data["ok"] is True
        assert data["approval_id"] == approval_id
        assert data["count"] == 1
        assert len(data["events"]) == 1
        assert data["events"][0]["approval_event_type"] == "APPROVAL_REQUESTED"

    def test_history_multiple_events(self, client):
        """Test history with multiple events (request -> approve)."""
        # Create approval
        create_response = client.post(
            "/api/v1/browser-approvals/requests",
            json={
                "workflow_run_id": "run_001",
                "workflow_id": "workflow_001",
                "action_name": "browser.execute_click",
                "operation_type": "click",
                "requested_by": "user001",
                "requested_role": "user",
                "tenant_id": "tenant_001",
                "user_id": "user_001",
                "site_id": "site_001",
                "target_domain": "example.com",
                "target_url": "https://example.com",
                "request_reason": "Test",
            },
        )
        approval_id = create_response.json()["approval_id"]

        # Approve
        client.post(
            f"/api/v1/browser-approvals/requests/{approval_id}/approve",
            json={
                "decided_by": "admin",
                "decided_role": "admin",
                "decision_reason": "Approved",
            },
        )

        # Get history
        history_response = client.get(f"/api/v1/browser-approvals/requests/{approval_id}/history")
        data = history_response.json()
        assert data["count"] == 2
        assert len(data["events"]) == 2
        assert data["events"][0]["approval_event_type"] == "APPROVAL_REQUESTED"
        assert data["events"][1]["approval_event_type"] == "APPROVAL_GRANTED"


class TestResponseSchema:
    """Test response schema validation."""

    def test_approval_record_response_fields(self, client):
        """Test that approval responses have required fields."""
        # Create approval
        create_response = client.post(
            "/api/v1/browser-approvals/requests",
            json={
                "workflow_run_id": "run_001",
                "workflow_id": "workflow_001",
                "action_name": "browser.execute_click",
                "operation_type": "click",
                "requested_by": "user001",
                "requested_role": "user",
                "tenant_id": "tenant_001",
                "user_id": "user_001",
                "site_id": "site_001",
                "target_domain": "example.com",
                "target_url": "https://example.com",
                "request_reason": "Test",
            },
        )
        data = create_response.json()

        # Check required fields
        assert "approval_event_id" in data
        assert "approval_id" in data
        assert "workflow_run_id" in data
        assert "approval_status" in data
        assert "approval_event_type" in data
        assert "created_at" in data
        assert "target_url_redacted" in data
        assert "target_url_hash" in data
        assert "safe_to_execute" in data
        assert "approval_required" in data

        # Check no sensitive data leaked
        assert "password" not in str(data).lower() or "[REDACTED]" in data["target_url_redacted"]


class TestAppendOnlyBehavior:
    """Test append-only JSONL behavior."""

    def test_records_are_appended_not_overwritten(self, client):
        """Test that records are appended to JSONL, not overwritten."""
        # Create first approval
        client.post(
            "/api/v1/browser-approvals/requests",
            json={
                "workflow_run_id": "run_001",
                "workflow_id": "workflow_001",
                "action_name": "browser.execute_click",
                "operation_type": "click",
                "requested_by": "user001",
                "requested_role": "user",
                "tenant_id": "tenant_001",
                "user_id": "user_001",
                "site_id": "site_001",
                "target_domain": "example.com",
                "target_url": "https://example.com",
                "request_reason": "Test 1",
            },
        )

        # Create second approval
        client.post(
            "/api/v1/browser-approvals/requests",
            json={
                "workflow_run_id": "run_002",
                "workflow_id": "workflow_002",
                "action_name": "browser.execute_type",
                "operation_type": "type",
                "requested_by": "user002",
                "requested_role": "user",
                "tenant_id": "tenant_001",
                "user_id": "user_002",
                "site_id": "site_001",
                "target_domain": "example.com",
                "target_url": "https://example.com",
                "request_reason": "Test 2",
            },
        )

        # Check JSONL file has both records
        records = read_approval_records(APPROVAL_RECORD_STORE_PATH)
        assert len(records) == 2
        assert records[0]["approval_event_type"] == "APPROVAL_REQUESTED"
        assert records[1]["approval_event_type"] == "APPROVAL_REQUESTED"


class TestApprovalAuthGate:
    """Approval APIs must require admin/owner when auth is enabled."""

    def test_list_requires_auth_when_enabled(self, monkeypatch, tmp_path):
        import ai_orchestrator.core.config as config

        monkeypatch.setattr(config, "AUTH_ENABLED", True)
        monkeypatch.setattr(config, "HTTP_USERS_PATH", tmp_path / "http_users.json")
        config.HTTP_USERS_PATH.write_text(
            json.dumps(
                [
                    {"username": "admin_u", "password_hash": "pw-admin", "role": "admin", "enabled": True},
                ]
            ),
            encoding="utf-8",
        )
        secure_client = TestClient(app)
        response = secure_client.get("/api/v1/browser-approvals/requests")
        assert response.status_code == 401

    def test_viewer_blocked_when_enabled(self, monkeypatch, tmp_path):
        import ai_orchestrator.core.config as config

        monkeypatch.setattr(config, "AUTH_ENABLED", True)
        monkeypatch.setattr(config, "HTTP_USERS_PATH", tmp_path / "http_users.json")
        config.HTTP_USERS_PATH.write_text(
            json.dumps(
                [
                    {"username": "viewer_u", "password_hash": "pw-viewer", "role": "viewer", "enabled": True},
                ]
            ),
            encoding="utf-8",
        )
        secure_client = TestClient(app)
        response = secure_client.get(
            "/api/v1/browser-approvals/requests",
            auth=("viewer_u", "pw-viewer"),
        )
        assert response.status_code == 403

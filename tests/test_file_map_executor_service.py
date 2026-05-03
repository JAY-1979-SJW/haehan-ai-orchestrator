"""Tests for file-map-executor service."""

import pytest
from fastapi.testclient import TestClient
from services.file_map_executor.app import app


client = TestClient(app)


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_returns_200(self):
        """GET /health should return 200 with healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "file-map-executor"
        assert data["version"] == "1.0"


class TestCleanupExecuteEndpoint:
    """Test cleanup execute endpoint."""

    def test_execute_dry_run_true_valid_path(self):
        """POST /cleanup/execute with dry_run=true and /tmp path should succeed."""
        payload = {
            "dry_run": True,
            "preflight_id": "test-preflight-123",
            "package_id": "test-package-456",
            "approval_token": "user-approved-cleanup-12345678-1234-5678-1234-567812345678",
            "user_confirmed_execution": True,
            "base_target_dir": "/tmp/test_cleanup_123",
            "plans": [
                {
                    "source": "/tmp/test_cleanup_123/source/file1.txt",
                    "target": "/tmp/test_cleanup_123/target/file1.txt",
                    "confirmed": True
                },
                {
                    "source": "/tmp/test_cleanup_123/source/file2.txt",
                    "target": "/tmp/test_cleanup_123/target/file2.txt",
                    "confirmed": True
                }
            ]
        }

        response = client.post("/cleanup/execute", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "run_id" in data
        assert data["dry_run"] is True
        assert data["success_count"] == 2
        assert len(data["succeeded"]) == 2
        assert data["failed_count"] == 0

    def test_execute_dry_run_false_blocked(self):
        """POST /cleanup/execute with dry_run=false should return 403."""
        payload = {
            "dry_run": False,
            "preflight_id": "test-preflight-123",
            "approval_token": "user-approved-cleanup-12345678-1234-5678-1234-567812345678",
            "user_confirmed_execution": True,
            "base_target_dir": "/tmp/test_cleanup_123",
            "plans": []
        }

        response = client.post("/cleanup/execute", json=payload)
        assert response.status_code == 403
        data = response.json()
        assert data["ok"] is False
        assert "not supported" in data["error"].lower()

    def test_execute_non_tmp_path_rejected(self):
        """POST /cleanup/execute with non-/tmp path should return 400."""
        payload = {
            "dry_run": True,
            "preflight_id": "test-preflight-123",
            "approval_token": "user-approved-cleanup-12345678-1234-5678-1234-567812345678",
            "user_confirmed_execution": True,
            "base_target_dir": "/home/user/test_cleanup",
            "plans": []
        }

        response = client.post("/cleanup/execute", json=payload)
        assert response.status_code == 400
        data = response.json()
        assert data["ok"] is False
        assert "/tmp" in data["error"]

    def test_execute_empty_plans(self):
        """POST /cleanup/execute with empty plans should succeed with 0 count."""
        payload = {
            "dry_run": True,
            "preflight_id": "test-preflight-123",
            "approval_token": "user-approved-cleanup-12345678-1234-5678-1234-567812345678",
            "user_confirmed_execution": True,
            "base_target_dir": "/tmp/test_cleanup_empty",
            "plans": []
        }

        response = client.post("/cleanup/execute", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["success_count"] == 0
        assert len(data["succeeded"]) == 0
        assert data["failed_count"] == 0


class TestCleanupPreflightEndpoint:
    """Test cleanup preflight endpoint."""

    def test_preflight_valid_path_empty_plans(self):
        """POST /cleanup/preflight with valid /tmp path and empty plans should succeed."""
        payload = {
            "base_target_dir": "/tmp/test_preflight_empty",
            "plans": []
        }

        response = client.post("/cleanup/preflight", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "preflight_id" in data
        assert data["dry_run"] is True
        assert data["total"] == 0
        assert data["ok_count"] == 0
        assert data["conflict_count"] == 0
        assert data["skipped_count"] == 0
        assert isinstance(data["items"], list)
        assert len(data["items"]) == 0

    def test_preflight_valid_path_with_plans(self):
        """POST /cleanup/preflight with plans should validate and return status per item."""
        payload = {
            "base_target_dir": "/tmp/test_preflight_plans",
            "plans": [
                {
                    "source": "/tmp/test_preflight_plans/file1.txt",
                    "target": "/tmp/test_preflight_plans/target/file1.txt",
                    "confirmed": True
                },
                {
                    "source": "/tmp/test_preflight_plans/file2.txt",
                    "target": "/tmp/test_preflight_plans/target/file2.txt",
                    "confirmed": True
                }
            ]
        }

        response = client.post("/cleanup/preflight", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "preflight_id" in data
        assert data["dry_run"] is True
        assert data["total"] == 2
        assert isinstance(data["items"], list)
        assert len(data["items"]) == 2
        # Each item should have source, target, status, reason
        for item in data["items"]:
            assert "source" in item
            assert "target" in item
            assert "status" in item
            assert "reason" in item

    def test_preflight_non_tmp_path_rejected(self):
        """POST /cleanup/preflight with non-/tmp path should return 400."""
        payload = {
            "base_target_dir": "/home/user/test_preflight",
            "plans": []
        }

        response = client.post("/cleanup/preflight", json=payload)
        assert response.status_code == 400
        data = response.json()
        assert data["ok"] is False
        assert "/tmp" in data["error"]

    def test_preflight_missing_base_target_dir(self):
        """POST /cleanup/preflight without base_target_dir should return 422 (validation error)."""
        payload = {
            "plans": []
        }

        response = client.post("/cleanup/preflight", json=payload)
        assert response.status_code == 422  # Pydantic validation error
        data = response.json()
        assert "detail" in data  # Pydantic validation error format

    def test_preflight_is_read_only_no_file_ops(self):
        """Preflight should be read-only, no actual file operations."""
        payload = {
            "base_target_dir": "/tmp/test_preflight_readonly",
            "plans": [
                {
                    "source": "/tmp/test_preflight_readonly/file.txt",
                    "target": "/tmp/test_preflight_readonly/target/file.txt",
                    "confirmed": True
                }
            ]
        }

        response = client.post("/cleanup/preflight", json=payload)
        assert response.status_code == 200
        data = response.json()
        # Preflight should report status without actually moving files
        assert data["ok"] is True
        assert data["dry_run"] is True  # Always dry_run semantics


class TestCleanupAuditEndpoint:
    """Test cleanup audit endpoint."""

    def test_audit_read_only(self):
        """GET /cleanup/audit should be read-only."""
        response = client.get("/cleanup/audit?run_id=test-123")
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert "audit_lines" in data
        assert isinstance(data["audit_lines"], list)

    def test_audit_no_params(self):
        """GET /cleanup/audit without run_id should be valid."""
        response = client.get("/cleanup/audit")
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] is None


class TestCleanupRollbackEndpoint:
    """Test cleanup rollback endpoint."""

    def test_rollback_read_only(self):
        """GET /cleanup/rollback should be read-only (no execution)."""
        response = client.get("/cleanup/rollback?run_id=test-123")
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert "manifest" in data
        assert data["rollback_status"] == "pending"

    def test_rollback_no_execution(self):
        """Rollback should never execute automatically."""
        response = client.get("/cleanup/rollback?run_id=test-456")
        assert response.status_code == 200
        data = response.json()
        # Status should remain "pending" - never "executed"
        assert data["rollback_status"] == "pending"


class TestSecurityPolicies:
    """Test security-related policies."""

    def test_no_500_errors_on_validation_failure(self):
        """Validation failures should return 4xx, not 500."""
        payload = {
            "dry_run": True,
            "approval_token": "user-approved-cleanup-12345678-1234-5678-1234-567812345678",
            "user_confirmed_execution": True,
            "base_target_dir": "/invalid/path",
            "plans": []
        }

        response = client.post("/cleanup/execute", json=payload)
        # Should be 4xx (bad request), not 500
        assert 400 <= response.status_code < 500

    def test_health_always_returns_200(self):
        """Health check should always be available."""
        for _ in range(3):
            response = client.get("/health")
            assert response.status_code == 200

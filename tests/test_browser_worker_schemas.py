"""Tests for Browser Worker schemas."""

from ai_orchestrator.browser_tool.worker.schemas import WorkerBrowserRequest, WorkerBrowserResponse


class TestWorkerBrowserRequest:
    """Test WorkerBrowserRequest schema."""

    def test_create_request_minimal(self):
        """Test creating minimal request."""
        req = WorkerBrowserRequest(
            action="browser.inspect",
            url="https://example.com",
            task_id="task-001",
        )
        assert req.action == "browser.inspect"
        assert req.url == "https://example.com"
        assert req.task_id == "task-001"
        assert req.dry_run is False
        assert req.payload is None

    def test_create_request_full(self):
        """Test creating full request with all fields."""
        req = WorkerBrowserRequest(
            action="browser.inspect",
            url="https://example.com",
            task_id="task-001",
            dry_run=True,
            payload={"selector": "button"},
        )
        assert req.dry_run is True
        assert req.payload == {"selector": "button"}

    def test_request_to_dict(self):
        """Test converting request to dict."""
        req = WorkerBrowserRequest(
            action="browser.inspect",
            url="https://example.com",
            task_id="task-001",
            dry_run=True,
        )
        d = req.to_dict()
        assert d["action"] == "browser.inspect"
        assert d["url"] == "https://example.com"
        assert d["task_id"] == "task-001"
        assert d["dry_run"] is True


class TestWorkerBrowserResponse:
    """Test WorkerBrowserResponse schema."""

    def test_dry_run_success_response(self):
        """Test creating dry-run success response."""
        resp = WorkerBrowserResponse.dry_run_success(
            action="browser.inspect",
            task_id="task-001",
            url="https://example.com",
        )
        assert resp.success is True
        assert resp.browser_started is False
        assert resp.backend == "mock_playwright_worker"
        assert resp.title == "DRY_RUN_BROWSER_INSPECT"
        assert resp.url == "https://example.com"
        assert resp.status == "ok"
        assert resp.error_code is None

    def test_actual_execution_disabled_response(self):
        """Test creating actual execution disabled response."""
        resp = WorkerBrowserResponse.actual_execution_disabled(
            action="browser.inspect",
            task_id="task-001",
        )
        assert resp.success is False
        assert resp.browser_started is False
        assert resp.backend == "mock_playwright_worker"
        assert resp.error_code == "ACTUAL_BROWSER_EXECUTION_NOT_ENABLED"
        assert resp.error_message is not None

    def test_unknown_action_response(self):
        """Test creating unknown action response."""
        resp = WorkerBrowserResponse.unknown_action(
            action="browser.unknown",
            task_id="task-001",
        )
        assert resp.success is False
        assert resp.browser_started is False
        assert resp.error_code == "UNKNOWN_BROWSER_ACTION"
        assert "browser.unknown" in resp.error_message

    def test_response_to_dict(self):
        """Test converting response to dict."""
        resp = WorkerBrowserResponse.dry_run_success(
            action="browser.inspect",
            task_id="task-001",
            url="https://example.com",
        )
        d = resp.to_dict()
        assert d["success"] is True
        assert d["action"] == "browser.inspect"
        assert d["backend"] == "mock_playwright_worker"

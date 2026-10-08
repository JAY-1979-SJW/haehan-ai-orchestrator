"""Tests for Browser Worker mock backend."""

from ai_orchestrator.browser_tool.worker.backends.mock_playwright_backend import MockPlaywrightBackend
from ai_orchestrator.browser_tool.worker.schemas import WorkerBrowserRequest


class TestMockPlaywrightBackend:
    """Test MockPlaywrightBackend."""

    def test_handle_browser_inspect_dry_run(self):
        """Test handling browser.inspect in dry_run mode."""
        request = WorkerBrowserRequest(
            action="browser.inspect",
            url="https://example.com",
            task_id="task-001",
            dry_run=True,
        )
        response = MockPlaywrightBackend.handle_browser_inspect_dry_run(request)

        assert response.success is True
        assert response.browser_started is False
        assert response.backend == "mock_playwright_worker"
        assert response.title == "DRY_RUN_BROWSER_INSPECT"
        assert response.url == "https://example.com"
        assert response.status == "ok"

    def test_handle_browser_inspect_unknown_action(self):
        """Test handling unknown action in browser_inspect handler."""
        request = WorkerBrowserRequest(
            action="browser.unknown",
            url="https://example.com",
            task_id="task-001",
            dry_run=True,
        )
        response = MockPlaywrightBackend.handle_browser_inspect_dry_run(request)

        assert response.success is False
        assert response.error_code == "UNKNOWN_BROWSER_ACTION"

    def test_handle_browser_action_dry_run_inspect(self):
        """Test handling browser action with dry_run=True for inspect."""
        request = WorkerBrowserRequest(
            action="browser.inspect",
            url="https://example.com",
            task_id="task-001",
            dry_run=True,
        )
        response = MockPlaywrightBackend.handle_browser_action(request)

        assert response.success is True
        assert response.browser_started is False
        assert response.title == "DRY_RUN_BROWSER_INSPECT"

    def test_handle_browser_action_actual_execution_disabled(self):
        """Test handling browser action with dry_run=False (actual execution)."""
        request = WorkerBrowserRequest(
            action="browser.inspect",
            url="https://example.com",
            task_id="task-001",
            dry_run=False,
        )
        response = MockPlaywrightBackend.handle_browser_action(request)

        assert response.success is False
        assert response.browser_started is False
        assert response.error_code == "ACTUAL_BROWSER_EXECUTION_NOT_ENABLED"

    def test_handle_browser_action_unknown_action(self):
        """Test handling unknown action."""
        request = WorkerBrowserRequest(
            action="browser.unknown",
            url="https://example.com",
            task_id="task-001",
            dry_run=True,
        )
        response = MockPlaywrightBackend.handle_browser_action(request)

        assert response.success is False
        assert response.error_code == "UNKNOWN_BROWSER_ACTION"

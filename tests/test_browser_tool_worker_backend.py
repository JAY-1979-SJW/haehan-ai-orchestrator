"""Tests for Browser Tool Worker Backend."""
import pytest
from ai_orchestrator.browser_tool.schemas import BrowserTask
from ai_orchestrator.browser_tool.backends.worker_backend import BrowserWorkerBackend


class TestBrowserWorkerBackend:
    """Test BrowserWorkerBackend."""

    def test_execute_browser_inspect_dry_run(self):
        """Test executing browser.inspect in dry_run mode."""
        backend = BrowserWorkerBackend()
        task = BrowserTask(action="inspect")
        result = backend.execute(
            task=task,
            url="https://example.com",
            task_id="task-001",
            dry_run=True,
        )

        assert result.success is True
        assert result.data["browser_started"] is False
        assert result.data["title"] == "DRY_RUN_BROWSER_INSPECT"
        assert result.data["url"] == "https://example.com"
        assert result.action == "inspect"

    def test_execute_browser_inspect_actual_execution_disabled(self):
        """Test executing browser.inspect with actual execution (should fail)."""
        backend = BrowserWorkerBackend()
        task = BrowserTask(action="inspect")
        result = backend.execute(
            task=task,
            url="https://example.com",
            task_id="task-001",
            dry_run=False,
        )

        assert result.success is False
        assert result.data["browser_started"] is False
        assert result.error_code == "ACTUAL_BROWSER_EXECUTION_NOT_ENABLED"

    def test_execute_unknown_action(self):
        """Test executing unknown action."""
        backend = BrowserWorkerBackend()
        task = BrowserTask(action="unknown")
        result = backend.execute(
            task=task,
            url="https://example.com",
            task_id="task-001",
            dry_run=True,
        )

        assert result.success is False
        assert result.error_code == "UNKNOWN_BROWSER_ACTION"

    def test_get_capabilities(self):
        """Test getting backend capabilities."""
        backend = BrowserWorkerBackend()
        caps = backend.get_capabilities()

        assert caps["backend_type"] == "browser_worker"
        assert "BROWSER-WORKER-1" in caps["deployment_stage"]
        assert "browser.inspect" in caps["supported_actions_dry_run"]
        assert len(caps["supported_actions_actual"]) == 0

    def test_convert_to_browser_result(self):
        """Test converting worker response to browser result."""
        from browser_worker.schemas import WorkerBrowserResponse
        from ai_orchestrator.browser_tool.schemas import BrowserTask

        worker_response = WorkerBrowserResponse.dry_run_success(
            action="browser.inspect",
            task_id="task-001",
            url="https://example.com",
        )
        original_task = BrowserTask(action="inspect")

        result = BrowserWorkerBackend._convert_to_browser_result(
            worker_response,
            original_task,
        )

        assert result.action == "inspect"
        assert result.success is True
        assert result.data["browser_started"] is False
        assert result.data["title"] == "DRY_RUN_BROWSER_INSPECT"
        assert result.data["backend"] == "mock_playwright_worker"

"""Browser Tool Worker Backend — interface between Router and Browser Worker.

This module serves as a client/adapter for communicating with the Browser Worker.
In the MVP stage (BROWSER-WORKER-1), it uses the worker service directly without
network calls. In future stages (BROWSER-WORKER-3+), it will make HTTP requests
to a separate browser-worker service.
"""
from typing import Optional, Any

from ai_orchestrator.browser_tool.schemas import BrowserResult, BrowserTask
from browser_worker.schemas import WorkerBrowserRequest, WorkerBrowserResponse
from browser_worker.service import handle_browser_request


class BrowserWorkerBackend:
    """Backend that interfaces with Browser Worker."""

    def __init__(self):
        """Initialize worker backend."""
        self.worker_url: Optional[str] = None  # Will be set when worker is deployed
        self.use_local_service = True  # MVP: use local service, no network

    def execute(
        self,
        task: BrowserTask,
        url: str,
        task_id: str,
        dry_run: bool = False,
    ) -> BrowserResult:
        """Execute browser task via Browser Worker.

        Args:
            task: Browser task from Tool Router
            url: URL to navigate/inspect
            task_id: Unique task identifier
            dry_run: Whether to run in dry_run mode

        Returns:
            BrowserResult compatible with existing API
        """
        # Build worker request
        worker_request = WorkerBrowserRequest(
            action=f"browser.{task.action}",
            url=url,
            task_id=task_id,
            dry_run=dry_run,
            payload=task.params,
        )

        # In MVP, call service directly (no network)
        if self.use_local_service:
            worker_response = handle_browser_request(worker_request)
        else:
            # Future: make HTTP request to worker service
            worker_response = self._call_worker_http(worker_request)

        # Convert worker response to BrowserResult
        return self._convert_to_browser_result(worker_response, task)

    def _call_worker_http(self, request: WorkerBrowserRequest) -> WorkerBrowserResponse:
        """Call Browser Worker via HTTP (future stage).

        This is a placeholder for BROWSER-WORKER-3+ when actual worker deployment
        is implemented.

        Args:
            request: Worker browser request

        Raises:
            NotImplementedError: This is not yet implemented
        """
        raise NotImplementedError(
            "Worker HTTP client will be implemented in BROWSER-WORKER-3. "
            "For now, use local service via use_local_service=True."
        )

    @staticmethod
    def _convert_to_browser_result(
        worker_response: WorkerBrowserResponse,
        original_task: BrowserTask,
    ) -> BrowserResult:
        """Convert WorkerBrowserResponse to BrowserResult.

        Args:
            worker_response: Response from browser worker
            original_task: Original task from router

        Returns:
            BrowserResult compatible with existing API
        """
        # Extract action name without "browser." prefix
        action_name = original_task.action

        return BrowserResult(
            action=action_name,
            success=worker_response.success,
            data={
                "title": worker_response.title,
                "url": worker_response.url,
                "backend": worker_response.backend,
                "browser_started": worker_response.browser_started,
                **(worker_response.metadata or {}),
            },
            error=worker_response.error_message or "",
            error_code=worker_response.error_code or "",
            backend="worker_playwright",
        )

    def get_capabilities(self) -> dict:
        """Get worker backend capabilities.

        Returns:
            Dictionary describing supported actions and modes
        """
        return {
            "backend_type": "browser_worker",
            "deployment_stage": "BROWSER-WORKER-1",
            "network_mode": "local_service" if self.use_local_service else "http",
            "supported_actions_dry_run": ["browser.inspect"],
            "supported_actions_actual": [],
            "note": "Actual execution disabled in MVP. Enable in BROWSER-WORKER-3+",
        }

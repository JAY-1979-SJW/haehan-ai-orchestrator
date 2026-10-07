"""Browser Tool Worker Backend — interface between Router and Browser Worker.

This module serves as a client/adapter for communicating with the Browser Worker.
In the MVP stage (BROWSER-WORKER-1), it uses the worker service directly without
network calls. In future stages (BROWSER-WORKER-3+), it will make HTTP requests
to a separate browser-worker service.
"""

import json
import os
from collections.abc import Callable

import httpx

from ai_orchestrator.browser_tool.schemas import BrowserResult, BrowserTask
from ai_orchestrator.browser_tool.worker.schemas import WorkerBrowserRequest, WorkerBrowserResponse
from ai_orchestrator.browser_tool.worker.service import handle_browser_request


class BrowserWorkerClient:
    """HTTP client for Browser Worker service.

    Handles communication with the separate browser-worker service via HTTP.
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: int = 30,
        transport_fn: Callable[[str, dict, int], WorkerBrowserResponse] | None = None,
    ):
        """Initialize HTTP client for browser worker.

        Args:
            base_url: Browser worker service URL (default: http://browser-worker:8500)
            timeout: Request timeout in seconds
            transport_fn: Optional custom transport function (for testing)
        """
        self.base_url = base_url or os.getenv(
            "BROWSER_WORKER_URL",
            "http://browser-worker:8500",
        )
        self.timeout = timeout
        self.transport_fn = transport_fn

    def call_inspect(
        self,
        request: WorkerBrowserRequest,
    ) -> WorkerBrowserResponse:
        """Call browser.inspect endpoint on worker service.

        Args:
            request: Worker browser request

        Returns:
            Worker browser response

        Raises:
            WorkerUnavailableError: Worker service not available
            WorkerTimeoutError: Request timeout
            WorkerBadResponseError: Invalid response format
        """
        if self.transport_fn:
            # Test mode: use custom transport
            return self.transport_fn(
                f"{self.base_url}/v1/browser/inspect",
                request.to_dict(),
                self.timeout,
            )

        # Production mode: use httpx
        return self._http_post_inspect(request)

    def _http_post_inspect(
        self,
        request: WorkerBrowserRequest,
    ) -> WorkerBrowserResponse:
        """Make HTTP POST request to worker service.

        Args:
            request: Worker browser request

        Returns:
            Worker browser response
        """
        endpoint = f"{self.base_url}/v1/browser/inspect"

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    endpoint,
                    json=request.to_dict(),
                )

                # Handle HTTP errors
                if response.status_code != 200:
                    return WorkerBrowserResponse.actual_execution_disabled(
                        request.action,
                        request.task_id,
                    )

                # Parse response
                data = response.json()
                return WorkerBrowserResponse(
                    success=data.get("success", False),
                    action=data.get("action", request.action),
                    task_id=data.get("task_id", request.task_id),
                    browser_started=data.get("browser_started", False),
                    backend=data.get("backend", "worker"),
                    title=data.get("title"),
                    url=data.get("url"),
                    status=data.get("status", "ok"),
                    error_code=data.get("error_code"),
                    error_message=data.get("error_message"),
                    metadata=data.get("metadata"),
                )
        except httpx.TimeoutException:
            return self._timeout_response(request)
        except (httpx.ConnectError, httpx.RequestError):
            return self._unavailable_response(request)
        except (json.JSONDecodeError, ValueError):
            return self._bad_response_error(request)

    @staticmethod
    def _timeout_response(request: WorkerBrowserRequest) -> WorkerBrowserResponse:
        """Create timeout error response."""
        return WorkerBrowserResponse(
            success=False,
            action=request.action,
            task_id=request.task_id,
            browser_started=False,
            backend="worker",
            status="error",
            error_code="BROWSER_WORKER_TIMEOUT",
            error_message="Browser worker service request timeout",
        )

    @staticmethod
    def _unavailable_response(request: WorkerBrowserRequest) -> WorkerBrowserResponse:
        """Create unavailable error response."""
        return WorkerBrowserResponse(
            success=False,
            action=request.action,
            task_id=request.task_id,
            browser_started=False,
            backend="worker",
            status="error",
            error_code="BROWSER_WORKER_UNAVAILABLE",
            error_message="Browser worker service unavailable",
        )

    @staticmethod
    def _bad_response_error(request: WorkerBrowserRequest) -> WorkerBrowserResponse:
        """Create bad response error."""
        return WorkerBrowserResponse(
            success=False,
            action=request.action,
            task_id=request.task_id,
            browser_started=False,
            backend="worker",
            status="error",
            error_code="BROWSER_WORKER_BAD_RESPONSE",
            error_message="Browser worker returned invalid response format",
        )


class BrowserWorkerBackend:
    """Backend that interfaces with Browser Worker."""

    def __init__(self, worker_client: BrowserWorkerClient | None = None):
        """Initialize worker backend.

        Args:
            worker_client: Optional custom worker client (for testing)
        """
        self.worker_url: str | None = None  # Deprecated, use worker_client
        # MVP: default to local service, allow HTTP mode via env var BROWSER_WORKER_USE_HTTP
        use_http = os.getenv("BROWSER_WORKER_USE_HTTP", "false").lower() == "true"
        self.use_local_service = not use_http
        self.worker_client = worker_client or BrowserWorkerClient()

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
        """Call Browser Worker via HTTP.

        Args:
            request: Worker browser request

        Returns:
            Worker browser response
        """
        return self.worker_client.call_inspect(request)

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

"""Tests for Browser Tool Worker Backend."""

from ai_orchestrator.browser_tool.schemas import BrowserTask
from ai_orchestrator.browser_tool.worker.schemas import (
    WorkerBrowserRequest,
    WorkerBrowserResponse,
)
from ai_orchestrator.browser_tool.worker_backend import (
    BrowserWorkerBackend,
    BrowserWorkerClient,
)


class MockTransport:
    """Mock transport for testing HTTP client."""

    def __init__(self, response: WorkerBrowserResponse):
        """Initialize with mock response."""
        self.response = response
        self.called = False
        self.last_request = None

    def __call__(self, url: str, request_dict: dict, timeout: int) -> WorkerBrowserResponse:
        """Mock transport function."""
        self.called = True
        self.last_request = (url, request_dict, timeout)
        return self.response


class TestBrowserWorkerClient:
    """Test BrowserWorkerClient HTTP communication."""

    def test_http_client_init_default_url(self):
        """Test client initializes with default URL."""
        client = BrowserWorkerClient()
        assert client.base_url == "http://browser-worker:8500"
        assert client.timeout == 30

    def test_http_client_custom_url(self):
        """Test client initializes with custom URL."""
        client = BrowserWorkerClient(base_url="http://localhost:9000", timeout=60)
        assert client.base_url == "http://localhost:9000"
        assert client.timeout == 60

    def test_http_client_with_mock_transport(self):
        """Test HTTP client with mock transport."""
        mock_response = WorkerBrowserResponse.dry_run_success(
            action="browser.inspect",
            task_id="task-001",
            url="https://example.com",
        )
        mock_transport = MockTransport(mock_response)

        client = BrowserWorkerClient(transport_fn=mock_transport)
        from ai_orchestrator.browser_tool.worker.schemas import WorkerBrowserRequest

        request = WorkerBrowserRequest(
            action="browser.inspect",
            url="https://example.com",
            task_id="task-001",
            dry_run=True,
        )
        response = client.call_inspect(request)

        assert mock_transport.called
        assert response.success is True
        assert response.title == "DRY_RUN_BROWSER_INSPECT"

    def test_http_client_timeout_response(self):
        """Test HTTP client timeout handling."""
        mock_response = WorkerBrowserResponse.actual_execution_disabled(  # noqa: F841
            action="browser.inspect",
            task_id="task-001",
        )
        timeout_response = BrowserWorkerClient._timeout_response(
            WorkerBrowserRequest(
                action="browser.inspect",
                url="https://example.com",
                task_id="task-001",
            )
        )
        assert timeout_response.success is False
        assert timeout_response.error_code == "BROWSER_WORKER_TIMEOUT"

    def test_http_client_unavailable_response(self):
        """Test HTTP client unavailable handling."""
        unavail_response = BrowserWorkerClient._unavailable_response(
            WorkerBrowserRequest(
                action="browser.inspect",
                url="https://example.com",
                task_id="task-001",
            )
        )
        assert unavail_response.success is False
        assert unavail_response.error_code == "BROWSER_WORKER_UNAVAILABLE"

    def test_http_client_bad_response(self):
        """Test HTTP client bad response handling."""
        bad_response = BrowserWorkerClient._bad_response_error(
            WorkerBrowserRequest(
                action="browser.inspect",
                url="https://example.com",
                task_id="task-001",
            )
        )
        assert bad_response.success is False
        assert bad_response.error_code == "BROWSER_WORKER_BAD_RESPONSE"


class TestBrowserWorkerBackend:
    """Test BrowserWorkerBackend."""

    def test_execute_browser_inspect_dry_run_local_service(self):
        """Test executing browser.inspect in dry_run mode (local service mode)."""
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

    def test_execute_browser_inspect_http_client(self):
        """Test executing browser.inspect with HTTP client (mock transport)."""
        mock_response = WorkerBrowserResponse.dry_run_success(
            action="browser.inspect",
            task_id="task-001",
            url="https://example.com",
        )
        mock_transport = MockTransport(mock_response)
        worker_client = BrowserWorkerClient(transport_fn=mock_transport)

        backend = BrowserWorkerBackend(worker_client=worker_client)
        backend.use_local_service = False  # Enable HTTP client

        task = BrowserTask(action="inspect")
        result = backend.execute(
            task=task,
            url="https://example.com",
            task_id="task-001",
            dry_run=True,
        )

        assert result.success is True
        assert mock_transport.called

    def test_execute_browser_inspect_actual_execution_disabled(self):
        """Test executing browser.inspect with actual execution (should fail)."""
        backend = BrowserWorkerBackend()
        task = BrowserTask(action="inspect")
        result = backend.execute(
            task=task,
            url="about:blank",
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
        from ai_orchestrator.browser_tool.schemas import BrowserTask
        from ai_orchestrator.browser_tool.worker.schemas import WorkerBrowserResponse

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

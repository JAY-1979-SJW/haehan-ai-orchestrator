"""Mock Playwright backend for testing and dry-run mode.

This backend does not execute actual browser operations.
It simulates dry-run browser.inspect responses without launching Playwright.
"""
from browser_worker.schemas import WorkerBrowserRequest, WorkerBrowserResponse


class MockPlaywrightBackend:
    """Mock Playwright backend for browser operations."""

    @staticmethod
    def handle_browser_inspect_dry_run(request: WorkerBrowserRequest) -> WorkerBrowserResponse:
        """Handle browser.inspect in dry_run mode.

        Returns:
            DRY_RUN response with simulated title and status.
        """
        if request.action != "browser.inspect":
            return WorkerBrowserResponse.unknown_action(request.action, request.task_id)

        return WorkerBrowserResponse.dry_run_success(
            action=request.action,
            task_id=request.task_id,
            url=request.url,
        )

    @staticmethod
    def handle_browser_action(request: WorkerBrowserRequest) -> WorkerBrowserResponse:
        """Handle any browser action (actual execution disabled).

        Returns:
            Error response indicating actual execution is disabled.
        """
        if not request.dry_run:
            return WorkerBrowserResponse.actual_execution_disabled(
                request.action,
                request.task_id,
            )

        # Handle dry_run cases
        if request.action == "browser.inspect":
            return MockPlaywrightBackend.handle_browser_inspect_dry_run(request)

        return WorkerBrowserResponse.unknown_action(request.action, request.task_id)

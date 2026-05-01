"""Real Playwright backend for actual browser execution.

This backend launches and controls actual browser instances using Playwright.
Execution is gated by:
1. BROWSER_EXECUTION_ENABLED environment variable (must be "true")
2. Action allowlist (only browser.inspect)
3. URL allowlist (only about:blank)
"""
import os
from browser_worker.schemas import WorkerBrowserRequest, WorkerBrowserResponse


class RealPlaywrightBackend:
    """Real Playwright backend for browser operations."""

    ALLOWED_ACTIONS = frozenset({"browser.inspect"})
    ALLOWED_URLS = frozenset({"about:blank"})
    EXECUTION_ENABLED_ENV_VAR = "BROWSER_EXECUTION_ENABLED"

    def __init__(self):
        """Initialize backend and check feature gate."""
        self.execution_enabled = (
            os.environ.get(self.EXECUTION_ENABLED_ENV_VAR, "").lower() == "true"
        )

    def _validate_execution_enabled(self) -> tuple[bool, str]:
        """Check if actual execution is enabled.

        Returns:
            (allowed, error_code)
        """
        if not self.execution_enabled:
            return False, "ACTUAL_BROWSER_EXECUTION_NOT_ENABLED"
        return True, ""

    def _validate_action(self, action: str) -> tuple[bool, str]:
        """Check if action is allowed for actual execution.

        Returns:
            (allowed, error_code)
        """
        if action not in self.ALLOWED_ACTIONS:
            return False, "ACTION_NOT_ALLOWED_ACTUAL_EXECUTION"
        return True, ""

    def _validate_url(self, url: str) -> tuple[bool, str]:
        """Check if URL is allowed for actual execution.

        Returns:
            (allowed, error_code)
        """
        if url not in self.ALLOWED_URLS:
            return False, "URL_NOT_ALLOWED_ACTUAL_EXECUTION"
        return True, ""

    def handle_browser_action(
        self, request: WorkerBrowserRequest
    ) -> WorkerBrowserResponse:
        """Handle browser action with actual Playwright execution.

        Args:
            request: Browser operation request

        Returns:
            Browser operation response
        """
        # 1. Check if execution is enabled
        allowed, error_code = self._validate_execution_enabled()
        if not allowed:
            return WorkerBrowserResponse(
                success=False,
                task_id=request.task_id,
                action=request.action,
                error_code=error_code,
                browser_started=False,
                backend="real_playwright_worker",
                status="error",
            )

        # 2. Check if action is allowed
        allowed, error_code = self._validate_action(request.action)
        if not allowed:
            return WorkerBrowserResponse(
                success=False,
                task_id=request.task_id,
                action=request.action,
                error_code=error_code,
                browser_started=False,
                backend="real_playwright_worker",
                status="error",
            )

        # 3. Check if URL is allowed
        allowed, error_code = self._validate_url(request.url)
        if not allowed:
            return WorkerBrowserResponse(
                success=False,
                task_id=request.task_id,
                action=request.action,
                error_code=error_code,
                browser_started=False,
                backend="real_playwright_worker",
                status="error",
            )

        # 4. Execute browser action with cleanup guarantees
        browser = None
        context = None
        page = None

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context()
                page = context.new_page()

                # Navigate to URL and get page info
                page.goto(request.url)
                title = page.title()
                url = page.url

                return WorkerBrowserResponse(
                    success=True,
                    task_id=request.task_id,
                    action=request.action,
                    title=title,
                    url=url,
                    browser_started=True,
                    backend="real_playwright_worker",
                    status="ok",
                )

        except Exception as e:
            return WorkerBrowserResponse(
                success=False,
                task_id=request.task_id,
                action=request.action,
                error_code="BROWSER_EXECUTION_ERROR",
                error_message=str(e),
                browser_started=bool(browser),
                backend="real_playwright_worker",
                status="error",
            )

        finally:
            # Cleanup: close page, context, browser in reverse order
            if page is not None:
                try:
                    page.close()
                except Exception:
                    pass
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass

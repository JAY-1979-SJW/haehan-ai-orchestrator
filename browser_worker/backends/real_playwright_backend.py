"""Real Playwright backend for actual browser execution.

This backend launches and controls actual browser instances using Playwright.
Execution is gated by:
1. BROWSER_EXECUTION_ENABLED environment variable (must be "true")
2. Action allowlist (only browser.inspect)
3. URL boundary policy (evaluate_server_browser_url_policy) — 제한 사이트 차단
"""
import os
from browser_worker.schemas import WorkerBrowserRequest, WorkerBrowserResponse
from browser_worker.policy import evaluate_server_browser_url_policy


class RealPlaywrightBackend:
    """Real Playwright backend for browser operations."""

    ALLOWED_ACTIONS = frozenset({"browser.inspect", "browser.open_url_controlled"})
    ALLOWED_URLS = frozenset({"about:blank", "https://example.com/"})
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

    def _validate_url(self, url: str, metadata: dict | None = None) -> tuple[bool, str]:
        """Check if URL is allowed for actual execution via boundary policy.

        page.goto 호출 전 실행. 제한 사이트는 BLOCK 반환.
        Returns:
            (allowed, error_code)
        """
        policy = evaluate_server_browser_url_policy(url, metadata)
        if not policy["allowed"]:
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

        # 3. Check if URL is allowed via boundary policy (제한 사이트 차단)
        allowed, error_code = self._validate_url(request.url, request.payload or {})
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
        cleanup_failed = False

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context()
                page = context.new_page()

                # Navigate to URL (isolated context, no existing profile)
                page.goto(request.url)
                opened = True

                # Action-specific response
                if request.action == "browser.open_url_controlled":
                    return WorkerBrowserResponse(
                        success=True,
                        task_id=request.task_id,
                        action=request.action,
                        browser_started=True,
                        backend="real_playwright_worker",
                        status="ok",
                        data={
                            "execution_mode": "isolated_sample_open",
                            "approval_required": True,
                            "target": {
                                "scheme": "https",
                                "host_class": "sample",
                                "url_redacted": True,
                            },
                            "browser": {
                                "isolated_context": True,
                                "used_existing_profile": False,
                                "opened": opened,
                                "closed": False,
                            },
                        },
                    )

                # Default response for browser.inspect
                return WorkerBrowserResponse(
                    success=True,
                    task_id=request.task_id,
                    action=request.action,
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
            try:
                if page is not None:
                    page.close()
                if context is not None:
                    context.close()
                if browser is not None:
                    browser.close()
            except Exception:
                cleanup_failed = True

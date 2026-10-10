"""Tests for Browser Worker Real Playwright Backend."""

import os
from unittest.mock import MagicMock, patch

from ai_orchestrator.browser_tool.worker.backends.real_playwright_backend import RealPlaywrightBackend
from ai_orchestrator.browser_tool.worker.schemas import WorkerBrowserRequest


class TestRealPlaywrightBackendFeatureGate:
    """Test RealPlaywrightBackend feature flag gating."""

    def test_browser_execution_disabled_by_default(self):
        """Test that browser execution is disabled when env var not set."""
        # Ensure env var is not set or is false
        with patch.dict(os.environ, {"BROWSER_EXECUTION_ENABLED": "false"}):
            backend = RealPlaywrightBackend()
            request = WorkerBrowserRequest(
                action="browser.inspect",
                url="about:blank",
                task_id="task-001",
                dry_run=False,
            )
            response = backend.handle_browser_action(request)

            assert response.success is False
            assert response.error_code == "ACTUAL_BROWSER_EXECUTION_NOT_ENABLED"
            assert response.browser_started is False

    def test_browser_execution_with_flag_true(self):
        """Test that browser execution is allowed when BROWSER_EXECUTION_ENABLED=true."""
        # This test verifies the feature flag logic without actually launching
        with patch.dict(os.environ, {"BROWSER_EXECUTION_ENABLED": "true"}):
            # Re-create backend to pick up env var
            backend = RealPlaywrightBackend()
            request = WorkerBrowserRequest(
                action="browser.inspect",
                url="about:blank",
                task_id="task-001",
                dry_run=False,
            )

            # Mock the sync_playwright to avoid actual launch
            with patch("ai_orchestrator.browser_tool.worker.backends.real_playwright_backend.sync_playwright") as mock_playwright:
                mock_browser = MagicMock()
                mock_context = MagicMock()
                mock_page = MagicMock()

                mock_page.title.return_value = "about:blank"
                mock_page.url = "about:blank"

                mock_context.new_page.return_value = mock_page
                mock_browser.new_context.return_value = mock_context

                mock_playwright.return_value.__enter__.return_value.chromium.launch.return_value = mock_browser

                response = backend.handle_browser_action(request)

                # With mocked playwright, should succeed
                assert response.success is True
                assert response.browser_started is True
                assert response.title == "about:blank"
                assert response.url == "about:blank"

    def test_action_not_allowed_actual_execution(self):
        """Test that non-browser.inspect actions are blocked."""
        with patch.dict(os.environ, {"BROWSER_EXECUTION_ENABLED": "true"}):
            backend = RealPlaywrightBackend()
            request = WorkerBrowserRequest(
                action="browser.execute_click",
                url="about:blank",
                task_id="task-001",
                dry_run=False,
            )
            response = backend.handle_browser_action(request)

            assert response.success is False
            assert response.error_code == "ACTION_NOT_ALLOWED_ACTUAL_EXECUTION"
            assert response.browser_started is False

    def test_url_not_allowed_external_site(self):
        """Test that unclassified external URLs are blocked."""
        with patch.dict(os.environ, {"BROWSER_EXECUTION_ENABLED": "true"}):
            backend = RealPlaywrightBackend()
            request = WorkerBrowserRequest(
                action="browser.inspect",
                url="https://external-unclassified.test",
                task_id="task-001",
                dry_run=False,
            )
            response = backend.handle_browser_action(request)

            assert response.success is False
            assert response.error_code == "URL_NOT_ALLOWED_ACTUAL_EXECUTION"
            assert response.browser_started is False

    def test_url_not_allowed_localhost(self):
        """Test that localhost URLs are blocked."""
        with patch.dict(os.environ, {"BROWSER_EXECUTION_ENABLED": "true"}):
            backend = RealPlaywrightBackend()
            request = WorkerBrowserRequest(
                action="browser.inspect",
                url="http://localhost:8000",
                task_id="task-001",
                dry_run=False,
            )
            response = backend.handle_browser_action(request)

            assert response.success is False
            assert response.error_code == "URL_NOT_ALLOWED_ACTUAL_EXECUTION"
            assert response.browser_started is False


class TestRealPlaywrightBackendCleanup:
    """Test RealPlaywrightBackend cleanup guarantees."""

    def test_browser_close_on_success(self):
        """Test that browser is closed on successful execution."""
        with patch.dict(os.environ, {"BROWSER_EXECUTION_ENABLED": "true"}):
            backend = RealPlaywrightBackend()
            request = WorkerBrowserRequest(
                action="browser.inspect",
                url="about:blank",
                task_id="task-001",
                dry_run=False,
            )

            with patch("ai_orchestrator.browser_tool.worker.backends.real_playwright_backend.sync_playwright") as mock_playwright:
                mock_browser = MagicMock()
                mock_context = MagicMock()
                mock_page = MagicMock()

                mock_page.title.return_value = "about:blank"
                mock_page.url = "about:blank"

                mock_context.new_page.return_value = mock_page
                mock_browser.new_context.return_value = mock_context

                mock_playwright.return_value.__enter__.return_value.chromium.launch.return_value = mock_browser

                response = backend.handle_browser_action(request)  # noqa: F841

                # Verify cleanup was called
                mock_page.close.assert_called_once()
                mock_context.close.assert_called_once()
                mock_browser.close.assert_called_once()

    def test_browser_close_on_exception(self):
        """Test that browser is closed even when exception occurs."""
        with patch.dict(os.environ, {"BROWSER_EXECUTION_ENABLED": "true"}):
            backend = RealPlaywrightBackend()
            request = WorkerBrowserRequest(
                action="browser.inspect",
                url="about:blank",
                task_id="task-001",
                dry_run=False,
            )

            with patch("ai_orchestrator.browser_tool.worker.backends.real_playwright_backend.sync_playwright") as mock_playwright:
                mock_browser = MagicMock()
                mock_context = MagicMock()
                mock_page = MagicMock()

                # Make page.title() raise an exception
                mock_page.title.side_effect = RuntimeError("Page load failed")

                mock_context.new_page.return_value = mock_page
                mock_browser.new_context.return_value = mock_context

                mock_playwright.return_value.__enter__.return_value.chromium.launch.return_value = mock_browser

                response = backend.handle_browser_action(request)

                # Should return error but still have called cleanup
                assert response.success is False
                assert response.error_code == "BROWSER_EXECUTION_ERROR"

                # Verify cleanup was still called
                mock_page.close.assert_called()
                mock_context.close.assert_called()
                mock_browser.close.assert_called()


class TestDryRunVsActualExecution:
    """Test that dry_run and actual execution paths are separate."""

    def test_dry_run_uses_mock_backend(self):
        """Test that dry_run=True uses MockPlaywrightBackend."""
        # This should use mock backend, not real
        request = WorkerBrowserRequest(
            action="browser.inspect",
            url="https://example.com",
            task_id="task-001",
            dry_run=True,
        )

        from ai_orchestrator.browser_tool.worker.service import handle_browser_request

        response = handle_browser_request(request)

        # Should succeed with mock response
        assert response.success is True
        assert response.browser_started is False
        assert response.title == "DRY_RUN_BROWSER_INSPECT"

    def test_dry_run_ignores_external_url(self):
        """Test that dry_run=True allows any URL (mock backend)."""
        request = WorkerBrowserRequest(
            action="browser.inspect",
            url="https://google.com",
            task_id="task-001",
            dry_run=True,
        )

        from ai_orchestrator.browser_tool.worker.service import handle_browser_request

        response = handle_browser_request(request)

        # Should succeed with mock response (dry_run ignores URL restrictions)
        assert response.success is True
        assert response.browser_started is False

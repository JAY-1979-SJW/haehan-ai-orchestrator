"""BROWSER-4C: Local browser task handler integration tests.

Tests WebSocket/local task handling with approval verification,
action dispatch, and result serialization.
"""

import asyncio
import tempfile
from pathlib import Path

import pytest

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

MOCK_HTML_FOR_TASK = """<!DOCTYPE html>
<html>
<head><title>Task Test Page</title></head>
<body>
    <span id="counter">0</span>
    <button id="safe-btn">Click</button>
    <button id="delete-btn" onclick="window.deleted=true;">Delete</button>
    <input type="text" id="search-input" />
    <script>
        window.deleted = false;
        document.getElementById('safe-btn').addEventListener('click', function() {
            let c = document.getElementById('counter');
            c.innerText = String(parseInt(c.innerText) + 1);
        });
    </script>
</body>
</html>"""


class TestBrowserTaskPayload:
    """Test task payload creation and conversion."""

    def test_payload_creation(self):
        from core.agent_runtime.browser.browser_task_handler import BrowserTaskPayload

        payload = BrowserTaskPayload(
            task_id="task-001",
            action_type="browser.execute_click",
            selector="#safe-btn",
            approval_id="approval-001",
            approval_token="token",
        )

        assert payload.task_id == "task-001"
        assert payload.action_type == "browser.execute_click"
        assert payload.selector == "#safe-btn"

    def test_payload_to_server_action(self):
        from core.agent_runtime.browser.browser_task_handler import BrowserTaskPayload

        payload = BrowserTaskPayload(
            task_id="task-001",
            action_type="browser.execute_click",
            selector="#safe-btn",
            approval_id="approval-001",
            approval_token="token",
        )

        server_action = payload.to_server_action()
        assert server_action.task_id == "task-001"
        assert server_action.action_type == "browser.execute_click"
        assert server_action.selector == "#safe-btn"


class TestBrowserTaskResult:
    """Test task result creation and serialization."""

    def test_result_creation(self):
        from core.agent_runtime.browser.browser_task_handler import BrowserTaskResult

        result = BrowserTaskResult(
            task_id="task-001",
            status="executed",
            action="browser_execute_click",
            selector="#safe-btn",
            executed=True,
        )

        assert result.task_id == "task-001"
        assert result.status == "executed"
        assert result.executed is True

    def test_result_redaction(self):
        from core.agent_runtime.browser.browser_task_handler import BrowserTaskResult

        result = BrowserTaskResult(
            task_id="task-001",
            status="executed",
            action="browser_execute_type",
            selector="#search",
            executed=True,
            text_length=10,
        )

        result_str = str(result)
        assert "[REDACTED]" in result_str
        assert "approval_token" not in result_str


@pytest.mark.skipif(not PLAYWRIGHT_AVAILABLE, reason="Playwright not installed")
class TestBrowserTaskHandlerExecution:
    """Test browser task handler with actual execution."""

    def test_valid_approval_click_task_executes(self):
        from core.agent_runtime.browser.approval.browser_approval_verifier import (
            BrowserApprovalStore,
            BrowserApprovalVerifier,
        )
        from core.agent_runtime.browser.browser_controller import BrowserController
        from core.agent_runtime.browser.browser_task_handler import (
            BrowserTaskHandler,
            BrowserTaskPayload,
        )
        from core.agent_runtime.browser.server_action_adapter import ServerActionAdapter

        async def run_test():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(MOCK_HTML_FOR_TASK)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page

                    store = BrowserApprovalStore()
                    store.create_approval(
                        approval_id="approval-001",
                        action_type="browser.execute_click",
                        selector="#safe-btn",
                        approval_token="token",
                    )

                    verifier = BrowserApprovalVerifier(store)
                    adapter = ServerActionAdapter(controller, verifier)
                    handler = BrowserTaskHandler(adapter, verifier)

                    payload = BrowserTaskPayload(
                        task_id="task-001",
                        action_type="browser.execute_click",
                        selector="#safe-btn",
                        approval_id="approval-001",
                        approval_token="token",
                    )

                    result = await handler.handle_task(payload)
                    assert result.executed is True
                    assert result.status == "executed"
                    counter = await page.text_content("#counter")
                    assert counter == "1"

                await browser.close()

        asyncio.run(run_test())

    def test_valid_approval_type_task_executes(self):
        from core.agent_runtime.browser.approval.browser_approval_verifier import (
            BrowserApprovalStore,
            BrowserApprovalVerifier,
        )
        from core.agent_runtime.browser.browser_controller import BrowserController
        from core.agent_runtime.browser.browser_task_handler import (
            BrowserTaskHandler,
            BrowserTaskPayload,
        )
        from core.agent_runtime.browser.server_action_adapter import ServerActionAdapter

        async def run_test():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(MOCK_HTML_FOR_TASK)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page

                    store = BrowserApprovalStore()
                    store.create_approval(
                        approval_id="approval-002",
                        action_type="browser.execute_type",
                        selector="#search-input",
                        approval_token="token",
                    )

                    verifier = BrowserApprovalVerifier(store)
                    adapter = ServerActionAdapter(controller, verifier)
                    handler = BrowserTaskHandler(adapter, verifier)

                    payload = BrowserTaskPayload(
                        task_id="task-002",
                        action_type="browser.execute_type",
                        selector="#search-input",
                        value="test-value",
                        approval_id="approval-002",
                        approval_token="token",
                    )

                    result = await handler.handle_task(payload)
                    assert result.executed is True
                    assert result.status == "executed"
                    value = await page.input_value("#search-input")
                    assert value == "test-value"

                await browser.close()

        asyncio.run(run_test())

    def test_execute_type_verifier_direct(self):
        """Direct test for execute_type with verifier (BROWSER-4B coverage)."""
        from core.agent_runtime.browser.approval.browser_approval_verifier import (
            BrowserApprovalStore,
            BrowserApprovalVerifier,
        )
        from core.agent_runtime.browser.browser_action_contract import ServerApprovalAction
        from core.agent_runtime.browser.browser_controller import BrowserController
        from core.agent_runtime.browser.server_action_adapter import ServerActionAdapter

        async def run_test():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(MOCK_HTML_FOR_TASK)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page

                    store = BrowserApprovalStore()
                    store.create_approval(
                        approval_id="approval-type",
                        action_type="browser.execute_type",
                        selector="#search-input",
                        approval_token="verifier-token",
                    )

                    verifier = BrowserApprovalVerifier(store)
                    adapter = ServerActionAdapter(controller, verifier)

                    action = ServerApprovalAction(
                        task_id="task-type",
                        action_type="browser.execute_type",
                        selector="#search-input",
                        value="verified-text",
                        approval_id="approval-type",
                        approval_token="verifier-token",
                    )

                    result = await adapter.execute_action(action)
                    assert result.executed is True
                    value = await page.input_value("#search-input")
                    assert value == "verified-text"

                await browser.close()

        asyncio.run(run_test())

    def test_task_without_approval_id_blocked(self):
        from core.agent_runtime.browser.approval.browser_approval_verifier import (
            BrowserApprovalStore,
            BrowserApprovalVerifier,
        )
        from core.agent_runtime.browser.browser_controller import BrowserController
        from core.agent_runtime.browser.browser_task_handler import (
            BrowserTaskHandler,
            BrowserTaskPayload,
        )
        from core.agent_runtime.browser.server_action_adapter import ServerActionAdapter

        async def run_test():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(MOCK_HTML_FOR_TASK)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page

                    store = BrowserApprovalStore()
                    verifier = BrowserApprovalVerifier(store)
                    adapter = ServerActionAdapter(controller, verifier)
                    handler = BrowserTaskHandler(adapter, verifier)

                    payload = BrowserTaskPayload(
                        task_id="task-003",
                        action_type="browser.execute_click",
                        selector="#safe-btn",
                        approval_id=None,  # Missing
                        approval_token="token",
                    )

                    result = await handler.handle_task(payload)
                    assert result.executed is False
                    assert result.status == "blocked"
                    assert "missing_approval_id" in result.error_code

                await browser.close()

        asyncio.run(run_test())

    def test_task_with_wrong_token_blocked(self):
        from core.agent_runtime.browser.approval.browser_approval_verifier import (
            BrowserApprovalStore,
            BrowserApprovalVerifier,
        )
        from core.agent_runtime.browser.browser_controller import BrowserController
        from core.agent_runtime.browser.browser_task_handler import (
            BrowserTaskHandler,
            BrowserTaskPayload,
        )
        from core.agent_runtime.browser.server_action_adapter import ServerActionAdapter

        async def run_test():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(MOCK_HTML_FOR_TASK)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page

                    store = BrowserApprovalStore()
                    store.create_approval(
                        approval_id="approval-004",
                        action_type="browser.execute_click",
                        selector="#safe-btn",
                        approval_token="correct-token",
                    )

                    verifier = BrowserApprovalVerifier(store)
                    adapter = ServerActionAdapter(controller, verifier)
                    handler = BrowserTaskHandler(adapter, verifier)

                    payload = BrowserTaskPayload(
                        task_id="task-004",
                        action_type="browser.execute_click",
                        selector="#safe-btn",
                        approval_id="approval-004",
                        approval_token="wrong-token",
                    )

                    result = await handler.handle_task(payload)
                    assert result.executed is False
                    assert result.status == "blocked"
                    assert result.error_code == "invalid_token"

                await browser.close()

        asyncio.run(run_test())

    def test_used_approval_reuse_blocked_in_task(self):
        from core.agent_runtime.browser.approval.browser_approval_verifier import (
            BrowserApprovalStore,
            BrowserApprovalVerifier,
        )
        from core.agent_runtime.browser.browser_controller import BrowserController
        from core.agent_runtime.browser.browser_task_handler import (
            BrowserTaskHandler,
            BrowserTaskPayload,
        )
        from core.agent_runtime.browser.server_action_adapter import ServerActionAdapter

        async def run_test():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(MOCK_HTML_FOR_TASK)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page

                    store = BrowserApprovalStore()
                    store.create_approval(
                        approval_id="approval-005",
                        action_type="browser.execute_click",
                        selector="#safe-btn",
                        approval_token="token",
                    )

                    verifier = BrowserApprovalVerifier(store)
                    adapter = ServerActionAdapter(controller, verifier)
                    handler = BrowserTaskHandler(adapter, verifier)

                    payload = BrowserTaskPayload(
                        task_id="task-005",
                        action_type="browser.execute_click",
                        selector="#safe-btn",
                        approval_id="approval-005",
                        approval_token="token",
                    )

                    # First execution
                    result1 = await handler.handle_task(payload)
                    assert result1.executed is True

                    # Reuse blocked
                    result2 = await handler.handle_task(payload)
                    assert result2.executed is False
                    assert result2.error_code == "approval_used"

                await browser.close()

        asyncio.run(run_test())

    def test_risky_delete_task_blocked(self):
        from core.agent_runtime.browser.approval.browser_approval_verifier import (
            BrowserApprovalStore,
            BrowserApprovalVerifier,
        )
        from core.agent_runtime.browser.browser_controller import BrowserController
        from core.agent_runtime.browser.browser_task_handler import (
            BrowserTaskHandler,
            BrowserTaskPayload,
        )
        from core.agent_runtime.browser.server_action_adapter import ServerActionAdapter

        async def run_test():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(MOCK_HTML_FOR_TASK)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page

                    store = BrowserApprovalStore()
                    store.create_approval(
                        approval_id="approval-delete",
                        action_type="browser.execute_click",
                        selector="#delete-btn",
                        approval_token="token",
                        final_approval_required=True,  # Marked critical
                    )

                    verifier = BrowserApprovalVerifier(store)
                    adapter = ServerActionAdapter(controller, verifier)
                    handler = BrowserTaskHandler(adapter, verifier)

                    payload = BrowserTaskPayload(
                        task_id="task-delete",
                        action_type="browser.execute_click",
                        selector="#delete-btn",
                        approval_id="approval-delete",
                        approval_token="token",
                    )

                    result = await handler.handle_task(payload)
                    # Still blocked because final_approval_required
                    assert result.final_approval_required is True
                    assert result.executed is False

                await browser.close()

        asyncio.run(run_test())

    def test_result_data_no_approval_token(self):
        from core.agent_runtime.browser.approval.browser_approval_verifier import (
            BrowserApprovalStore,
            BrowserApprovalVerifier,
        )
        from core.agent_runtime.browser.browser_controller import BrowserController
        from core.agent_runtime.browser.browser_task_handler import (
            BrowserTaskHandler,
            BrowserTaskPayload,
        )
        from core.agent_runtime.browser.server_action_adapter import ServerActionAdapter

        async def run_test():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(MOCK_HTML_FOR_TASK)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page

                    store = BrowserApprovalStore()
                    store.create_approval(
                        approval_id="approval-secret",
                        action_type="browser.execute_click",
                        selector="#safe-btn",
                        approval_token="secret-token-12345",
                    )

                    verifier = BrowserApprovalVerifier(store)
                    adapter = ServerActionAdapter(controller, verifier)
                    handler = BrowserTaskHandler(adapter, verifier)

                    payload = BrowserTaskPayload(
                        task_id="task-secret",
                        action_type="browser.execute_click",
                        selector="#safe-btn",
                        approval_id="approval-secret",
                        approval_token="secret-token-12345",
                    )

                    result = await handler.handle_task(payload)
                    result_str = str(result)
                    assert "secret-token-12345" not in result_str
                    assert "approval_token" not in result_str

                await browser.close()

        asyncio.run(run_test())

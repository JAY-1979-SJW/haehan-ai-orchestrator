"""BROWSER-4A: Server approval action contract and adapter tests.

Tests server approval flow with mock tasks (no real server/WebSocket calls).
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

MOCK_HTML_FOR_CONTRACT = """<!DOCTYPE html>
<html>
<head><title>Contract Test Page</title></head>
<body>
    <span id="counter">0</span>
    <button id="safe-btn">Click Me</button>
    <button id="delete-btn" onclick="window.actionExecuted=true;">Delete</button>
    <input type="text" id="search-input" />
    <input type="password" id="password-input" />
    <script>
        window.actionExecuted = false;
        document.getElementById('safe-btn').addEventListener('click', function() {
            let c = document.getElementById('counter');
            c.innerText = String(parseInt(c.innerText) + 1);
        });
    </script>
</body>
</html>"""


@pytest.mark.skipif(not PLAYWRIGHT_AVAILABLE, reason="Playwright not installed")
class TestServerApprovalActionContract:
    """Test ServerApprovalAction validation and risk assessment."""

    def test_action_validation_success(self):
        from core.agent_runtime.browser.browser_action_contract import ServerApprovalAction

        action = ServerApprovalAction(
            task_id="task-001",
            action_type="browser.execute_click",
            selector="#safe-btn",
            approval_token="test-token",
        )
        is_valid, error = action.validate()
        assert is_valid is True
        assert error is None

    def test_action_validation_missing_task_id(self):
        from core.agent_runtime.browser.browser_action_contract import ServerApprovalAction

        action = ServerApprovalAction(
            task_id="",
            action_type="browser.execute_click",
            selector="#safe-btn",
            approval_token="test-token",
        )
        is_valid, error = action.validate()
        assert is_valid is False
        assert "task_id" in error

    def test_action_validation_unsupported_type(self):
        from core.agent_runtime.browser.browser_action_contract import ServerApprovalAction

        action = ServerApprovalAction(
            task_id="task-001",
            action_type="browser.invalid_action",
            selector="#safe-btn",
            approval_token="test-token",
        )
        is_valid, error = action.validate()
        assert is_valid is False
        assert "not supported" in error

    def test_action_validation_missing_approval_token(self):
        from core.agent_runtime.browser.browser_action_contract import ServerApprovalAction

        action = ServerApprovalAction(
            task_id="task-001",
            action_type="browser.execute_click",
            selector="#safe-btn",
            approval_token=None,  # Missing
        )
        is_valid, error = action.validate()
        assert is_valid is False
        assert "approval_token required" in error

    def test_risk_assessment_safe_click(self):
        from core.agent_runtime.browser.browser_action_contract import assess_action_risk

        risk, needs_final = assess_action_risk(
            "browser.execute_click",
            "#safe-btn",
        )
        assert risk == "low"
        assert needs_final is False

    def test_risk_assessment_critical_delete(self):
        from core.agent_runtime.browser.browser_action_contract import assess_action_risk

        risk, needs_final = assess_action_risk(
            "browser.execute_click",
            "#delete-btn",
        )
        assert risk == "critical"
        assert needs_final is True

    def test_execution_result_redaction(self):
        from core.agent_runtime.browser.browser_action_contract import ExecutionResult

        result = ExecutionResult(
            task_id="task-001",
            action="browser_execute_type",
            selector="#search-input",
            executed=True,
            element_found=True,
            risk_level="low",
            final_approval_required=False,
            result="success",
            text_length=10,
        )
        s = str(result)
        assert "approval_token" not in s
        assert "[REDACTED]" in s

    def test_result_validation_no_secrets(self):
        from core.agent_runtime.browser.browser_action_contract import (
            ExecutionResult,
            validate_execution_result,
        )

        result = ExecutionResult(
            task_id="task-001",
            action="browser_execute_click",
            selector="#safe-btn",
            executed=True,
            element_found=True,
            risk_level="low",
            final_approval_required=False,
            result="success",
        )
        is_safe, error = validate_execution_result(result)
        assert is_safe is True
        assert error is None

    def test_result_validation_rejects_non_redacted_text(self):
        from core.agent_runtime.browser.browser_action_contract import (
            ExecutionResult,
            validate_execution_result,
        )

        result = ExecutionResult(
            task_id="task-001",
            action="browser_execute_type",
            selector="#search-input",
            executed=True,
            element_found=True,
            risk_level="low",
            final_approval_required=False,
            result="success",
            text_preview="actual_secret",  # Should be [REDACTED]
        )
        is_safe, error = validate_execution_result(result)
        assert is_safe is False
        assert "text_preview" in error


@pytest.mark.skipif(not PLAYWRIGHT_AVAILABLE, reason="Playwright not installed")
class TestServerActionAdapterIntegration:
    """Test ServerActionAdapter with mock Playwright page."""

    def test_execute_click_without_approval_token_blocked(self):
        from core.agent_runtime.browser.browser_action_contract import ServerApprovalAction
        from core.agent_runtime.browser.browser_controller import BrowserController
        from core.agent_runtime.browser.server_action_adapter import ServerActionAdapter

        async def run_test():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(MOCK_HTML_FOR_CONTRACT)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page
                    adapter = ServerActionAdapter(controller)

                    action = ServerApprovalAction(
                        task_id="task-001",
                        action_type="browser.execute_click",
                        selector="#safe-btn",
                        approval_token=None,  # No approval
                    )
                    with pytest.raises(Exception) as exc_info:
                        await adapter.execute_action(action)
                    assert "approval_token" in str(exc_info.value)

                await browser.close()

        asyncio.run(run_test())

    def test_execute_click_with_approval_token_succeeds(self):
        from core.agent_runtime.browser.browser_action_contract import ServerApprovalAction
        from core.agent_runtime.browser.browser_controller import BrowserController
        from core.agent_runtime.browser.server_action_adapter import ServerActionAdapter

        async def run_test():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(MOCK_HTML_FOR_CONTRACT)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page
                    adapter = ServerActionAdapter(controller)

                    action = ServerApprovalAction(
                        task_id="task-001",
                        action_type="browser.execute_click",
                        selector="#safe-btn",
                        approval_token="test-token",
                    )
                    result = await adapter.execute_action(action)
                    assert result.executed is True
                    assert result.task_id == "task-001"
                    counter = await page.text_content("#counter")
                    assert counter == "1"

                await browser.close()

        asyncio.run(run_test())

    def test_execute_type_without_approval_token_blocked(self):
        from core.agent_runtime.browser.browser_action_contract import ServerApprovalAction
        from core.agent_runtime.browser.browser_controller import BrowserController
        from core.agent_runtime.browser.server_action_adapter import ServerActionAdapter

        async def run_test():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(MOCK_HTML_FOR_CONTRACT)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page
                    adapter = ServerActionAdapter(controller)

                    action = ServerApprovalAction(
                        task_id="task-002",
                        action_type="browser.execute_type",
                        selector="#search-input",
                        value="test",
                        approval_token=None,  # No approval
                    )
                    with pytest.raises(Exception) as exc_info:
                        await adapter.execute_action(action)
                    assert "approval_token" in str(exc_info.value)

                await browser.close()

        asyncio.run(run_test())

    def test_execute_type_with_approval_token_succeeds(self):
        from core.agent_runtime.browser.browser_action_contract import ServerApprovalAction
        from core.agent_runtime.browser.browser_controller import BrowserController
        from core.agent_runtime.browser.server_action_adapter import ServerActionAdapter

        async def run_test():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(MOCK_HTML_FOR_CONTRACT)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page
                    adapter = ServerActionAdapter(controller)

                    action = ServerApprovalAction(
                        task_id="task-002",
                        action_type="browser.execute_type",
                        selector="#search-input",
                        value="test-value",
                        approval_token="test-token",
                    )
                    result = await adapter.execute_action(action)
                    assert result.executed is True
                    assert result.task_id == "task-002"
                    value = await page.input_value("#search-input")
                    assert value == "test-value"

                await browser.close()

        asyncio.run(run_test())

    def test_risky_action_requires_final_approval_and_not_executed(self):
        from core.agent_runtime.browser.browser_action_contract import ServerApprovalAction
        from core.agent_runtime.browser.browser_controller import BrowserController
        from core.agent_runtime.browser.server_action_adapter import ServerActionAdapter

        async def run_test():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(MOCK_HTML_FOR_CONTRACT)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page
                    adapter = ServerActionAdapter(controller)

                    action = ServerApprovalAction(
                        task_id="task-003",
                        action_type="browser.execute_click",
                        selector="#delete-btn",
                        approval_token="test-token",
                        final_approval_token=None,  # Missing final approval
                    )
                    result = await adapter.execute_action(action)
                    assert result.final_approval_required is True
                    assert result.executed is False
                    assert result.result == "risky_element"

                await browser.close()

        asyncio.run(run_test())

    def test_result_does_not_include_approval_token(self):
        from core.agent_runtime.browser.browser_action_contract import ServerApprovalAction
        from core.agent_runtime.browser.browser_controller import BrowserController
        from core.agent_runtime.browser.server_action_adapter import ServerActionAdapter

        async def run_test():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(MOCK_HTML_FOR_CONTRACT)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page
                    adapter = ServerActionAdapter(controller)

                    action = ServerApprovalAction(
                        task_id="task-004",
                        action_type="browser.execute_click",
                        selector="#safe-btn",
                        approval_token="secret-token-12345",
                    )
                    result = await adapter.execute_action(action)
                    result_str = str(result)
                    assert "secret-token-12345" not in result_str
                    assert "approval_token" not in result_str

                await browser.close()

        asyncio.run(run_test())

    def test_result_does_not_include_typed_text(self):
        from core.agent_runtime.browser.browser_action_contract import ServerApprovalAction
        from core.agent_runtime.browser.browser_controller import BrowserController
        from core.agent_runtime.browser.server_action_adapter import ServerActionAdapter

        async def run_test():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(MOCK_HTML_FOR_CONTRACT)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page
                    adapter = ServerActionAdapter(controller)

                    secret_text = "my-secret-password-xyz"
                    action = ServerApprovalAction(
                        task_id="task-005",
                        action_type="browser.execute_type",
                        selector="#search-input",
                        value=secret_text,
                        approval_token="test-token",
                    )
                    result = await adapter.execute_action(action)
                    result_str = str(result)
                    assert secret_text not in result_str
                    assert "[REDACTED]" in result_str

                await browser.close()

        asyncio.run(run_test())

    def test_unsupported_action_type_rejected(self):
        from core.agent_runtime.browser.browser_action_contract import ServerApprovalAction
        from core.agent_runtime.browser.browser_controller import BrowserController
        from core.agent_runtime.browser.server_action_adapter import ServerActionAdapter

        async def run_test():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(MOCK_HTML_FOR_CONTRACT)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page
                    adapter = ServerActionAdapter(controller)

                    action = ServerApprovalAction(
                        task_id="task-006",
                        action_type="browser.submit",  # Not supported
                        selector="#form",
                        approval_token="test-token",
                    )
                    with pytest.raises(Exception) as exc_info:
                        await adapter.execute_action(action)
                    assert "not supported" in str(exc_info.value).lower()

                await browser.close()

        asyncio.run(run_test())

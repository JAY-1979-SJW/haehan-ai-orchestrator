"""BROWSER-4B: Server-side approval token verification tests.

Tests approval verification, token hashing, and one-time use enforcement.
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

MOCK_HTML_FOR_APPROVAL = """<!DOCTYPE html>
<html>
<head><title>Approval Test Page</title></head>
<body>
    <span id="counter">0</span>
    <button id="safe-btn">Click Me</button>
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


class TestBrowserApprovalVerifier:
    """Test approval verification without Playwright."""

    def test_create_approval(self):
        from core.agent_runtime.browser.approval.browser_approval_verifier import (
            BrowserApprovalStore,
            _hash_token,
        )

        store = BrowserApprovalStore()
        record = store.create_approval(
            approval_id="approval-001",
            action_type="browser.execute_click",
            selector="#safe-btn",
            approval_token="secret-token-abc",
        )

        assert record.approval_id == "approval-001"
        assert record.action_type == "browser.execute_click"
        assert record.selector == "#safe-btn"
        # Raw token not stored
        assert record.token_hash == _hash_token("secret-token-abc")

    def test_hash_token_consistency(self):
        from core.agent_runtime.browser.approval.browser_approval_verifier import _hash_token

        token = "my-secret-token"
        hash1 = _hash_token(token)
        hash2 = _hash_token(token)
        assert hash1 == hash2

    def test_verify_valid_approval(self):
        from core.agent_runtime.browser.approval.browser_approval_verifier import (
            BrowserApprovalStore,
            BrowserApprovalVerifier,
        )

        store = BrowserApprovalStore()
        store.create_approval(
            approval_id="approval-001",
            action_type="browser.execute_click",
            selector="#safe-btn",
            approval_token="secret-token-abc",
        )

        verifier = BrowserApprovalVerifier(store)
        result = verifier.verify(
            approval_id="approval-001",
            approval_token="secret-token-abc",
            action_type="browser.execute_click",
            selector="#safe-btn",
        )

        assert result.valid is True
        assert result.record is not None

    def test_verify_missing_approval_id(self):
        from core.agent_runtime.browser.approval.browser_approval_verifier import (
            BrowserApprovalStore,
            BrowserApprovalVerifier,
        )

        store = BrowserApprovalStore()
        verifier = BrowserApprovalVerifier(store)
        result = verifier.verify(
            approval_id=None,
            approval_token="token",
            action_type="browser.execute_click",
            selector="#safe-btn",
        )

        assert result.valid is False
        assert result.error_code == "missing_approval_id"

    def test_verify_missing_approval_token(self):
        from core.agent_runtime.browser.approval.browser_approval_verifier import (
            BrowserApprovalStore,
            BrowserApprovalVerifier,
        )

        store = BrowserApprovalStore()
        verifier = BrowserApprovalVerifier(store)
        result = verifier.verify(
            approval_id="approval-001",
            approval_token=None,
            action_type="browser.execute_click",
            selector="#safe-btn",
        )

        assert result.valid is False
        assert result.error_code == "missing_approval_token"

    def test_verify_unknown_approval_id(self):
        from core.agent_runtime.browser.approval.browser_approval_verifier import (
            BrowserApprovalStore,
            BrowserApprovalVerifier,
        )

        store = BrowserApprovalStore()
        verifier = BrowserApprovalVerifier(store)
        result = verifier.verify(
            approval_id="unknown-approval",
            approval_token="token",
            action_type="browser.execute_click",
            selector="#safe-btn",
        )

        assert result.valid is False
        assert result.error_code == "approval_not_found"

    def test_verify_wrong_token(self):
        from core.agent_runtime.browser.approval.browser_approval_verifier import (
            BrowserApprovalStore,
            BrowserApprovalVerifier,
        )

        store = BrowserApprovalStore()
        store.create_approval(
            approval_id="approval-001",
            action_type="browser.execute_click",
            selector="#safe-btn",
            approval_token="correct-token",
        )

        verifier = BrowserApprovalVerifier(store)
        result = verifier.verify(
            approval_id="approval-001",
            approval_token="wrong-token",
            action_type="browser.execute_click",
            selector="#safe-btn",
        )

        assert result.valid is False
        assert result.error_code == "invalid_token"

    def test_verify_wrong_action_type(self):
        from core.agent_runtime.browser.approval.browser_approval_verifier import (
            BrowserApprovalStore,
            BrowserApprovalVerifier,
        )

        store = BrowserApprovalStore()
        store.create_approval(
            approval_id="approval-001",
            action_type="browser.execute_click",
            selector="#safe-btn",
            approval_token="token",
        )

        verifier = BrowserApprovalVerifier(store)
        result = verifier.verify(
            approval_id="approval-001",
            approval_token="token",
            action_type="browser.execute_type",  # Wrong
            selector="#safe-btn",
        )

        assert result.valid is False
        assert result.error_code == "action_type_mismatch"

    def test_verify_wrong_selector(self):
        from core.agent_runtime.browser.approval.browser_approval_verifier import (
            BrowserApprovalStore,
            BrowserApprovalVerifier,
        )

        store = BrowserApprovalStore()
        store.create_approval(
            approval_id="approval-001",
            action_type="browser.execute_click",
            selector="#safe-btn",
            approval_token="token",
        )

        verifier = BrowserApprovalVerifier(store)
        result = verifier.verify(
            approval_id="approval-001",
            approval_token="token",
            action_type="browser.execute_click",
            selector="#wrong-btn",  # Wrong
        )

        assert result.valid is False
        assert result.error_code == "selector_mismatch"

    def test_mark_used(self):
        from core.agent_runtime.browser.approval.browser_approval_verifier import BrowserApprovalStore

        store = BrowserApprovalStore()
        store.create_approval(
            approval_id="approval-001",
            action_type="browser.execute_click",
            selector="#safe-btn",
            approval_token="token",
        )

        assert store.mark_used("approval-001") is True
        record = store.get("approval-001")
        assert record.status == "used"

    def test_reuse_blocked_after_use(self):
        from core.agent_runtime.browser.approval.browser_approval_verifier import (
            BrowserApprovalStore,
            BrowserApprovalVerifier,
        )

        store = BrowserApprovalStore()
        store.create_approval(
            approval_id="approval-001",
            action_type="browser.execute_click",
            selector="#safe-btn",
            approval_token="token",
        )

        # First use passes
        verifier = BrowserApprovalVerifier(store)
        result1 = verifier.verify(
            approval_id="approval-001",
            approval_token="token",
            action_type="browser.execute_click",
            selector="#safe-btn",
        )
        assert result1.valid is True

        # Mark as used
        store.mark_used("approval-001")

        # Reuse fails
        result2 = verifier.verify(
            approval_id="approval-001",
            approval_token="token",
            action_type="browser.execute_click",
            selector="#safe-btn",
        )
        assert result2.valid is False
        assert result2.error_code == "approval_used"

    def test_revoke_approval(self):
        from core.agent_runtime.browser.approval.browser_approval_verifier import (
            BrowserApprovalStore,
            BrowserApprovalVerifier,
        )

        store = BrowserApprovalStore()
        store.create_approval(
            approval_id="approval-001",
            action_type="browser.execute_click",
            selector="#safe-btn",
            approval_token="token",
        )

        store.revoke("approval-001")

        verifier = BrowserApprovalVerifier(store)
        result = verifier.verify(
            approval_id="approval-001",
            approval_token="token",
            action_type="browser.execute_click",
            selector="#safe-btn",
        )

        assert result.valid is False
        assert result.error_code == "approval_revoked"

    def test_expired_approval(self):
        from core.agent_runtime.browser.approval.browser_approval_verifier import (
            BrowserApprovalStore,
            BrowserApprovalVerifier,
        )

        store = BrowserApprovalStore()
        store.create_approval(
            approval_id="approval-001",
            action_type="browser.execute_click",
            selector="#safe-btn",
            approval_token="token",
            expires_in_seconds=-1,  # Already expired
        )

        verifier = BrowserApprovalVerifier(store)
        result = verifier.verify(
            approval_id="approval-001",
            approval_token="token",
            action_type="browser.execute_click",
            selector="#safe-btn",
        )

        assert result.valid is False
        assert result.error_code == "approval_expired"


@pytest.mark.skipif(not PLAYWRIGHT_AVAILABLE, reason="Playwright not installed")
class TestServerActionAdapterWithApprovalVerifier:
    """Test ServerActionAdapter with approval verifier."""

    def test_execute_click_with_valid_approval(self):
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
                await page.set_content(MOCK_HTML_FOR_APPROVAL)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page

                    store = BrowserApprovalStore()
                    store.create_approval(
                        approval_id="approval-001",
                        action_type="browser.execute_click",
                        selector="#safe-btn",
                        approval_token="secret-token",
                    )

                    verifier = BrowserApprovalVerifier(store)
                    adapter = ServerActionAdapter(controller, verifier)

                    action = ServerApprovalAction(
                        task_id="task-001",
                        action_type="browser.execute_click",
                        selector="#safe-btn",
                        approval_id="approval-001",
                        approval_token="secret-token",
                    )
                    result = await adapter.execute_action(action)
                    assert result.executed is True
                    counter = await page.text_content("#counter")
                    assert counter == "1"

                await browser.close()

        asyncio.run(run_test())

    def test_execute_click_with_invalid_token_blocked(self):
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
                await page.set_content(MOCK_HTML_FOR_APPROVAL)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page

                    store = BrowserApprovalStore()
                    store.create_approval(
                        approval_id="approval-001",
                        action_type="browser.execute_click",
                        selector="#safe-btn",
                        approval_token="correct-token",
                    )

                    verifier = BrowserApprovalVerifier(store)
                    adapter = ServerActionAdapter(controller, verifier)

                    action = ServerApprovalAction(
                        task_id="task-001",
                        action_type="browser.execute_click",
                        selector="#safe-btn",
                        approval_id="approval-001",
                        approval_token="wrong-token",
                    )
                    result = await adapter.execute_action(action)
                    assert result.executed is False
                    assert result.result == "invalid_token"
                    counter = await page.text_content("#counter")
                    assert counter == "0"  # Not executed

                await browser.close()

        asyncio.run(run_test())

    def test_approval_marked_used_after_execution(self):
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
                await page.set_content(MOCK_HTML_FOR_APPROVAL)
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

                    action = ServerApprovalAction(
                        task_id="task-001",
                        action_type="browser.execute_click",
                        selector="#safe-btn",
                        approval_id="approval-001",
                        approval_token="token",
                    )
                    result = await adapter.execute_action(action)
                    assert result.executed is True

                    # Check approval is marked used
                    record = store.get("approval-001")
                    assert record.status == "used"

                await browser.close()

        asyncio.run(run_test())

    def test_reuse_blocked_after_first_execution(self):
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
                await page.set_content(MOCK_HTML_FOR_APPROVAL)
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

                    action = ServerApprovalAction(
                        task_id="task-001",
                        action_type="browser.execute_click",
                        selector="#safe-btn",
                        approval_id="approval-001",
                        approval_token="token",
                    )

                    # First execution succeeds
                    result1 = await adapter.execute_action(action)
                    assert result1.executed is True
                    counter = await page.text_content("#counter")
                    assert counter == "1"

                    # Second execution blocked
                    result2 = await adapter.execute_action(action)
                    assert result2.executed is False
                    assert result2.result == "approval_used"
                    counter = await page.text_content("#counter")
                    assert counter == "1"  # Not incremented

                await browser.close()

        asyncio.run(run_test())

    def test_adapter_without_verifier_still_works(self):
        from core.agent_runtime.browser.browser_action_contract import ServerApprovalAction
        from core.agent_runtime.browser.browser_controller import BrowserController
        from core.agent_runtime.browser.server_action_adapter import ServerActionAdapter

        async def run_test():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(MOCK_HTML_FOR_APPROVAL)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page
                    adapter = ServerActionAdapter(controller)  # No verifier

                    action = ServerApprovalAction(
                        task_id="task-001",
                        action_type="browser.execute_click",
                        selector="#safe-btn",
                        approval_token="any-token",
                    )
                    result = await adapter.execute_action(action)
                    assert result.executed is True

                await browser.close()

        asyncio.run(run_test())

    def test_approval_token_not_in_result_data(self):
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
                await page.set_content(MOCK_HTML_FOR_APPROVAL)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page

                    store = BrowserApprovalStore()
                    store.create_approval(
                        approval_id="approval-001",
                        action_type="browser.execute_click",
                        selector="#safe-btn",
                        approval_token="secret-approval-token-12345",
                    )

                    verifier = BrowserApprovalVerifier(store)
                    adapter = ServerActionAdapter(controller, verifier)

                    action = ServerApprovalAction(
                        task_id="task-001",
                        action_type="browser.execute_click",
                        selector="#safe-btn",
                        approval_id="approval-001",
                        approval_token="secret-approval-token-12345",
                    )
                    result = await adapter.execute_action(action)
                    result_str = str(result)
                    assert "secret-approval-token-12345" not in result_str
                    assert "approval_token" not in result_str

                await browser.close()

        asyncio.run(run_test())

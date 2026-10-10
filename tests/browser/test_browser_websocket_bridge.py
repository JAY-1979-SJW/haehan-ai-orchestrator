"""Local WebSocket bridge tests (BROWSER-6).

Verifies BrowserLocalWebSocketBridge contract:
- Schema validation runs BEFORE handler dispatch
- All callbacks are safe (no tokens, no raw text, no cookies/sessions)
- Status mapping: validation_failed / approval_invalid / blocked / executed / failed
- task_id always present in callback
- Bridge never connects to real WebSocket
- Bridge dispatches via BrowserTaskHandler (not BrowserController directly)
- Persistent + DB store integration
"""

from __future__ import annotations

import asyncio
import inspect
import time
import unittest
from unittest.mock import MagicMock

from core.agent_runtime.browser.approval.browser_approval_db_store import SQLiteBrowserApprovalStore
from core.agent_runtime.browser.approval.browser_approval_persistent_store import (
    PersistentBrowserApprovalStore,
)
from core.agent_runtime.browser.approval.browser_approval_verifier import (
    BrowserApprovalStore,
    BrowserApprovalVerifier,
)
from core.agent_runtime.browser.bridge.browser_websocket_bridge import (
    BrowserLocalWebSocketBridge,
    MockResultCallbackCollector,
)
from core.agent_runtime.browser.bridge.browser_websocket_schema import RESULT_DATA_FORBIDDEN_KEYS
from core.agent_runtime.browser.browser_action_contract import ExecutionResult
from core.agent_runtime.browser.browser_task_handler import BrowserTaskHandler
from core.agent_runtime.browser.server_action_adapter import ServerActionAdapter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_adapter_returning(
    executed: bool = True,
    element_found: bool = True,
    action: str = "browser.execute_click",
    selector: str = "#btn",
    result_code: str = "success",
) -> MagicMock:
    """Build a mock ServerActionAdapter whose execute_action returns ExecutionResult."""
    adapter = MagicMock(spec=ServerActionAdapter)
    exec_result = ExecutionResult(
        task_id="t1",
        action=action,
        selector=selector,
        executed=executed,
        element_found=element_found,
        risk_level="low",
        final_approval_required=False,
        result=result_code,
        target_url_domain="example.com",
        text_length=0,
    )

    async def _execute(_):
        return exec_result

    adapter.execute_action = _execute
    return adapter


def _make_bridge(store=None, adapter=None, collector=None):
    store = store or BrowserApprovalStore()
    adapter = adapter or _make_adapter_returning()
    verifier = BrowserApprovalVerifier(store)
    handler = BrowserTaskHandler(server_action_adapter=adapter, approval_verifier=verifier)
    collector = collector or MockResultCallbackCollector()
    bridge = BrowserLocalWebSocketBridge(task_handler=handler, callback=collector.append)
    return bridge, store, collector


def _create_appr(
    store,
    *,
    approval_id="appr-1",
    token="tok-1",
    action_type="browser.execute_click",
    selector="#btn",
    expires_in_seconds=None,
):
    return store.create_approval(
        approval_id=approval_id,
        action_type=action_type,
        selector=selector,
        approval_token=token,
        expires_in_seconds=expires_in_seconds,
    )


def _valid_msg(
    *,
    task_id="t1",
    approval_id="appr-1",
    token="tok-1",
    action_type="browser.execute_click",
    selector="#btn",
    value=None,
) -> dict:
    msg = {
        "task_id": task_id,
        "task_type": "browser_action",
        "action_type": action_type,
        "selector": selector,
        "approval_id": approval_id,
        "approval_token": token,
    }
    if value is not None:
        msg["value"] = value
    return msg


# ---------------------------------------------------------------------------
# 1-2: Valid message executes
# ---------------------------------------------------------------------------


class TestValidExecution(unittest.TestCase):
    def test_valid_execute_click_message_executes_and_callbacks_safe_result(self):
        bridge, store, coll = _make_bridge()
        _create_appr(store)
        result = bridge.handle_inbound_message_sync(_valid_msg())
        self.assertEqual(result["status"], "executed")
        self.assertTrue(result["executed"])
        self.assertEqual(result["task_id"], "t1")
        coll.assert_no_secrets()

    def test_valid_execute_type_message_executes_and_callbacks_safe_result(self):
        adapter = _make_adapter_returning(action="browser.execute_type", selector="#input")
        bridge, store, coll = _make_bridge(adapter=adapter)
        _create_appr(store, action_type="browser.execute_type", selector="#input")
        msg = _valid_msg(action_type="browser.execute_type", selector="#input", value="hello")
        result = bridge.handle_inbound_message_sync(msg)
        self.assertEqual(result["status"], "executed")
        # Raw value never propagates
        self.assertNotIn("hello", str(result))
        coll.assert_no_secrets()


# ---------------------------------------------------------------------------
# 3-5: Schema validation failures
# ---------------------------------------------------------------------------


class TestSchemaInvalid(unittest.TestCase):
    def test_invalid_schema_message_rejected_before_handler(self):
        # Use a real handler-but-with-tracking adapter to detect dispatch
        adapter = MagicMock(spec=ServerActionAdapter)
        adapter.execute_action = MagicMock()
        verifier = BrowserApprovalVerifier(BrowserApprovalStore())
        handler = BrowserTaskHandler(server_action_adapter=adapter, approval_verifier=verifier)
        collector = MockResultCallbackCollector()
        bridge = BrowserLocalWebSocketBridge(task_handler=handler, callback=collector.append)

        # Missing task_id
        result = bridge.handle_inbound_message_sync({"task_type": "browser_action"})
        self.assertEqual(result["status"], "validation_failed")
        adapter.execute_action.assert_not_called()
        collector.assert_no_secrets()

    def test_unsupported_action_rejected(self):
        bridge, store, coll = _make_bridge()
        _create_appr(store)
        msg = _valid_msg()
        msg["action_type"] = "browser.evil"
        result = bridge.handle_inbound_message_sync(msg)
        self.assertEqual(result["status"], "validation_failed")
        coll.assert_no_secrets()

    def test_execute_submit_message_rejected(self):
        bridge, store, coll = _make_bridge()
        _create_appr(store)
        msg = _valid_msg()
        msg["action_type"] = "browser.execute_submit"
        result = bridge.handle_inbound_message_sync(msg)
        self.assertEqual(result["status"], "validation_failed")
        coll.assert_no_secrets()


# ---------------------------------------------------------------------------
# 6-10: Approval verification failures
# ---------------------------------------------------------------------------


class TestApprovalRejection(unittest.TestCase):
    def test_missing_approval_rejected(self):
        bridge, store, coll = _make_bridge()
        # No approval created
        msg = _valid_msg(approval_id="appr-missing")
        result = bridge.handle_inbound_message_sync(msg)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("not_found", (result.get("error_code") or "").lower())
        coll.assert_no_secrets()

    def test_wrong_token_rejected(self):
        bridge, store, coll = _make_bridge()
        _create_appr(store, token="real-token")
        msg = _valid_msg(token="wrong-token")
        result = bridge.handle_inbound_message_sync(msg)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["error_code"], "invalid_token")
        coll.assert_no_secrets()

    def test_used_approval_reuse_rejected(self):
        bridge, store, coll = _make_bridge()
        _create_appr(store)
        # First call succeeds (and marks used)
        bridge.handle_inbound_message_sync(_valid_msg())
        coll.clear()
        # Second call must be blocked
        result = bridge.handle_inbound_message_sync(_valid_msg(task_id="t2"))
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["error_code"], "approval_used")
        coll.assert_no_secrets()

    def test_revoked_approval_rejected(self):
        bridge, store, coll = _make_bridge()
        _create_appr(store)
        store.revoke("appr-1")
        result = bridge.handle_inbound_message_sync(_valid_msg())
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["error_code"], "approval_revoked")
        coll.assert_no_secrets()

    def test_expired_approval_rejected(self):
        bridge, store, coll = _make_bridge()
        _create_appr(store, expires_in_seconds=1)
        time.sleep(1.1)
        result = bridge.handle_inbound_message_sync(_valid_msg())
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["error_code"], "approval_expired")
        coll.assert_no_secrets()


# ---------------------------------------------------------------------------
# 11: Risky action — relies on approval store risk_level (the policy gate
# is in handler/adapter; the bridge just propagates the result.status).
# ---------------------------------------------------------------------------


class TestRiskyAction(unittest.TestCase):
    def test_risky_delete_message_blocked_when_handler_blocks(self):
        """If handler returns a non-executed result for a risky action,
        the bridge propagates 'blocked' status without leaking detail."""
        adapter = _make_adapter_returning(
            executed=False, action="browser.execute_click", selector="#delete-btn", result_code="risky_element"
        )
        bridge, store, coll = _make_bridge(adapter=adapter)
        _create_appr(store, selector="#delete-btn")
        msg = _valid_msg(selector="#delete-btn")
        result = bridge.handle_inbound_message_sync(msg)
        self.assertIn(result["status"], {"blocked", "failed"})
        coll.assert_no_secrets()


# ---------------------------------------------------------------------------
# 12-18: Callback content / security
# ---------------------------------------------------------------------------


class TestCallbackContent(unittest.TestCase):
    def setUp(self):
        self.bridge, self.store, self.coll = _make_bridge()
        _create_appr(self.store)
        self.result = self.bridge.handle_inbound_message_sync(_valid_msg())

    def test_result_callback_contains_task_id(self):
        self.assertEqual(self.result["task_id"], "t1")
        self.assertEqual(self.coll.last_message()["task_id"], "t1")

    def test_result_callback_contains_only_safe_fields(self):
        for k in self.result:
            self.assertNotIn(
                k.lower(), {fk.lower() for fk in RESULT_DATA_FORBIDDEN_KEYS}, f"forbidden key in callback: {k}"
            )

    def test_result_callback_does_not_include_approval_token(self):
        self.assertNotIn("approval_token", self.result)
        self.assertNotIn("tok-1", str(self.result))

    def test_result_callback_does_not_include_final_approval_token(self):
        self.assertNotIn("final_approval_token", self.result)

    def test_result_callback_does_not_include_token_hash(self):
        self.assertNotIn("token_hash", self.result)

    def test_result_callback_does_not_include_raw_typed_text(self):
        adapter = _make_adapter_returning(action="browser.execute_type", selector="#in")
        bridge, store, coll = _make_bridge(adapter=adapter)
        _create_appr(store, action_type="browser.execute_type", selector="#in")
        msg = _valid_msg(action_type="browser.execute_type", selector="#in", value="my-secret-input")
        result = bridge.handle_inbound_message_sync(msg)
        self.assertNotIn("my-secret-input", str(result))
        self.assertNotIn("typed_text", result)
        coll.assert_no_secrets()

    def test_result_callback_does_not_include_cookie_session_storage_base64(self):
        for forbidden in ["cookie", "session", "localStorage", "sessionStorage", "base64", "Authorization"]:
            self.assertNotIn(forbidden, self.result)


# ---------------------------------------------------------------------------
# 19-21: Bridge contract guarantees
# ---------------------------------------------------------------------------


class TestBridgeContract(unittest.TestCase):
    @staticmethod
    def _strip_strings_and_comments(src: str) -> str:
        """Drop docstrings, string literals, and comments — leaving only executable code."""
        import io
        import tokenize

        out = []
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            tt, ts, *_ = tok
            if tt in (tokenize.STRING, tokenize.COMMENT):
                continue
            out.append(ts)
        return " ".join(out)

    def test_bridge_never_connects_to_real_websocket(self):
        """Executable code (not docstrings) must not call websockets/aiohttp ws clients."""
        from core.agent_runtime.browser.bridge import browser_websocket_bridge as bwb

        code = self._strip_strings_and_comments(inspect.getsource(bwb))
        for forbidden in ["websockets.connect", "aiohttp.ClientSession", "websockets.client"]:
            self.assertNotIn(forbidden, code, f"Bridge must not use real WebSocket: {forbidden}")

    def test_bridge_uses_schema_before_handler(self):
        """Schema validation MUST appear before handler dispatch in source order."""
        from core.agent_runtime.browser.bridge import browser_websocket_bridge as bwb

        src = inspect.getsource(bwb)
        idx_schema = src.find("BrowserWebSocketTaskPayloadSchema.from_dict(")
        idx_handler = src.find("self._handler.handle_task(")
        self.assertGreater(idx_schema, 0)
        self.assertGreater(idx_handler, 0)
        self.assertLess(idx_schema, idx_handler, "Schema validation must appear BEFORE handler dispatch")

    def test_bridge_uses_task_handler_not_controller_directly(self):
        """Executable code must not reference BrowserController."""
        from core.agent_runtime.browser.bridge import browser_websocket_bridge as bwb

        code = self._strip_strings_and_comments(inspect.getsource(bwb))
        self.assertNotIn("BrowserController", code, "Bridge must not call BrowserController directly")


# ---------------------------------------------------------------------------
# 22: Handler exception → safe failed result
# ---------------------------------------------------------------------------


class TestHandlerExceptionHandling(unittest.TestCase):
    def test_handler_exception_returns_safe_failed_result(self):
        """If task handler raises, bridge returns failed result without stack trace."""
        bad_handler = MagicMock()

        async def _raises(_):
            raise RuntimeError("super-secret-internal-detail-xyz")

        bad_handler.handle_task = _raises
        coll = MockResultCallbackCollector()
        bridge = BrowserLocalWebSocketBridge(task_handler=bad_handler, callback=coll.append)
        result = bridge.handle_inbound_message_sync(_valid_msg())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "handler_exception")
        # Internal detail must NOT leak into callback
        self.assertNotIn("super-secret-internal-detail-xyz", str(result))
        coll.assert_no_secrets()


# ---------------------------------------------------------------------------
# 23-24: Persistent + DB store integration
# ---------------------------------------------------------------------------


class TestStoreIntegration(unittest.TestCase):
    def test_persistent_store_integration(self):
        store = PersistentBrowserApprovalStore()
        bridge, _, coll = _make_bridge(store=store)
        _create_appr(store)
        result = bridge.handle_inbound_message_sync(_valid_msg())
        self.assertEqual(result["status"], "executed")
        coll.assert_no_secrets()

    def test_db_store_integration(self):
        store = SQLiteBrowserApprovalStore()
        bridge, _, coll = _make_bridge(store=store)
        _create_appr(store)
        result = bridge.handle_inbound_message_sync(_valid_msg())
        self.assertEqual(result["status"], "executed")
        # DB store should mark used after successful execution
        rec = store.get("appr-1")
        self.assertEqual(rec.status, "used")
        coll.assert_no_secrets()


# ---------------------------------------------------------------------------
# Async direct path (verifies asyncio.run wrapper is sane)
# ---------------------------------------------------------------------------


class TestAsyncEntrypoint(unittest.TestCase):
    def test_handle_inbound_message_async(self):
        bridge, store, coll = _make_bridge()
        _create_appr(store)
        result = asyncio.run(bridge.handle_inbound_message(_valid_msg()))
        self.assertEqual(result["status"], "executed")
        coll.assert_no_secrets()


if __name__ == "__main__":
    unittest.main()

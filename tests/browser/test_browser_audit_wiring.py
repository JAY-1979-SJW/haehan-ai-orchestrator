"""BROWSER-AUDIT-2: audit writer dry-run wiring tests.

Verifies BrowserLocalWebSocketBridge correctly emits BrowserAuditEvent
records to an injected audit writer (MockAuditWriter) for the four
lifecycle points (validation_failed / blocked / executed / failed),
and never leaks tokens or other forbidden material.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock

from core.agent_runtime.browser.approval.browser_approval_verifier import (
    BrowserApprovalStore,
    BrowserApprovalVerifier,
)
from core.agent_runtime.browser.approval.browser_audit_contract import (
    FORBIDDEN_AUDIT_FIELDS,
    REQUIRED_AUDIT_COLUMNS,
    BrowserAuditEventType,
    MockAuditWriter,
    build_browser_approval_audit_event,
)
from core.agent_runtime.browser.bridge.browser_websocket_bridge import (
    BrowserLocalWebSocketBridge,
    MockResultCallbackCollector,
)
from core.agent_runtime.browser.browser_action_contract import ExecutionResult
from core.agent_runtime.browser.browser_task_handler import BrowserTaskHandler
from core.agent_runtime.browser.server_action_adapter import ServerActionAdapter

SECRET_TOKEN = "tok-secret-abc"
SECRET_FINAL = "final-secret-xyz"
SECRET_TYPED = "p@ssw0rd-typed-text"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _adapter_returning(
    *,
    executed=True,
    action="browser.execute_click",
    selector="#btn",
    result_code="success",
    element_found=True,
    status_override=None,
):
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


def _make_bridge(*, audit_writer=None, audit_context=None, adapter=None, store=None):
    store = store or BrowserApprovalStore()
    adapter = adapter or _adapter_returning()
    verifier = BrowserApprovalVerifier(store)
    handler = BrowserTaskHandler(server_action_adapter=adapter, approval_verifier=verifier)
    coll = MockResultCallbackCollector()
    bridge = BrowserLocalWebSocketBridge(
        task_handler=handler,
        callback=coll.append,
        audit_writer=audit_writer,
        audit_context=audit_context,
    )
    return bridge, store, coll


def _valid_msg(
    *,
    task_id="t1",
    approval_id="appr-1",
    token=SECRET_TOKEN,
    action_type="browser.execute_click",
    selector="#btn",
    value=None,
    final_token=None,
):
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
    if final_token is not None:
        msg["final_approval_token"] = final_token
    return msg


def _create_appr(
    store, *, approval_id="appr-1", token=SECRET_TOKEN, action_type="browser.execute_click", selector="#btn"
):
    return store.create_approval(
        approval_id=approval_id,
        action_type=action_type,
        selector=selector,
        approval_token=token,
    )


def _row_blob(record):
    return json.dumps(record, sort_keys=True, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# 1. Bridge → audit on success
# ---------------------------------------------------------------------------


class TestSuccessAudit(unittest.TestCase):
    def test_bridge_success_result_writes_audit_event(self):
        writer = MockAuditWriter()
        bridge, store, coll = _make_bridge(audit_writer=writer)
        _create_appr(store)

        bridge.handle_inbound_message_sync(_valid_msg())

        self.assertEqual(len(writer.records), 1)
        row = writer.last()
        self.assertEqual(row["event_type"], BrowserAuditEventType.TASK_EXECUTED.value)
        self.assertEqual(row["status"], "PASS")
        self.assertEqual(row["target_id"], "t1")
        self.assertEqual(row["request_id"], "t1")
        self.assertIsNotNone(row["payload_hash"])
        self.assertEqual(row["metadata_json"]["task_id"], "t1")
        self.assertEqual(row["metadata_json"]["bridge_status"], "callback_built")


# ---------------------------------------------------------------------------
# 2. Bridge → audit on blocked
# ---------------------------------------------------------------------------


class TestBlockedAudit(unittest.TestCase):
    def test_bridge_blocked_result_writes_audit_event(self):
        writer = MockAuditWriter()
        # No approval created → verifier returns blocked
        bridge, store, coll = _make_bridge(audit_writer=writer)
        bridge.handle_inbound_message_sync(_valid_msg())

        self.assertEqual(len(writer.records), 1)
        row = writer.last()
        self.assertEqual(row["status"], "WARN")
        self.assertEqual(row["event_type"], BrowserAuditEventType.TASK_BLOCKED.value)


# ---------------------------------------------------------------------------
# 3. Bridge → audit on validation_failed
# ---------------------------------------------------------------------------


class TestValidationFailedAudit(unittest.TestCase):
    def test_bridge_validation_failed_writes_audit_event(self):
        writer = MockAuditWriter()
        bridge, store, coll = _make_bridge(audit_writer=writer)
        bridge.handle_inbound_message_sync({"task_type": "browser_action"})

        self.assertEqual(len(writer.records), 1)
        row = writer.last()
        self.assertEqual(row["event_type"], BrowserAuditEventType.TASK_VALIDATION_FAILED.value)
        self.assertEqual(row["status"], "WARN")
        self.assertEqual(row["error_code"], "schema_invalid")
        self.assertEqual(row["target_id"], "unknown")

    def test_bridge_validation_failed_does_not_persist_raw_inbound(self):
        writer = MockAuditWriter()
        bridge, store, coll = _make_bridge(audit_writer=writer)
        # Raw inbound contains a forbidden field — must not appear in audit
        bad = {
            "task_type": "browser_action",
            "approval_token": SECRET_TOKEN,
            "cookies": "session=evil",
        }
        bridge.handle_inbound_message_sync(bad)

        blob = _row_blob(writer.last())
        self.assertNotIn(SECRET_TOKEN, blob)
        self.assertNotIn("evil", blob)


# ---------------------------------------------------------------------------
# 4. Bridge → audit on handler exception
# ---------------------------------------------------------------------------


class TestHandlerExceptionAudit(unittest.TestCase):
    def test_bridge_handler_exception_writes_failed_audit_event(self):
        writer = MockAuditWriter()

        class BoomHandler:
            async def handle_task(self, _payload):
                raise RuntimeError("boom secret approval_token=" + SECRET_TOKEN)

        coll = MockResultCallbackCollector()
        bridge = BrowserLocalWebSocketBridge(
            task_handler=BoomHandler(),
            callback=coll.append,
            audit_writer=writer,
        )
        store = BrowserApprovalStore()
        _create_appr(store)
        # Use valid schema so handler is reached
        bridge.handle_inbound_message_sync(_valid_msg())

        self.assertEqual(len(writer.records), 1)
        row = writer.last()
        self.assertEqual(row["event_type"], BrowserAuditEventType.TASK_FAILED.value)
        self.assertEqual(row["status"], "FAIL")
        self.assertEqual(row["error_code"], "handler_exception")
        # error_message holds class name only — never raw exception text
        self.assertEqual(row["error_message"], "RuntimeError")
        blob = _row_blob(row)
        self.assertNotIn(SECRET_TOKEN, blob)
        self.assertNotIn("boom secret", blob)


# ---------------------------------------------------------------------------
# 5. Existing behavior preserved without writer
# ---------------------------------------------------------------------------


class TestNoAuditWriter(unittest.TestCase):
    def test_bridge_without_audit_writer_preserves_existing_behavior(self):
        bridge, store, coll = _make_bridge()
        _create_appr(store)
        result = bridge.handle_inbound_message_sync(_valid_msg())
        self.assertEqual(result["status"], "executed")
        coll.assert_no_secrets()


# ---------------------------------------------------------------------------
# 6. Writer failure is non-fatal
# ---------------------------------------------------------------------------


class _ExplodingWriter:
    def __init__(self):
        self.attempts = 0

    def write(self, _event):
        self.attempts += 1
        raise RuntimeError("disk full")


class TestAuditFailureIsNonFatal(unittest.TestCase):
    def test_audit_writer_failure_does_not_break_callback(self):
        writer = _ExplodingWriter()
        bridge, store, coll = _make_bridge(audit_writer=writer)
        _create_appr(store)
        result = bridge.handle_inbound_message_sync(_valid_msg())
        self.assertEqual(result["status"], "executed")
        self.assertEqual(writer.attempts, 1)
        coll.assert_no_secrets()


# ---------------------------------------------------------------------------
# 7-12. Token / secret non-disclosure in audit row
# ---------------------------------------------------------------------------


class TestAuditNoSecrets(unittest.TestCase):
    def _run_with(self, msg_kwargs=None):
        writer = MockAuditWriter()
        bridge, store, coll = _make_bridge(audit_writer=writer)
        _create_appr(store)
        bridge.handle_inbound_message_sync(_valid_msg(**(msg_kwargs or {})))
        return writer

    def test_audit_event_does_not_include_approval_token(self):
        writer = self._run_with()
        self.assertNotIn(SECRET_TOKEN, _row_blob(writer.last()))

    def test_audit_event_does_not_include_final_approval_token(self):
        writer = self._run_with({"final_token": SECRET_FINAL})
        self.assertNotIn(SECRET_FINAL, _row_blob(writer.last()))

    def test_audit_event_does_not_include_token_hash(self):
        writer = self._run_with()
        row = writer.last()
        self.assertNotIn("token_hash", {k.lower() for k in row})
        self.assertNotIn("token_hash", {k.lower() for k in row["metadata_json"]})

    def test_audit_event_does_not_include_typed_text(self):
        # execute_type with typed value
        adapter = _adapter_returning(action="browser.execute_type", selector="#input")
        store = BrowserApprovalStore()
        store.create_approval(
            approval_id="appr-1",
            action_type="browser.execute_type",
            selector="#input",
            approval_token=SECRET_TOKEN,
        )
        writer = MockAuditWriter()
        bridge, _, _coll = _make_bridge(audit_writer=writer, adapter=adapter, store=store)
        msg = _valid_msg(action_type="browser.execute_type", selector="#input", value=SECRET_TYPED)
        bridge.handle_inbound_message_sync(msg)
        self.assertNotIn(SECRET_TYPED, _row_blob(writer.last()))

    def test_audit_event_does_not_include_cookie_session_storage_base64(self):
        writer = MockAuditWriter()
        bridge, store, coll = _make_bridge(audit_writer=writer)
        bad = {
            "task_type": "browser_action",
            "task_id": "t1",
            "action_type": "browser.execute_click",
            "selector": "#btn",
            "approval_id": "appr-1",
            "approval_token": SECRET_TOKEN,
            "cookie": "x=1",
            "session": "abc",
            "localStorage": {"a": 1},
            "sessionStorage": {"b": 2},
            "raw_screenshot": "iVBORw0KGgo=",
            "base64": "ZXZpbA==",
        }
        bridge.handle_inbound_message_sync(bad)
        row = writer.last()
        self.assertIsNotNone(row)
        blob = _row_blob(row)
        for needle in ("x=1", "abc", "iVBORw0KGgo=", "ZXZpbA=="):
            self.assertNotIn(needle, blob)
        # Top-level forbidden keys absent
        for k in row:
            self.assertNotIn(k.lower(), {f.lower() for f in FORBIDDEN_AUDIT_FIELDS})

    def test_audit_event_does_not_include_raw_stack_trace(self):
        writer = MockAuditWriter()

        class BoomHandler:
            async def handle_task(self, _payload):
                raise RuntimeError("Traceback (most recent call last)\n  File ...")

        coll = MockResultCallbackCollector()
        bridge = BrowserLocalWebSocketBridge(
            task_handler=BoomHandler(),
            callback=coll.append,
            audit_writer=writer,
        )
        store = BrowserApprovalStore()
        _create_appr(store)
        bridge.handle_inbound_message_sync(_valid_msg())
        blob = _row_blob(writer.last())
        self.assertNotIn("Traceback", blob)
        self.assertNotIn("File ...", blob)


# ---------------------------------------------------------------------------
# 13. Metadata content
# ---------------------------------------------------------------------------


class TestAuditMetadataContents(unittest.TestCase):
    def test_audit_metadata_contains_task_id_action_risk_result(self):
        writer = MockAuditWriter()
        bridge, store, coll = _make_bridge(audit_writer=writer)
        _create_appr(store)
        bridge.handle_inbound_message_sync(_valid_msg())
        meta = writer.last()["metadata_json"]
        self.assertEqual(meta["task_id"], "t1")
        self.assertEqual(meta["action_type"], "browser.execute_click")
        self.assertEqual(meta["risk_level"], "low")
        self.assertEqual(meta["result"], "success")


# ---------------------------------------------------------------------------
# 14. payload_hash uses only safe payload
# ---------------------------------------------------------------------------


class TestPayloadHashSafe(unittest.TestCase):
    def test_audit_payload_hash_uses_safe_payload_only(self):
        from core.agent_runtime.browser.approval.browser_audit_contract import hash_safe_payload

        writer = MockAuditWriter()
        bridge, store, coll = _make_bridge(audit_writer=writer)
        _create_appr(store)
        bridge.handle_inbound_message_sync(_valid_msg())
        row = writer.last()
        expected = hash_safe_payload(row["metadata_json"])
        self.assertEqual(row["payload_hash"], expected)


# ---------------------------------------------------------------------------
# 15. Approval decision audit event (factory-level) without token
# ---------------------------------------------------------------------------


class TestApprovalDecisionAudit(unittest.TestCase):
    def test_approval_decision_audit_event_without_token(self):
        event = build_browser_approval_audit_event(
            event_type=BrowserAuditEventType.APPROVAL_APPROVED,
            approval_id="appr-1",
            task_id="t1",
            action_type="browser.execute_click",
            selector="#btn",
            actor_role="admin",
            request_id="t1",
        )
        row = event.to_audit_row()
        blob = _row_blob(row)
        self.assertNotIn(SECRET_TOKEN, blob)
        self.assertEqual(row["event_type"], BrowserAuditEventType.APPROVAL_APPROVED.value)
        self.assertEqual(row["metadata_json"]["approval_id"], "appr-1")
        self.assertNotIn("approval_token", {k.lower() for k in row["metadata_json"]})


# ---------------------------------------------------------------------------
# 16. MockAuditWriter records required columns
# ---------------------------------------------------------------------------


class TestRequiredColumns(unittest.TestCase):
    def test_mockauditwriter_records_required_columns(self):
        writer = MockAuditWriter()
        bridge, store, coll = _make_bridge(audit_writer=writer)
        _create_appr(store)
        bridge.handle_inbound_message_sync(_valid_msg())
        row = writer.last()
        for col in REQUIRED_AUDIT_COLUMNS:
            self.assertIn(col, row, f"missing required column: {col}")


if __name__ == "__main__":
    unittest.main()

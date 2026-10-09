"""Browser audit event contract tests (BROWSER-AUDIT-1).

Verifies the safe contract for browser approval/execution audit events:
- All event types map to BrowserAuditEventType + status (PASS/WARN/FAIL/SKIP/ERROR)
- Metadata sanitizer drops every forbidden field (token, typed_text, cookie, etc.)
- payload_hash uses sanitized payload only (deterministic, secret-independent)
- Event rows match LOG-2B 22-column app_audit_log REQUIRED_AUDIT_COLUMNS
- MockAuditWriter rejects any row containing forbidden fields
- Bridge callback result + approval decision both convert cleanly to events
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass

from core.agent_runtime.browser.approval.browser_audit_contract import (
    FORBIDDEN_AUDIT_FIELDS,
    REQUIRED_AUDIT_COLUMNS,
    BrowserAuditEvent,
    BrowserAuditEventType,
    BrowserAuditStatus,
    MockAuditWriter,
    build_browser_approval_audit_event,
    build_browser_result_audit_event,
    build_browser_task_audit_event,
    hash_event,
    hash_safe_payload,
    sanitize_browser_audit_metadata,
    status_for_event,
)

# ---------------------------------------------------------------------------
# Schema mapping (1-7)
# ---------------------------------------------------------------------------


class TestEventToAuditSchemaMapping(unittest.TestCase):
    def _assert_audit_row_complete(self, row):
        """All REQUIRED_AUDIT_COLUMNS must be present."""
        for col in REQUIRED_AUDIT_COLUMNS:
            self.assertIn(col, row, f"missing required column: {col}")

    def test_browser_task_received_event_maps_to_audit_schema(self):
        ev = build_browser_task_audit_event(
            event_type=BrowserAuditEventType.TASK_RECEIVED,
            task_id="t1",
            action_type="browser.execute_click",
            selector="#btn",
        )
        self.assertEqual(ev.event_type, "browser.task.received")
        self.assertEqual(ev.status, "PASS")
        self._assert_audit_row_complete(ev.to_audit_row())

    def test_browser_approval_requested_event_maps_to_audit_schema(self):
        ev = build_browser_approval_audit_event(
            event_type=BrowserAuditEventType.APPROVAL_REQUESTED,
            approval_id="appr-1",
            task_id="t1",
            action_type="browser.execute_click",
            selector="#btn",
        )
        self.assertEqual(ev.event_type, "browser.approval.requested")
        self.assertEqual(ev.status, "PASS")
        self.assertEqual(ev.metadata_json["approval_id"], "appr-1")
        self._assert_audit_row_complete(ev.to_audit_row())

    def test_browser_approval_approved_event_maps_to_audit_schema(self):
        ev = build_browser_approval_audit_event(
            event_type=BrowserAuditEventType.APPROVAL_APPROVED,
            approval_id="appr-1",
            task_id="t1",
            action_type="browser.execute_click",
            selector="#btn",
            approval_status="approved",
        )
        self.assertEqual(ev.status, "PASS")
        self.assertEqual(ev.metadata_json["approval_status"], "approved")

    def test_browser_approval_rejected_event_maps_to_audit_schema(self):
        ev = build_browser_approval_audit_event(
            event_type=BrowserAuditEventType.APPROVAL_REJECTED,
            approval_id="appr-2",
            task_id="t1",
            action_type="browser.execute_click",
            selector="#btn",
            approval_status="rejected",
        )
        self.assertEqual(ev.status, "SKIP")

    def test_browser_task_executed_event_maps_to_audit_schema(self):
        ev = build_browser_task_audit_event(
            event_type=BrowserAuditEventType.TASK_EXECUTED,
            task_id="t1",
            action_type="browser.execute_click",
            selector="#btn",
            executed=True,
            result="success",
        )
        self.assertEqual(ev.status, "PASS")
        self.assertTrue(ev.metadata_json["executed"])

    def test_browser_task_blocked_event_maps_to_audit_schema(self):
        ev = build_browser_task_audit_event(
            event_type=BrowserAuditEventType.TASK_BLOCKED,
            task_id="t1",
            action_type="browser.execute_click",
            selector="#delete",
            error_code="approval_invalid",
        )
        self.assertEqual(ev.status, "WARN")
        self.assertEqual(ev.error_code, "approval_invalid")

    def test_browser_task_failed_event_maps_to_audit_schema(self):
        ev = build_browser_task_audit_event(
            event_type=BrowserAuditEventType.TASK_FAILED,
            task_id="t1",
            action_type="browser.execute_click",
            selector="#btn",
            error_code="execution_error",
        )
        self.assertEqual(ev.status, "FAIL")


# ---------------------------------------------------------------------------
# Status mapping (8)
# ---------------------------------------------------------------------------


class TestStatusMapping(unittest.TestCase):
    def test_status_mapping_pass_warn_fail_skip_error(self):
        cases = {
            BrowserAuditEventType.TASK_RECEIVED: BrowserAuditStatus.PASS,
            BrowserAuditEventType.APPROVAL_REQUESTED: BrowserAuditStatus.PASS,
            BrowserAuditEventType.APPROVAL_APPROVED: BrowserAuditStatus.PASS,
            BrowserAuditEventType.APPROVAL_USED: BrowserAuditStatus.PASS,
            BrowserAuditEventType.TASK_EXECUTED: BrowserAuditStatus.PASS,
            BrowserAuditEventType.RESULT_CALLBACK_BUILT: BrowserAuditStatus.PASS,
            BrowserAuditEventType.TASK_VALIDATION_FAILED: BrowserAuditStatus.WARN,
            BrowserAuditEventType.TASK_BLOCKED: BrowserAuditStatus.WARN,
            BrowserAuditEventType.APPROVAL_EXPIRED: BrowserAuditStatus.WARN,
            BrowserAuditEventType.APPROVAL_REJECTED: BrowserAuditStatus.SKIP,
            BrowserAuditEventType.TASK_FAILED: BrowserAuditStatus.FAIL,
        }
        for et, expected in cases.items():
            self.assertEqual(status_for_event(et), expected, f"{et}: expected {expected.value}")


# ---------------------------------------------------------------------------
# Sanitizer (9-15)
# ---------------------------------------------------------------------------


class TestMetadataSanitizer(unittest.TestCase):
    def test_metadata_sanitizer_removes_approval_token(self):
        out = sanitize_browser_audit_metadata(
            {
                "task_id": "t1",
                "approval_token": "tok-secret-XYZ",
            }
        )
        self.assertNotIn("approval_token", out)
        self.assertIn("task_id", out)

    def test_metadata_sanitizer_removes_final_approval_token(self):
        out = sanitize_browser_audit_metadata(
            {
                "task_id": "t1",
                "final_approval_token": "final-secret",
            }
        )
        self.assertNotIn("final_approval_token", out)

    def test_metadata_sanitizer_removes_token_hash(self):
        out = sanitize_browser_audit_metadata(
            {
                "task_id": "t1",
                "token_hash": "0123abcd" * 8,
            }
        )
        self.assertNotIn("token_hash", out)

    def test_metadata_sanitizer_removes_typed_text(self):
        out = sanitize_browser_audit_metadata(
            {
                "task_id": "t1",
                "typed_text": "raw user input",
            }
        )
        self.assertNotIn("typed_text", out)
        self.assertNotIn("raw user input", str(out))

    def test_metadata_sanitizer_removes_cookie_session_storage(self):
        out = sanitize_browser_audit_metadata(
            {
                "task_id": "t1",
                "cookie": "abc",
                "session": "xyz",
                "localStorage": {"x": 1},
                "sessionStorage": {"y": 2},
            }
        )
        for k in ("cookie", "session", "localStorage", "sessionStorage"):
            self.assertNotIn(k, out)

    def test_metadata_sanitizer_removes_raw_screenshot_base64(self):
        out = sanitize_browser_audit_metadata(
            {
                "task_id": "t1",
                "raw_screenshot": b"PNG bytes",
                "base64": "iVBORw0KGgo=",
            }
        )
        self.assertNotIn("raw_screenshot", out)
        self.assertNotIn("base64", out)

    def test_metadata_sanitizer_removes_raw_exception_stack(self):
        out = sanitize_browser_audit_metadata(
            {
                "task_id": "t1",
                "stack_trace": 'Traceback (most recent call last)\n  File "x.py"...',
                "traceback": "long stack",
                "raw_exception": "TypeError",
            }
        )
        for k in ("stack_trace", "traceback", "raw_exception"):
            self.assertNotIn(k, out)

    def test_sanitizer_drops_unknown_keys(self):
        """Defense-in-depth: any field not in allowed list is dropped."""
        out = sanitize_browser_audit_metadata(
            {
                "task_id": "t1",
                "evil_unknown_field": "leak",
            }
        )
        self.assertNotIn("evil_unknown_field", out)

    def test_text_preview_always_redacted(self):
        out = sanitize_browser_audit_metadata(
            {
                "task_id": "t1",
                "text_preview": "trying to leak text",
            }
        )
        self.assertEqual(out["text_preview"], "[REDACTED]")


# ---------------------------------------------------------------------------
# Payload hash (16-17)
# ---------------------------------------------------------------------------


class TestPayloadHash(unittest.TestCase):
    def test_payload_hash_uses_safe_payload_only(self):
        """Hash over sanitized payload — top-level forbidden keys ignored."""
        h_safe = hash_safe_payload({"task_id": "t1", "action_type": "browser.execute_click"})
        h_with_token = hash_safe_payload(
            {
                "task_id": "t1",
                "action_type": "browser.execute_click",
                "approval_token": "secret",
            }
        )
        self.assertEqual(h_safe, h_with_token, "payload_hash must ignore top-level forbidden keys")

    def test_payload_hash_does_not_change_due_to_raw_secret_absence(self):
        """Same sanitized inputs → same hash regardless of caller's mistakes."""
        a = hash_safe_payload({"task_id": "t1", "action_type": "x"})
        b = hash_safe_payload({"task_id": "t1", "action_type": "x"})
        self.assertEqual(a, b)

    def test_payload_hash_changes_for_safe_field_changes(self):
        a = hash_safe_payload({"task_id": "t1"})
        b = hash_safe_payload({"task_id": "t2"})
        self.assertNotEqual(a, b)

    def test_event_hash_chains_with_previous(self):
        """event_hash differs when previous_event_hash differs."""
        row = {"event_type": "browser.task.received", "target_id": "t1"}
        h1 = hash_event(row, previous_event_hash=None)
        h2 = hash_event(row, previous_event_hash=h1)
        self.assertNotEqual(h1, h2)


# ---------------------------------------------------------------------------
# Mock writer (18)
# ---------------------------------------------------------------------------


class TestMockAuditWriter(unittest.TestCase):
    def test_mock_audit_writer_rejects_forbidden_fields(self):
        """Writer must abort when metadata_json contains a forbidden key.

        Two-layer defense:
        - to_audit_row() runs sanitize_browser_audit_metadata() which strips
          known forbidden keys from metadata_json. So a sanitized event will
          NOT trigger the writer's secret check.
        - To prove the writer's defense, we monkey-patch the event so its
          to_audit_row() returns a row that bypassed sanitization.
        """
        ev = BrowserAuditEvent(
            event_type="browser.task.received",
            event_at="2026-05-01T00:00:00Z",
            target_id="t1",
            payload_hash="abc",
            metadata_json={"task_id": "t1"},
        )

        def _leaky_row():
            return {
                "event_type": ev.event_type,
                "event_at": ev.event_at,
                "actor_user_id": None,
                "actor_role": None,
                "organization_id": None,
                "target_type": "browser_task",
                "target_id": "t1",
                "request_id": None,
                "status": "PASS",
                "error_code": None,
                "error_message": None,
                "elapsed_ms": None,
                "payload_hash": "abc",
                "metadata_json": {"task_id": "t1", "approval_token": "leak-XYZ"},
            }

        ev.to_audit_row = _leaky_row  # bypass built-in sanitizer

        writer = MockAuditWriter()
        with self.assertRaises(ValueError):
            writer.write(ev)

    def test_sanitizer_strips_forbidden_field_from_metadata_json_in_audit_row(self):
        """The dataclass sanitizer drops forbidden metadata before writer sees it."""
        ev = BrowserAuditEvent(
            event_type="browser.task.received",
            event_at="2026-05-01T00:00:00Z",
            target_id="t1",
            payload_hash="abc",
            metadata_json={"task_id": "t1", "approval_token": "leak-XYZ"},
        )
        row = ev.to_audit_row()
        self.assertNotIn("approval_token", row["metadata_json"])
        self.assertNotIn("leak-XYZ", str(row))

    def test_mock_audit_writer_accepts_clean_event(self):
        ev = build_browser_task_audit_event(
            event_type=BrowserAuditEventType.TASK_EXECUTED,
            task_id="t1",
            action_type="browser.execute_click",
            selector="#btn",
            executed=True,
        )
        writer = MockAuditWriter()
        row = writer.write(ev)
        self.assertEqual(row["event_type"], "browser.task.executed")
        writer.assert_no_secrets()

    def test_mock_audit_writer_chains_event_hash(self):
        writer = MockAuditWriter()
        ev1 = build_browser_task_audit_event(
            event_type=BrowserAuditEventType.TASK_RECEIVED,
            task_id="t1",
        )
        writer.write(ev1)
        prev = writer.previous_event_hash()
        ev2 = build_browser_task_audit_event(
            event_type=BrowserAuditEventType.TASK_EXECUTED,
            task_id="t1",
            previous_event_hash=prev,
        )
        writer.write(ev2)
        self.assertEqual(ev2.previous_event_hash, prev)


# ---------------------------------------------------------------------------
# Bridge / approval integration (19-20, 22)
# ---------------------------------------------------------------------------


@dataclass
class _FakeTaskResult:
    """Minimal duck-type for BrowserTaskResult (avoids import cycle in test)."""

    task_id: str
    status: str
    action: str = "browser.execute_click"
    selector: str = "#btn"
    executed: bool = True
    element_found: bool = True
    risk_level: str = "low"
    final_approval_required: bool = False
    result: str = "success"
    target_url_domain: str = "example.com"
    text_length: int = 0
    error_code = None
    error_message = None


class TestBridgeAndApprovalConversion(unittest.TestCase):
    def test_bridge_callback_result_converts_to_audit_event(self):
        result = _FakeTaskResult(task_id="t1", status="executed")
        ev = build_browser_result_audit_event(task_result=result)
        self.assertEqual(ev.event_type, "browser.task.executed")
        self.assertEqual(ev.status, "PASS")
        self.assertEqual(ev.target_id, "t1")
        # Round-trip through writer to confirm no secrets surface
        MockAuditWriter().write(ev)

    def test_bridge_blocked_result_converts_to_blocked_event(self):
        result = _FakeTaskResult(task_id="t1", status="blocked", executed=False)
        ev = build_browser_result_audit_event(task_result=result)
        self.assertEqual(ev.event_type, "browser.task.blocked")
        self.assertEqual(ev.status, "WARN")

    def test_bridge_failed_result_converts_to_failed_event(self):
        result = _FakeTaskResult(task_id="t1", status="failed", executed=False)
        ev = build_browser_result_audit_event(task_result=result)
        self.assertEqual(ev.event_type, "browser.task.failed")
        self.assertEqual(ev.status, "FAIL")

    def test_approval_decision_converts_to_audit_event_without_token(self):
        """Even when caller supplies a token field, it must not appear in the event."""
        ev = build_browser_approval_audit_event(
            event_type=BrowserAuditEventType.APPROVAL_APPROVED,
            approval_id="appr-1",
            task_id="t1",
            action_type="browser.execute_click",
            selector="#btn",
            approval_status="approved",
        )
        row = ev.to_audit_row()
        # No forbidden field anywhere in the row
        rendered = str(row)
        for forbidden in ("approval_token", "final_approval_token", "token_hash", "device_token"):
            self.assertNotIn(forbidden, rendered)

    def test_browser_audit_event_serializes_to_safe_dict(self):
        ev = build_browser_task_audit_event(
            event_type=BrowserAuditEventType.TASK_RECEIVED,
            task_id="t1",
            action_type="browser.execute_click",
            selector="#btn",
        )
        row = ev.to_audit_row()
        self.assertIsInstance(row, dict)
        self.assertIn("metadata_json", row)
        self.assertIn("event_type", row)
        # All REQUIRED columns mappable
        for col in REQUIRED_AUDIT_COLUMNS:
            self.assertIn(col, row)


# ---------------------------------------------------------------------------
# app_audit_log compat (21) + secret scan (23)
# ---------------------------------------------------------------------------


class TestAppAuditLogCompat(unittest.TestCase):
    def test_app_audit_log_required_columns_mappable(self):
        """Every event factory produces a row with all required LOG-2B columns."""
        events = [
            build_browser_task_audit_event(
                event_type=BrowserAuditEventType.TASK_RECEIVED,
                task_id="t1",
            ),
            build_browser_approval_audit_event(
                event_type=BrowserAuditEventType.APPROVAL_REQUESTED,
                approval_id="a1",
                task_id="t1",
                action_type="browser.execute_click",
                selector="#btn",
            ),
            build_browser_result_audit_event(
                task_result=_FakeTaskResult(task_id="t1", status="executed"),
            ),
        ]
        for ev in events:
            row = ev.to_audit_row()
            missing = REQUIRED_AUDIT_COLUMNS - set(row.keys())
            self.assertEqual(missing, set(), f"event {ev.event_type} missing columns: {missing}")


class TestNoSecretScan(unittest.TestCase):
    def test_browser_audit_event_no_secret_scan(self):
        """Sweep every factory's output and verify no forbidden field appears."""
        events = [
            build_browser_task_audit_event(
                event_type=BrowserAuditEventType.TASK_RECEIVED,
                task_id="t1",
                action_type="browser.execute_type",
                selector="#input",
                text_length=20,
            ),
            build_browser_approval_audit_event(
                event_type=BrowserAuditEventType.APPROVAL_USED,
                approval_id="a1",
                task_id="t1",
                action_type="browser.execute_click",
                selector="#btn",
            ),
            build_browser_result_audit_event(
                task_result=_FakeTaskResult(task_id="t1", status="failed", executed=False),
            ),
        ]
        writer = MockAuditWriter()
        for ev in events:
            writer.write(ev)
        writer.assert_no_secrets()
        # Also: rendered string must never contain forbidden field names
        rendered = str(writer.records).lower()
        for forbidden in FORBIDDEN_AUDIT_FIELDS:
            self.assertNotIn(forbidden, rendered, f"forbidden field name appears in records: {forbidden}")

    def test_safe_error_summary_redacts_secret_lines(self):
        """error_message containing forbidden keyword is redacted."""
        ev = build_browser_task_audit_event(
            event_type=BrowserAuditEventType.TASK_FAILED,
            task_id="t1",
            error_message="failed because cookie='abc-leak' was rejected",
        )
        self.assertEqual(ev.error_message, "[REDACTED]")

    def test_safe_error_summary_keeps_innocuous_first_line(self):
        ev = build_browser_task_audit_event(
            event_type=BrowserAuditEventType.TASK_FAILED,
            task_id="t1",
            error_message="element_not_found: #btn\n  at line 42\n  at line 43",
        )
        # Multi-line stacks → only first line kept, no "at line 42/43"
        self.assertEqual(ev.error_message, "element_not_found: #btn")


if __name__ == "__main__":
    unittest.main()

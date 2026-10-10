"""BROWSER-5: SQLite-backed approval store tests.

Tests DB-backed approval store security invariants, persistence,
verifier/task-handler compatibility, and JSONL interface compatibility.

No production DB connections — all tests use in-memory or tmp file SQLite.
"""

from __future__ import annotations

import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from core.agent_runtime.browser.approval.browser_approval_db_store import (
    _FORBIDDEN_DB_COLUMNS,
    DatabaseBrowserApprovalStore,
    SQLiteBrowserApprovalStore,
)
from core.agent_runtime.browser.approval.browser_approval_persistent_store import (
    PersistentBrowserApprovalStore,
)
from core.agent_runtime.browser.approval.browser_approval_verifier import (
    BrowserApprovalVerifier,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_db_store(**kw) -> SQLiteBrowserApprovalStore:
    return SQLiteBrowserApprovalStore(**kw)


def _create_approval(
    store,
    *,
    approval_id="appr-001",
    token="secret-tok",
    action_type="browser.execute_click",
    selector="#btn",
    risk_level="low",
    final_approval_required=False,
    expires_in_seconds=None,
):
    return store.create_approval(
        approval_id=approval_id,
        action_type=action_type,
        selector=selector,
        approval_token=token,
        risk_level=risk_level,
        final_approval_required=final_approval_required,
        expires_in_seconds=expires_in_seconds,
    )


# ---------------------------------------------------------------------------
# 1-2: Token storage security
# ---------------------------------------------------------------------------


class TestDbStoreTokenSecurity(unittest.TestCase):
    def setUp(self):
        self.store = _make_db_store()

    def test_db_store_creates_approval_without_raw_token(self):
        """create_approval must not raise and must return a record without raw token."""
        record = _create_approval(self.store, token="my-raw-token")
        self.assertIsNotNone(record)
        self.assertNotEqual(record.token_hash, "my-raw-token")
        self.assertFalse(hasattr(record, "approval_token"), "Record must not have approval_token attribute")

    def test_db_store_saves_token_hash_only(self):
        """Raw token must never appear in DB; only SHA256 hash stored."""
        raw_token = "ultra-secret-approval-token"
        record = _create_approval(self.store, token=raw_token)

        # Read back from DB
        fetched = self.store.get(record.approval_id)
        self.assertIsNotNone(fetched)

        # token_hash should be SHA256 hexdigest (64 chars), never the raw value
        import hashlib

        expected_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        self.assertEqual(fetched.token_hash, expected_hash)
        self.assertNotEqual(fetched.token_hash, raw_token)
        self.assertEqual(len(fetched.token_hash), 64)

    def test_db_store_no_raw_token_in_db(self):
        """Schema must not have approval_token or final_approval_token columns."""
        _create_approval(self.store, token="tok-xyz")
        columns = self.store.get_column_names()
        columns_lower = [c.lower() for c in columns]
        for forbidden in _FORBIDDEN_DB_COLUMNS:
            self.assertNotIn(forbidden, columns_lower, f"DB schema has forbidden column: '{forbidden}'")

    def test_db_store_no_typed_text(self):
        """Schema must not have typed_text column."""
        columns = [c.lower() for c in self.store.get_column_names()]
        self.assertNotIn("typed_text", columns)

    def test_db_store_no_cookie_session(self):
        """Schema must not have cookie or session columns."""
        columns = [c.lower() for c in self.store.get_column_names()]
        self.assertNotIn("cookie", columns)
        self.assertNotIn("session", columns)
        self.assertNotIn("localstorage", columns)
        self.assertNotIn("sessionstorage", columns)


# ---------------------------------------------------------------------------
# 3-4: Token validation
# ---------------------------------------------------------------------------


class TestDbStoreTokenValidation(unittest.TestCase):
    def setUp(self):
        self.store = _make_db_store()
        self.verifier = BrowserApprovalVerifier(self.store)

    def test_db_store_validates_token(self):
        """Correct token must pass verification."""
        token = "correct-token-abc"
        _create_approval(
            self.store, token=token, approval_id="appr-v1", action_type="browser.execute_click", selector="#go"
        )
        result = self.verifier.verify(
            approval_id="appr-v1",
            approval_token=token,
            action_type="browser.execute_click",
            selector="#go",
        )
        self.assertTrue(result.valid, f"Expected valid, got: {result.error_code}")

    def test_db_store_rejects_wrong_token(self):
        """Wrong token must fail verification."""
        _create_approval(
            self.store, token="real-token", approval_id="appr-v2", action_type="browser.execute_click", selector="#go"
        )
        result = self.verifier.verify(
            approval_id="appr-v2",
            approval_token="wrong-token",
            action_type="browser.execute_click",
            selector="#go",
        )
        self.assertFalse(result.valid)
        self.assertIsNotNone(result.error_code)


# ---------------------------------------------------------------------------
# 5-7: Persistence and one-time use
# ---------------------------------------------------------------------------


class TestDbStorePersistence(unittest.TestCase):
    def test_db_store_persists_after_restart(self, tmp_path=None):
        """Approval created in one store instance must be visible in another."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = Path(tmpdir) / "test_approvals.db"

            store1 = SQLiteBrowserApprovalStore(db_path=db_file)
            _create_approval(store1, approval_id="appr-persist", token="tok-p")
            store1.close()

            store2 = SQLiteBrowserApprovalStore(db_path=db_file)
            record = store2.get("appr-persist")
            self.assertIsNotNone(record, "Record must persist across store instances")
            self.assertEqual(record.approval_id, "appr-persist")
            store2.close()

    def test_db_store_mark_used_persists(self):
        """mark_used must persist status change to DB."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = Path(tmpdir) / "used_test.db"

            store1 = SQLiteBrowserApprovalStore(db_path=db_file)
            _create_approval(store1, approval_id="appr-used", token="tok-u")
            store1.mark_used("appr-used")
            store1.close()

            store2 = SQLiteBrowserApprovalStore(db_path=db_file)
            record = store2.get("appr-used")
            self.assertIsNotNone(record)
            self.assertEqual(record.status, "used")
            store2.close()

    def test_db_store_blocks_reuse(self):
        """Second verification of a used approval must fail."""
        store = _make_db_store()
        verifier = BrowserApprovalVerifier(store)
        _create_approval(
            store, approval_id="appr-reuse", token="tok-r", action_type="browser.execute_click", selector="#x"
        )

        # First use — valid
        r1 = verifier.verify("appr-reuse", "tok-r", "browser.execute_click", "#x")
        self.assertTrue(r1.valid)
        verifier.store.mark_used("appr-reuse")

        # Second use — must be blocked
        r2 = verifier.verify("appr-reuse", "tok-r", "browser.execute_click", "#x")
        self.assertFalse(r2.valid)
        self.assertIn("used", (r2.error_code or "").lower())


# ---------------------------------------------------------------------------
# 8-9: Revoked and expired
# ---------------------------------------------------------------------------


class TestDbStoreStatusBlocking(unittest.TestCase):
    def setUp(self):
        self.store = _make_db_store()
        self.verifier = BrowserApprovalVerifier(self.store)

    def test_db_store_revoked_blocked(self):
        """Revoked approval must fail verification."""
        _create_approval(
            self.store, approval_id="appr-rev", token="tok-rev", action_type="browser.execute_click", selector="#del"
        )
        self.store.revoke("appr-rev")

        result = self.verifier.verify("appr-rev", "tok-rev", "browser.execute_click", "#del")
        self.assertFalse(result.valid)
        self.assertIsNotNone(result.error_code)

    def test_db_store_expired_blocked(self):
        """Expired approval must fail verification."""
        _create_approval(
            self.store,
            approval_id="appr-exp",
            token="tok-exp",
            action_type="browser.execute_click",
            selector="#x",
            expires_in_seconds=1,
        )  # 1 second expiry
        time.sleep(1.1)  # let it expire

        result = self.verifier.verify("appr-exp", "tok-exp", "browser.execute_click", "#x")
        self.assertFalse(result.valid)


# ---------------------------------------------------------------------------
# 13-14: Verifier and task handler compatibility
# ---------------------------------------------------------------------------


class TestVerifierWithDbStore(unittest.TestCase):
    def test_verifier_works_with_db_store(self):
        """BrowserApprovalVerifier must accept SQLiteBrowserApprovalStore."""
        store = SQLiteBrowserApprovalStore()
        verifier = BrowserApprovalVerifier(store)

        _create_approval(
            store, approval_id="appr-db-v", token="db-tok", action_type="browser.execute_click", selector="#submit-btn"
        )

        result = verifier.verify(
            approval_id="appr-db-v",
            approval_token="db-tok",
            action_type="browser.execute_click",
            selector="#submit-btn",
        )
        self.assertTrue(result.valid)
        self.assertIsNone(result.error_code)

    def test_task_handler_works_with_db_store(self):
        """BrowserTaskHandler must accept verifier backed by DB store.

        Verifies that the handler correctly validates approval via DB store
        and rejects a wrong token — without needing a real browser/adapter.
        """
        from core.agent_runtime.browser.browser_task_handler import BrowserTaskHandler, BrowserTaskPayload
        from core.agent_runtime.browser.server_action_adapter import ServerActionAdapter

        store = SQLiteBrowserApprovalStore()
        verifier = BrowserApprovalVerifier(store)

        _create_approval(
            store, approval_id="appr-th", token="task-tok", action_type="browser.execute_click", selector="#confirm"
        )

        mock_adapter = MagicMock(spec=ServerActionAdapter)
        handler = BrowserTaskHandler(
            server_action_adapter=mock_adapter,
            approval_verifier=verifier,
        )

        # Wrong-token payload must be blocked at approval stage (no browser needed)
        import asyncio

        bad_payload = BrowserTaskPayload(
            task_id="task-bad",
            action_type="browser.execute_click",
            selector="#confirm",
            approval_id="appr-th",
            approval_token="wrong-token",
        )
        result = asyncio.run(handler.handle_task(bad_payload))
        self.assertEqual(result.status, "blocked", "Wrong token must be blocked by verifier backed by DB store")

        # Correct-token approval passes verifier; adapter mock returns execution result
        mock_adapter.execute_action = MagicMock(
            return_value=MagicMock(executed=True, element_found=True, error_code=None, error_message=None)
        )
        good_payload = BrowserTaskPayload(
            task_id="task-good",
            action_type="browser.execute_click",
            selector="#confirm",
            approval_id="appr-th",
            approval_token="task-tok",
        )
        result2 = asyncio.run(handler.handle_task(good_payload))
        self.assertNotEqual(result2.status, "blocked", f"Correct token blocked unexpectedly: {result2.error_code}")


# ---------------------------------------------------------------------------
# 15: JSONL store compatibility
# ---------------------------------------------------------------------------


class TestJSONLCompatibility(unittest.TestCase):
    def test_JSONL_store_compatibility_check(self):
        """SQLite store must have same public interface as PersistentBrowserApprovalStore."""
        required_methods = ["create_approval", "get", "mark_used", "revoke", "clear"]

        jsonl_store = PersistentBrowserApprovalStore()
        db_store = SQLiteBrowserApprovalStore()

        for method in required_methods:
            self.assertTrue(hasattr(jsonl_store, method), f"JSONL store missing: {method}")
            self.assertTrue(hasattr(db_store, method), f"DB store missing: {method}")

    def test_both_stores_reject_reuse(self):
        """Both JSONL and DB store must block reuse after mark_used."""
        for store_cls, label in [
            (PersistentBrowserApprovalStore, "JSONL"),
            (SQLiteBrowserApprovalStore, "SQLite"),
        ]:
            with self.subTest(store=label):
                store = store_cls()
                verifier = BrowserApprovalVerifier(store)
                _create_approval(
                    store,
                    approval_id="appr-compat",
                    token="compat-tok",
                    action_type="browser.execute_click",
                    selector="#btn",
                )
                verifier.store.mark_used("appr-compat")
                result = verifier.verify("appr-compat", "compat-tok", "browser.execute_click", "#btn")
                self.assertFalse(result.valid, f"{label} store should block reuse")

    def test_db_store_alias(self):
        """DatabaseBrowserApprovalStore must be same class as SQLiteBrowserApprovalStore."""
        self.assertIs(DatabaseBrowserApprovalStore, SQLiteBrowserApprovalStore)

    def test_db_store_list_pending(self):
        """list_pending matches PersistentBrowserApprovalStore interface for tray app."""
        store = SQLiteBrowserApprovalStore()
        self.assertTrue(hasattr(store, "list_pending"))
        _create_approval(store, approval_id="appr-p1", token="t1")
        _create_approval(store, approval_id="appr-p2", token="t2")
        store.mark_used("appr-p1")

        pending = store.list_pending()
        self.assertNotIn("appr-p1", pending)
        self.assertIn("appr-p2", pending)


# ---------------------------------------------------------------------------
# Schema column validation
# ---------------------------------------------------------------------------


class TestDbSchemaColumns(unittest.TestCase):
    def setUp(self):
        self.store = _make_db_store()
        self.columns = [c.lower() for c in self.store.get_column_names()]

    def test_required_columns_present(self):
        required = {
            "id",
            "approval_id",
            "action_type",
            "selector",
            "token_hash",
            "status",
            "risk_level",
            "final_approval_required",
            "created_at",
            "expires_at",
            "used_at",
            "revoked_at",
        }
        for col in required:
            self.assertIn(col, self.columns, f"Missing required column: {col}")

    def test_forbidden_columns_absent(self):
        for forbidden in _FORBIDDEN_DB_COLUMNS:
            self.assertNotIn(forbidden, self.columns, f"Forbidden column found in schema: '{forbidden}'")


if __name__ == "__main__":
    unittest.main()

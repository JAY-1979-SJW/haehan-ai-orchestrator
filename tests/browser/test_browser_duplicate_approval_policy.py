"""Duplicate approval_id policy tests (P1-FIX).

Verifies that all 3 store implementations (in-memory / JSONL / SQLite)
reject duplicate create_approval() calls with DuplicateApprovalError,
preserving existing record state.

Policy:
- create_approval() with existing approval_id → raise DuplicateApprovalError
- token_hash never overwritten
- status (used / revoked) never reset
- All 3 stores behave identically
"""

from __future__ import annotations

import contextlib
import tempfile
import unittest
from pathlib import Path

from core.agent_runtime.browser.approval.browser_approval_db_store import (
    SQLiteBrowserApprovalStore,
)
from core.agent_runtime.browser.approval.browser_approval_persistent_store import (
    PersistentBrowserApprovalStore,
)
from core.agent_runtime.browser.approval.browser_approval_verifier import (
    BrowserApprovalStore,
    BrowserApprovalVerifier,
    DuplicateApprovalError,
)

# ---------------------------------------------------------------------------
# Per-store rejection
# ---------------------------------------------------------------------------


class TestInMemoryDuplicateRejection(unittest.TestCase):
    def test_in_memory_store_duplicate_approval_id_rejected(self):
        store = BrowserApprovalStore()
        store.create_approval("appr-1", "browser.execute_click", "#x", "tok-a")
        with self.assertRaises(DuplicateApprovalError):
            store.create_approval("appr-1", "browser.execute_click", "#x", "tok-b")


class TestPersistentJsonlDuplicateRejection(unittest.TestCase):
    def test_persistent_jsonl_store_duplicate_approval_id_rejected(self):
        store = PersistentBrowserApprovalStore()
        store.create_approval("appr-1", "browser.execute_click", "#x", "tok-a")
        with self.assertRaises(DuplicateApprovalError):
            store.create_approval("appr-1", "browser.execute_click", "#x", "tok-b")

    def test_jsonl_duplicate_rejection_after_reload(self):
        """Even after reload (replay), duplicate must be rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "store.jsonl"
            store1 = PersistentBrowserApprovalStore(store_path=path)
            store1.create_approval("appr-r", "browser.execute_click", "#x", "tok-a")

            store2 = PersistentBrowserApprovalStore(store_path=path)
            with self.assertRaises(DuplicateApprovalError):
                store2.create_approval("appr-r", "browser.execute_click", "#x", "tok-b")


class TestDbStoreDuplicateRejection(unittest.TestCase):
    def test_db_store_duplicate_approval_id_rejected(self):
        store = SQLiteBrowserApprovalStore()
        store.create_approval("appr-1", "browser.execute_click", "#x", "tok-a")
        with self.assertRaises(DuplicateApprovalError):
            store.create_approval("appr-1", "browser.execute_click", "#x", "tok-b")

    def test_db_duplicate_rejection_after_persist(self):
        """Duplicate rejected even when DB is reopened."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "approvals.db"
            s1 = SQLiteBrowserApprovalStore(db_path=db)
            s1.create_approval("appr-p", "browser.execute_click", "#x", "tok-a")
            s1.close()
            s2 = SQLiteBrowserApprovalStore(db_path=db)
            try:
                with self.assertRaises(DuplicateApprovalError):
                    s2.create_approval("appr-p", "browser.execute_click", "#x", "tok-b")
            finally:
                s2.close()


# ---------------------------------------------------------------------------
# State preservation on duplicate rejection
# ---------------------------------------------------------------------------


class TestStatePreservation(unittest.TestCase):
    """Existing record state must NEVER be overwritten by duplicate attempt."""

    def _all_stores(self):
        return [
            ("in_memory", BrowserApprovalStore()),
            ("jsonl", PersistentBrowserApprovalStore()),
            ("sqlite", SQLiteBrowserApprovalStore()),
        ]

    def test_duplicate_does_not_overwrite_token_hash(self):
        for label, store in self._all_stores():
            with self.subTest(store=label):
                store.create_approval("appr-th", "browser.execute_click", "#x", "first-token")
                original = store.get("appr-th")
                original_hash = original.token_hash

                with self.assertRaises(DuplicateApprovalError):
                    store.create_approval("appr-th", "browser.execute_click", "#x", "second-token")

                after = store.get("appr-th")
                self.assertEqual(
                    after.token_hash, original_hash, f"{label}: token_hash was overwritten on duplicate attempt"
                )

    def test_duplicate_does_not_reset_used_status(self):
        for label, store in self._all_stores():
            with self.subTest(store=label):
                store.create_approval("appr-u", "browser.execute_click", "#x", "tok")
                store.mark_used("appr-u")
                self.assertEqual(store.get("appr-u").status, "used")

                with self.assertRaises(DuplicateApprovalError):
                    store.create_approval("appr-u", "browser.execute_click", "#x", "tok2")

                after = store.get("appr-u")
                self.assertEqual(after.status, "used", f"{label}: 'used' status was reset by duplicate attempt")

    def test_duplicate_does_not_reset_revoked_status(self):
        for label, store in self._all_stores():
            with self.subTest(store=label):
                store.create_approval("appr-rv", "browser.execute_click", "#x", "tok")
                store.revoke("appr-rv")
                self.assertEqual(store.get("appr-rv").status, "revoked")

                with self.assertRaises(DuplicateApprovalError):
                    store.create_approval("appr-rv", "browser.execute_click", "#x", "tok2")

                after = store.get("appr-rv")
                self.assertEqual(after.status, "revoked", f"{label}: 'revoked' status was reset")

    def test_duplicate_does_not_overwrite_action_type_or_selector(self):
        """Action/selector mismatch must also not slip through duplicate path."""
        for label, store in self._all_stores():
            with self.subTest(store=label):
                store.create_approval("appr-as", "browser.execute_click", "#orig", "tok")

                with self.assertRaises(DuplicateApprovalError):
                    store.create_approval("appr-as", "browser.execute_type", "#new", "tok")

                after = store.get("appr-as")
                self.assertEqual(after.action_type, "browser.execute_click")
                self.assertEqual(after.selector, "#orig")


# ---------------------------------------------------------------------------
# Cross-store consistency
# ---------------------------------------------------------------------------


class TestCrossStoreConsistency(unittest.TestCase):
    def test_duplicate_policy_consistent_across_all_stores(self):
        """All 3 stores raise the same exception type with the same message contract."""
        for store in [
            BrowserApprovalStore(),
            PersistentBrowserApprovalStore(),
            SQLiteBrowserApprovalStore(),
        ]:
            store.create_approval("dupe-id", "browser.execute_click", "#x", "tok")
            with self.assertRaises(DuplicateApprovalError) as ctx:
                store.create_approval("dupe-id", "browser.execute_click", "#x", "tok")
            self.assertIn("dupe-id", str(ctx.exception))


# ---------------------------------------------------------------------------
# Verifier and task handler behave correctly under new policy
# ---------------------------------------------------------------------------


class TestVerifierStillWorks(unittest.TestCase):
    def test_verifier_still_accepts_valid_unique_approval(self):
        """New unique approvals still verify normally with each store."""
        for store_cls in [BrowserApprovalStore, PersistentBrowserApprovalStore, SQLiteBrowserApprovalStore]:
            with self.subTest(store=store_cls.__name__):
                store = store_cls()
                verifier = BrowserApprovalVerifier(store)
                store.create_approval("appr-v", "browser.execute_click", "#go", "tok")
                result = verifier.verify("appr-v", "tok", "browser.execute_click", "#go")
                self.assertTrue(result.valid, f"{store_cls.__name__}: valid approval rejected")

    def test_task_handler_still_works_after_duplicate_policy(self):
        """BrowserTaskHandler still validates correctly with each store."""
        import asyncio
        from unittest.mock import MagicMock

        from core.agent_runtime.browser.browser_task_handler import (
            BrowserTaskHandler,
            BrowserTaskPayload,
        )
        from core.agent_runtime.browser.server_action_adapter import ServerActionAdapter

        for store_cls in [BrowserApprovalStore, PersistentBrowserApprovalStore, SQLiteBrowserApprovalStore]:
            with self.subTest(store=store_cls.__name__):
                store = store_cls()
                store.create_approval("appr-th", "browser.execute_click", "#confirm", "task-tok")
                verifier = BrowserApprovalVerifier(store)
                adapter = MagicMock(spec=ServerActionAdapter)
                adapter.execute_action = MagicMock(
                    return_value=MagicMock(
                        executed=True,
                        element_found=True,
                        error_code=None,
                        error_message=None,
                    )
                )
                handler = BrowserTaskHandler(
                    server_action_adapter=adapter,
                    approval_verifier=verifier,
                )
                payload = BrowserTaskPayload(
                    task_id="t1",
                    action_type="browser.execute_click",
                    selector="#confirm",
                    approval_id="appr-th",
                    approval_token="task-tok",
                )
                result = asyncio.run(handler.handle_task(payload))
                self.assertNotEqual(
                    result.status, "blocked", f"{store_cls.__name__}: blocked unexpectedly: {result.error_code}"
                )


# ---------------------------------------------------------------------------
# Security invariant: no raw token stored even on duplicate attempt
# ---------------------------------------------------------------------------


class TestNoRawTokenAfterDuplicate(unittest.TestCase):
    def test_no_raw_token_stored_after_duplicate_rejection(self):
        """Failed duplicate must not leak the rejected raw token anywhere."""
        for label, store in [
            ("in_memory", BrowserApprovalStore()),
            ("jsonl", PersistentBrowserApprovalStore()),
            ("sqlite", SQLiteBrowserApprovalStore()),
        ]:
            with self.subTest(store=label):
                store.create_approval("appr-leak", "browser.execute_click", "#x", "first-token-XYZ")
                rejected_token = "second-token-ABC"
                with contextlib.suppress(DuplicateApprovalError):
                    store.create_approval("appr-leak", "browser.execute_click", "#x", rejected_token)

                # The stored record must still have the FIRST token's hash
                rec = store.get("appr-leak")
                import hashlib

                first_hash = hashlib.sha256(b"first-token-XYZ").hexdigest()
                second_hash = hashlib.sha256(rejected_token.encode()).hexdigest()
                self.assertEqual(rec.token_hash, first_hash)
                self.assertNotEqual(rec.token_hash, second_hash)


if __name__ == "__main__":
    unittest.main()


class DuplicateApprovalErrorLocationTests(unittest.TestCase):
    """층간 위반 정리(L7 저장소가 L2 검증기를 가져오던 구조): 예외는 작은 L1 모듈에 있고 검증기가 재노출한다."""

    def test_verifier_reexports_the_same_class(self) -> None:
        from core.agent_runtime.browser.approval import browser_approval_errors, browser_approval_verifier

        self.assertIs(browser_approval_verifier.DuplicateApprovalError, browser_approval_errors.DuplicateApprovalError)
        self.assertTrue(issubclass(browser_approval_errors.DuplicateApprovalError, ValueError))

    def test_stores_do_not_import_the_verifier_module(self) -> None:
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[2] / "core" / "agent_runtime" / "browser" / "approval"
        for name in ("browser_approval_db_store.py", "browser_approval_persistent_store.py"):
            text = (root / name).read_text(encoding="utf-8")
            self.assertNotIn("browser_approval_verifier", text, f"{name} 가 검증기를 import 한다")

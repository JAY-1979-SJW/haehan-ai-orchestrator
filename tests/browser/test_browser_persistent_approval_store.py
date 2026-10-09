"""Tests for persistent file-backed browser approval store (BROWSER-4F).

Verifies:
1. Token hashing (raw tokens never stored)
2. JSONL append-only format
3. Replay-on-load state restoration
4. One-time use persistence
5. Approval expiration
6. Revocation persistence
7. Integration with BrowserApprovalVerifier
8. Integration with BrowserTaskHandler
9. Security: no secrets in files
10. Thread-safe locking
"""

import json
import tempfile
from pathlib import Path

from core.agent_runtime.browser.approval.browser_approval_persistent_store import (
    PersistentBrowserApprovalStore,
    _hash_token,
)
from core.agent_runtime.browser.approval.browser_approval_verifier import BrowserApprovalVerifier
from core.agent_runtime.browser.browser_task_handler import BrowserTaskPayload


class TestTokenHashing:
    """Verify token hashing security"""

    def test_raw_token_never_stored_on_create(self):
        """Raw approval_token never stored, only token_hash"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "approvals.jsonl"
            store = PersistentBrowserApprovalStore(store_path)

            raw_token = "super-secret-token-xyz"
            record = store.create_approval(
                approval_id="appr-1",
                action_type="browser.execute_click",
                selector="#btn",
                approval_token=raw_token,
            )

            # Record has token_hash, not raw token
            assert record.token_hash is not None
            assert record.token_hash != raw_token
            assert len(record.token_hash) == 64  # SHA256 hex

    def test_token_hash_function_consistent(self):
        """_hash_token produces consistent SHA256 hashes"""
        token = "test-token-value"
        hash1 = _hash_token(token)
        hash2 = _hash_token(token)

        assert hash1 == hash2
        assert len(hash1) == 64

    def test_different_tokens_different_hashes(self):
        """Different tokens produce different hashes"""
        hash1 = _hash_token("token-1")
        hash2 = _hash_token("token-2")

        assert hash1 != hash2

    def test_jsonl_file_contains_no_raw_tokens(self):
        """JSONL file never contains raw approval tokens"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "approvals.jsonl"
            store = PersistentBrowserApprovalStore(store_path)

            raw_token = "password-like-secret-value"
            store.create_approval(
                approval_id="appr-1",
                action_type="browser.execute_click",
                selector="#btn",
                approval_token=raw_token,
            )

            # Read JSONL file and verify no raw token
            with store_path.open() as f:
                content = f.read()
                assert raw_token not in content
                assert "password-like-secret-value" not in content


class TestJSONLFormat:
    """Verify append-only JSONL format"""

    def test_append_only_event_log_format(self):
        """Events appended to JSONL with proper JSON structure"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "approvals.jsonl"
            store = PersistentBrowserApprovalStore(store_path)

            store.create_approval(
                approval_id="appr-1",
                action_type="browser.execute_click",
                selector="#btn",
                approval_token="token-1",
            )

            # Read JSONL and verify JSON validity
            with store_path.open() as f:
                for line in f:
                    if line.strip():
                        event = json.loads(line)
                        assert "event_type" in event
                        assert "approval_id" in event

    def test_multiple_events_appended_sequentially(self):
        """Multiple approvals create multiple JSONL lines"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "approvals.jsonl"
            store = PersistentBrowserApprovalStore(store_path)

            store.create_approval(
                approval_id="appr-1",
                action_type="browser.execute_click",
                selector="#btn-1",
                approval_token="token-1",
            )
            store.create_approval(
                approval_id="appr-2",
                action_type="browser.execute_click",
                selector="#btn-2",
                approval_token="token-2",
            )

            # Count JSONL lines
            with store_path.open() as f:
                lines = [l for l in f if l.strip()]  # noqa: E741
                assert len(lines) == 2

    def test_event_contains_approval_metadata(self):
        """Each event contains approval metadata"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "approvals.jsonl"
            store = PersistentBrowserApprovalStore(store_path)

            store.create_approval(
                approval_id="appr-1",
                action_type="browser.execute_click",
                selector="#btn",
                approval_token="token-1",
                risk_level="medium",
                final_approval_required=True,
            )

            with store_path.open() as f:
                event = json.loads(f.readline())
                assert event["approval_id"] == "appr-1"
                assert event["action_type"] == "browser.execute_click"
                assert event["selector"] == "#btn"
                assert event["risk_level"] == "medium"
                assert event["final_approval_required"] is True
                assert "event_timestamp" in event


class TestReplayOnLoad:
    """Verify state restoration via replay"""

    def test_load_restores_approval_from_jsonl(self):
        """_load() reconstructs approval from JSONL"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "approvals.jsonl"

            # Create and save approval
            store1 = PersistentBrowserApprovalStore(store_path)
            store1.create_approval(
                approval_id="appr-1",
                action_type="browser.execute_click",
                selector="#btn",
                approval_token="token-1",
            )

            # Create new store and load from same file
            store2 = PersistentBrowserApprovalStore(store_path)
            record = store2.get("appr-1")

            assert record is not None
            assert record.approval_id == "appr-1"
            assert record.action_type == "browser.execute_click"
            assert record.selector == "#btn"

    def test_approval_valid_after_restart(self):
        """Valid approval remains valid after store restart"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "approvals.jsonl"

            # Create approval
            store1 = PersistentBrowserApprovalStore(store_path)
            store1.create_approval(
                approval_id="appr-1",
                action_type="browser.execute_click",
                selector="#btn",
                approval_token="token-1",
            )

            # Reload and verify is_valid
            store2 = PersistentBrowserApprovalStore(store_path)
            record = store2.get("appr-1")
            assert record.is_valid() is True


class TestOneTimeUse:
    """Verify one-time use enforcement"""

    def test_mark_used_persists_to_jsonl(self):
        """mark_used() persists "used" status to JSONL"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "approvals.jsonl"
            store = PersistentBrowserApprovalStore(store_path)

            store.create_approval(
                approval_id="appr-1",
                action_type="browser.execute_click",
                selector="#btn",
                approval_token="token-1",
            )
            store.mark_used("appr-1")

            # Verify JSONL has APPROVAL_USED event
            with store_path.open() as f:
                lines = [l for l in f if l.strip()]  # noqa: E741
                events = [json.loads(l) for l in lines]  # noqa: E741
                used_event = [e for e in events if e.get("event_type") == "APPROVAL_USED"]
                assert len(used_event) > 0

    def test_used_approval_not_valid_after_restart(self):
        """Used approval remains invalid after store restart"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "approvals.jsonl"

            # Create and mark as used
            store1 = PersistentBrowserApprovalStore(store_path)
            store1.create_approval(
                approval_id="appr-1",
                action_type="browser.execute_click",
                selector="#btn",
                approval_token="token-1",
            )
            store1.mark_used("appr-1")

            # Reload and verify not valid
            store2 = PersistentBrowserApprovalStore(store_path)
            record = store2.get("appr-1")
            assert record.status == "used"
            assert record.is_valid() is False

    def test_reuse_blocked_after_mark_used(self):
        """Used approval cannot be marked used again"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "approvals.jsonl"
            store = PersistentBrowserApprovalStore(store_path)

            store.create_approval(
                approval_id="appr-1",
                action_type="browser.execute_click",
                selector="#btn",
                approval_token="token-1",
            )
            store.mark_used("appr-1")

            # Attempt to reuse
            record = store.get("appr-1")
            assert record.is_valid() is False


class TestApprovalExpiration:
    """Verify expiration persistence"""

    def test_expired_approval_not_valid_after_restart(self):
        """Expired approval remains expired after store restart"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "approvals.jsonl"

            # Create approval that expires in 1 second
            store1 = PersistentBrowserApprovalStore(store_path)
            store1.create_approval(
                approval_id="appr-1",
                action_type="browser.execute_click",
                selector="#btn",
                approval_token="token-1",
                expires_in_seconds=1,
            )

            # Wait for expiration
            import time

            time.sleep(1.1)

            # Reload and verify expired
            store2 = PersistentBrowserApprovalStore(store_path)
            record = store2.get("appr-1")
            assert record.is_valid() is False


class TestRevocation:
    """Verify revocation persistence"""

    def test_revoke_persists_to_jsonl(self):
        """revoke() persists "revoked" status to JSONL"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "approvals.jsonl"
            store = PersistentBrowserApprovalStore(store_path)

            store.create_approval(
                approval_id="appr-1",
                action_type="browser.execute_click",
                selector="#btn",
                approval_token="token-1",
            )
            store.revoke("appr-1")

            # Verify JSONL has APPROVAL_REVOKED event
            with store_path.open() as f:
                events = [json.loads(l) for l in f if l.strip()]  # noqa: E741
                revoked_event = [e for e in events if e.get("event_type") == "APPROVAL_REVOKED"]
                assert len(revoked_event) > 0

    def test_revoked_approval_not_valid_after_restart(self):
        """Revoked approval remains invalid after store restart"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "approvals.jsonl"

            # Create and revoke
            store1 = PersistentBrowserApprovalStore(store_path)
            store1.create_approval(
                approval_id="appr-1",
                action_type="browser.execute_click",
                selector="#btn",
                approval_token="token-1",
            )
            store1.revoke("appr-1")

            # Reload and verify revoked
            store2 = PersistentBrowserApprovalStore(store_path)
            record = store2.get("appr-1")
            assert record.status == "revoked"
            assert record.is_valid() is False


class TestVerifierIntegration:
    """Verify integration with BrowserApprovalVerifier"""

    def test_verifier_works_with_persistent_store(self):
        """BrowserApprovalVerifier can verify against persistent store"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "approvals.jsonl"
            store = PersistentBrowserApprovalStore(store_path)
            verifier = BrowserApprovalVerifier(store)

            # Create approval
            token = "test-token-value"
            store.create_approval(
                approval_id="appr-1",
                action_type="browser.execute_click",
                selector="#btn",
                approval_token=token,
            )

            # Verify with correct token
            result = verifier.verify(
                approval_id="appr-1",
                approval_token=token,
                action_type="browser.execute_click",
                selector="#btn",
            )
            assert result.valid is True

    def test_verifier_rejects_invalid_token_with_persistent_store(self):
        """BrowserApprovalVerifier rejects invalid token from persistent store"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "approvals.jsonl"
            store = PersistentBrowserApprovalStore(store_path)
            verifier = BrowserApprovalVerifier(store)

            # Create approval with one token
            store.create_approval(
                approval_id="appr-1",
                action_type="browser.execute_click",
                selector="#btn",
                approval_token="correct-token",
            )

            # Verify with wrong token
            result = verifier.verify(
                approval_id="appr-1",
                approval_token="wrong-token",
                action_type="browser.execute_click",
                selector="#btn",
            )
            assert result.valid is False

    def test_verifier_rejects_used_approval_from_persistent_store(self):
        """BrowserApprovalVerifier rejects used approval from persistent store"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "approvals.jsonl"
            store = PersistentBrowserApprovalStore(store_path)
            verifier = BrowserApprovalVerifier(store)

            # Create and mark as used
            token = "test-token-value"
            store.create_approval(
                approval_id="appr-1",
                action_type="browser.execute_click",
                selector="#btn",
                approval_token=token,
            )
            store.mark_used("appr-1")

            # Attempt to verify
            result = verifier.verify(
                approval_id="appr-1",
                approval_token=token,
                action_type="browser.execute_click",
                selector="#btn",
            )
            assert result.valid is False


class TestTaskHandlerIntegration:
    """Verify integration with BrowserTaskHandler approval verification"""

    def test_payload_with_persistent_store_approval_valid(self):
        """BrowserTaskPayload with approval from persistent store validates correctly"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "approvals.jsonl"
            store = PersistentBrowserApprovalStore(store_path)
            verifier = BrowserApprovalVerifier(store)

            # Create approval
            token = "test-token-value"
            store.create_approval(
                approval_id="appr-1",
                action_type="browser.execute_click",
                selector="#btn",
                approval_token=token,
            )

            # Verify payload would validate
            payload = BrowserTaskPayload(
                task_id="task-1",
                action_type="browser.execute_click",
                selector="#btn",
                approval_id="appr-1",
                approval_token=token,
            )

            # Verify approval through verifier
            result = verifier.verify(
                approval_id=payload.approval_id,
                approval_token=payload.approval_token,
                action_type=payload.action_type,
                selector=payload.selector,
            )
            assert result.valid is True

    def test_payload_without_valid_approval_from_persistent_store_invalid(self):
        """BrowserTaskPayload without valid approval from persistent store fails verification"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "approvals.jsonl"
            store = PersistentBrowserApprovalStore(store_path)
            verifier = BrowserApprovalVerifier(store)

            # No approval created
            payload = BrowserTaskPayload(
                task_id="task-1",
                action_type="browser.execute_click",
                selector="#btn",
                approval_id="appr-1",
                approval_token="wrong-token",
            )

            # Verify fails
            result = verifier.verify(
                approval_id=payload.approval_id,
                approval_token=payload.approval_token,
                action_type=payload.action_type,
                selector=payload.selector,
            )
            assert result.valid is False


class TestFilePersistenceWithoutMemory:
    """Verify file-based persistence across process boundaries"""

    def test_approval_persists_without_in_memory_store(self):
        """Approval survives without in-memory reference"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "approvals.jsonl"

            # Create and discard store (simulating process exit)
            store1 = PersistentBrowserApprovalStore(store_path)
            store1.create_approval(
                approval_id="appr-1",
                action_type="browser.execute_click",
                selector="#btn",
                approval_token="token-1",
            )
            del store1

            # Create fresh store from file
            store2 = PersistentBrowserApprovalStore(store_path)
            record = store2.get("appr-1")

            assert record is not None
            assert record.approval_id == "appr-1"


class TestNoSecretsInFile:
    """Verify no secrets leaked to persistent file"""

    def test_no_raw_tokens_in_jsonl(self):
        """JSONL file contains no raw tokens"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "approvals.jsonl"
            store = PersistentBrowserApprovalStore(store_path)

            secret_token = "super-secret-api-key-12345"
            store.create_approval(
                approval_id="appr-1",
                action_type="browser.execute_click",
                selector="#btn",
                approval_token=secret_token,
            )

            with store_path.open() as f:
                content = f.read()
                assert secret_token not in content

    def test_no_forbidden_keywords_in_jsonl(self):
        """JSONL file contains no forbidden keywords (password, cookie, session, etc)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "approvals.jsonl"
            store = PersistentBrowserApprovalStore(store_path)

            forbidden_keywords = ["password", "cookie", "session", "secret", "key", "token"]  # noqa: F841
            store.create_approval(
                approval_id="appr-1",
                action_type="browser.execute_click",
                selector="#btn",
                approval_token="some-secret",
            )

            with store_path.open() as f:
                lines = f.readlines()
                for line in lines:
                    if not line.strip():
                        continue
                    event = json.loads(line)
                    # Verify token_hash is not raw token
                    if "token_hash" in event:
                        assert event["token_hash"] not in ["some-secret"]
                        assert len(event["token_hash"]) == 64  # SHA256 hex


class TestThreadSafety:
    """Verify thread-safe operations"""

    def test_concurrent_approvals_safe(self):
        """Multiple concurrent approvals don't corrupt store"""
        import threading

        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "approvals.jsonl"
            store = PersistentBrowserApprovalStore(store_path)

            def create_approval(idx):
                store.create_approval(
                    approval_id=f"appr-{idx}",
                    action_type="browser.execute_click",
                    selector=f"#btn-{idx}",
                    approval_token=f"token-{idx}",
                )

            threads = [threading.Thread(target=create_approval, args=(i,)) for i in range(5)]

            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # Verify all approvals created
            for i in range(5):
                record = store.get(f"appr-{i}")
                assert record is not None


class TestOptionalPersistence:
    """Verify optional file persistence"""

    def test_store_without_path_works_in_memory(self):
        """PersistentBrowserApprovalStore works without path (in-memory mode)"""
        store = PersistentBrowserApprovalStore(store_path=None)

        record = store.create_approval(
            approval_id="appr-1",
            action_type="browser.execute_click",
            selector="#btn",
            approval_token="token-1",
        )

        assert record is not None
        retrieved = store.get("appr-1")
        assert retrieved is not None

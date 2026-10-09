"""Persistent file-backed browser approval store (BROWSER-4F).

This module extends the in-memory BrowserApprovalStore with file-based persistence.

Design principles:
1. Raw approval_token never stored (token_hash only)
2. JSONL append-only format for audit trail
3. Replay on load to restore state
4. One-time use, revoked, and expired states persisted
5. No secrets in files (token, password, cookie, session, etc.)
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class BrowserApprovalRecord:
    """Approval record (same as in-memory version)."""

    approval_id: str
    action_type: str
    selector: str
    token_hash: str
    status: str = "approved"  # approved, used, revoked, expired
    risk_level: str = "low"
    final_approval_required: bool = False
    expires_at: datetime | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def is_valid(self) -> bool:
        """Check if approval is in valid state for use."""
        if self.status != "approved":
            return False
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        return True


def _hash_token(token: str) -> str:
    """Hash approval token using SHA256."""
    return hashlib.sha256(token.encode()).hexdigest()


def _now_iso() -> str:
    """Get current timestamp in ISO format."""
    return datetime.utcnow().isoformat()


class PersistentBrowserApprovalStore:
    """File-backed approval store with append-only event log.

    Stores approvals in JSONL format for audit trail and persistence.
    Replays events on load to restore state.
    """

    def __init__(self, store_path: Path | None = None):
        """Initialize persistent store.

        Args:
            store_path: Path to JSONL log file. If None, uses temp/in-memory mode.
        """
        self.store_path = store_path
        self._records: dict[str, BrowserApprovalRecord] = {}
        self._lock = threading.Lock()

        if self.store_path:
            self._load()

    def _load(self) -> None:
        """Replay JSONL log to restore state."""
        if not self.store_path or not self.store_path.exists():
            return

        try:
            with self.store_path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning("Failed to parse event: %s", line)
                        continue

                    # Replay event
                    approval_id = event.get("approval_id")
                    if not approval_id:
                        continue

                    # Extract record fields (event_timestamp and event_type are metadata)
                    rec = {
                        "approval_id": approval_id,
                        "action_type": event.get("action_type", ""),
                        "selector": event.get("selector", ""),
                        "token_hash": event.get("token_hash", ""),
                        "status": event.get("status", "approved"),
                        "risk_level": event.get("risk_level", "low"),
                        "final_approval_required": event.get("final_approval_required", False),
                        "expires_at": None,
                        "created_at": datetime.utcnow(),
                    }

                    # Parse dates
                    if event.get("expires_at"):
                        with contextlib.suppress(ValueError, TypeError):
                            rec["expires_at"] = datetime.fromisoformat(event.get("expires_at"))

                    if event.get("created_at"):
                        with contextlib.suppress(ValueError, TypeError):
                            rec["created_at"] = datetime.fromisoformat(event.get("created_at"))

                    # Create record
                    self._records[approval_id] = BrowserApprovalRecord(**rec)
        except Exception as e:  # noqa: BLE001 - 브라우저 승인 영구 저장소 -- 저장소 로드 실패 시 빈 레코드로 초기화(존재하지 않는 승인은 이후 로직에서 미승인으로 처리되어 fail-closed), 이벤트 append 실패는 로깅만
            logger.error("Failed to load approval store: %s", e)
            self._records = {}

    def _append_event(self, event_type: str, approval_id: str, record: BrowserApprovalRecord) -> None:
        """Append event to log file."""
        if not self.store_path:
            return

        try:
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            event = {
                "event_timestamp": _now_iso(),
                "event_type": event_type,
                "approval_id": approval_id,
                "action_type": record.action_type,
                "selector": record.selector,
                "token_hash": record.token_hash,
                "status": record.status,
                "risk_level": record.risk_level,
                "final_approval_required": record.final_approval_required,
                "created_at": record.created_at.isoformat() if record.created_at else "",
                "expires_at": record.expires_at.isoformat() if record.expires_at else "",
            }
            with self.store_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception as e:  # noqa: BLE001 - 브라우저 승인 영구 저장소 -- 저장소 로드 실패 시 빈 레코드로 초기화(존재하지 않는 승인은 이후 로직에서 미승인으로 처리되어 fail-closed), 이벤트 append 실패는 로깅만
            logger.error("Failed to append approval event: %s", e)

    def create_approval(  # noqa: PLR0913 - 공개 API 시그니처 유지(저장소 3종 공통 인터페이스)
        self,
        approval_id: str,
        action_type: str,
        selector: str,
        approval_token: str,
        risk_level: str = "low",
        final_approval_required: bool = False,
        expires_in_seconds: int | None = None,
    ) -> BrowserApprovalRecord:
        """Create approval record (token_hash stored, not raw token).

        Raises:
            DuplicateApprovalError: If approval_id already exists.
                Existing record is never overwritten — token_hash and status preserved.
        """
        # Import here to avoid circular import at module load
        from core.agent_runtime.browser.approval.browser_approval_errors import DuplicateApprovalError

        token_hash = _hash_token(approval_token)

        expires_at = None
        if expires_in_seconds:
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in_seconds)

        record = BrowserApprovalRecord(
            approval_id=approval_id,
            action_type=action_type,
            selector=selector,
            token_hash=token_hash,
            status="approved",
            risk_level=risk_level,
            final_approval_required=final_approval_required,
            expires_at=expires_at,
            created_at=datetime.utcnow(),
        )

        with self._lock:
            if approval_id in self._records:
                raise DuplicateApprovalError(f"approval_id already exists: {approval_id}")
            self._records[approval_id] = record
            self._append_event("APPROVAL_CREATED", approval_id, record)

        logger.info(f"Approval created: {approval_id}")
        return record

    def get(self, approval_id: str) -> BrowserApprovalRecord | None:
        """Retrieve approval record by ID."""
        with self._lock:
            return self._records.get(approval_id)

    def mark_used(self, approval_id: str) -> bool:
        """Mark approval as used (one-time use)."""
        with self._lock:
            record = self._records.get(approval_id)
            if not record:
                return False
            record.status = "used"
            self._append_event("APPROVAL_USED", approval_id, record)
            logger.info(f"Approval marked used: {approval_id}")
            return True

    def revoke(self, approval_id: str) -> bool:
        """Revoke approval."""
        with self._lock:
            record = self._records.get(approval_id)
            if not record:
                return False
            record.status = "revoked"
            self._append_event("APPROVAL_REVOKED", approval_id, record)
            logger.info(f"Approval revoked: {approval_id}")
            return True

    def clear(self) -> None:
        """Clear all records (for testing)."""
        with self._lock:
            self._records.clear()


# Alias for compatibility with existing code
FileBackedBrowserApprovalStore = PersistentBrowserApprovalStore

"""Server-side approval token verification for browser actions.

This module implements approval token validation with:
- In-memory approval store (PoC)
- Token hash verification (raw tokens not stored)
- Approval status tracking (pending/approved/used/revoked/expired)
- One-time use enforcement
- Action/selector matching
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from core.agent_runtime.browser.approval.browser_approval_errors import DuplicateApprovalError

logger = logging.getLogger(__name__)


@dataclass
class BrowserApprovalRecord:
    """Server-side approval record (in-memory).

    Attributes:
        approval_id: Unique approval identifier
        action_type: Action type being approved
        selector: CSS selector being approved
        token_hash: SHA256 hash of approval token (raw token never stored)
        status: One of [approved, used, revoked, expired]
        risk_level: Risk level of the action
        final_approval_required: Whether final approval is needed
        expires_at: Optional expiration time (None = no expiration in PoC)
        created_at: Creation timestamp
    """

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


@dataclass
class ApprovalVerificationResult:
    """Result of approval verification.

    Attributes:
        valid: Whether approval is valid
        error_code: Error code if invalid (approval_not_found, invalid_token, etc.)
        error_message: Human-readable error message
        record: Approval record if found
    """

    valid: bool
    error_code: str | None = None
    error_message: str | None = None
    record: BrowserApprovalRecord | None = None


class BrowserApprovalStore:
    """In-memory approval store for PoC.

    Stores approval records by approval_id (not by token).
    Raw tokens are never stored, only token_hash for verification.
    """

    def __init__(self):
        """Initialize approval store."""
        self._records: dict[str, BrowserApprovalRecord] = {}

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

        Args:
            approval_id: Unique approval ID
            action_type: Action type being approved
            selector: CSS selector being approved
            approval_token: Raw token (used only to compute hash)
            risk_level: Risk level of action
            final_approval_required: Whether final approval needed
            expires_in_seconds: Expiration time (None = no expiration)

        Returns:
            BrowserApprovalRecord
        """
        # Reject duplicate approval_id — never overwrite existing record
        if approval_id in self._records:
            raise DuplicateApprovalError(f"approval_id already exists: {approval_id}")

        # Compute hash and discard raw token
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
        )

        self._records[approval_id] = record
        logger.info(f"Approval created: {approval_id}")
        return record

    def get(self, approval_id: str) -> BrowserApprovalRecord | None:
        """Retrieve approval record by ID."""
        return self._records.get(approval_id)

    def _set_status(self, approval_id: str, status: str, log_label: str) -> bool:
        """approval 상태를 바꾼다(mark_used/revoke 공통). 없으면 False."""
        record = self._records.get(approval_id)
        if not record:
            return False
        record.status = status
        logger.info(f"Approval {log_label}: {approval_id}")
        return True

    def mark_used(self, approval_id: str) -> bool:
        """Mark approval as used (one-time use).

        Args:
            approval_id: Approval ID to mark

        Returns:
            True if marked, False if not found
        """
        return self._set_status(approval_id, "used", "marked used")

    def revoke(self, approval_id: str) -> bool:
        """Revoke approval.

        Args:
            approval_id: Approval ID to revoke

        Returns:
            True if revoked, False if not found
        """
        return self._set_status(approval_id, "revoked", "revoked")

    def clear(self) -> None:
        """Clear all records (for testing)."""
        self._records.clear()


class BrowserApprovalVerifier:
    """Verifies approval tokens for browser actions.

    Validates approval_id and approval_token against stored approval records.
    Raw tokens are never stored or logged.
    """

    def __init__(self, approval_store: BrowserApprovalStore):
        """Initialize verifier with approval store.

        Args:
            approval_store: BrowserApprovalStore instance
        """
        self.store = approval_store

    @staticmethod
    def _status_error(record: BrowserApprovalRecord) -> ApprovalVerificationResult | None:
        """record.status 검사 (used/revoked/그 외 비-approved 거절)."""
        if record.status == "used":
            return ApprovalVerificationResult(
                valid=False,
                error_code="approval_used",
                error_message="Approval has already been used",
                record=record,
            )
        elif record.status == "revoked":
            return ApprovalVerificationResult(
                valid=False,
                error_code="approval_revoked",
                error_message="Approval has been revoked",
                record=record,
            )
        elif record.status != "approved":
            return ApprovalVerificationResult(
                valid=False,
                error_code="approval_invalid",
                error_message=f"Approval status is {record.status}",
                record=record,
            )
        return None

    def verify(
        self,
        approval_id: str | None,
        approval_token: str | None,
        action_type: str,
        selector: str,
    ) -> ApprovalVerificationResult:
        """Verify approval_id and approval_token.

        Args:
            approval_id: Approval ID from action
            approval_token: Raw approval token from action
            action_type: Action type to verify
            selector: Selector to verify

        Returns:
            ApprovalVerificationResult
        """
        # Check required fields
        if not approval_id:
            return ApprovalVerificationResult(
                valid=False,
                error_code="missing_approval_id",
                error_message="approval_id is required",
            )

        if not approval_token:
            return ApprovalVerificationResult(
                valid=False,
                error_code="missing_approval_token",
                error_message="approval_token is required",
            )

        # Look up approval record
        record = self.store.get(approval_id)
        if not record:
            return ApprovalVerificationResult(
                valid=False,
                error_code="approval_not_found",
                error_message=f"Approval {approval_id} not found",
            )

        # Check status first
        status_err = self._status_error(record)
        if status_err is not None:
            return status_err

        # Check expiration
        if record.expires_at and datetime.utcnow() > record.expires_at:
            return ApprovalVerificationResult(
                valid=False,
                error_code="approval_expired",
                error_message="Approval has expired",
                record=record,
            )

        # Verify token hash
        token_hash = _hash_token(approval_token)
        if token_hash != record.token_hash:
            return ApprovalVerificationResult(
                valid=False,
                error_code="invalid_token",
                error_message="approval_token does not match",
                record=record,
            )

        # Verify action_type
        if action_type != record.action_type:
            return ApprovalVerificationResult(
                valid=False,
                error_code="action_type_mismatch",
                error_message=f"Expected {record.action_type}, got {action_type}",
                record=record,
            )

        # Verify selector
        if selector != record.selector:
            return ApprovalVerificationResult(
                valid=False,
                error_code="selector_mismatch",
                error_message=f"Expected {record.selector}, got {selector}",
                record=record,
            )

        # All checks passed
        return ApprovalVerificationResult(
            valid=True,
            record=record,
        )


def _hash_token(token: str) -> str:
    """Hash approval token using SHA256.

    Raw token is not stored anywhere after hashing.

    Args:
        token: Raw token string

    Returns:
        Hex digest of SHA256 hash
    """
    return hashlib.sha256(token.encode()).hexdigest()

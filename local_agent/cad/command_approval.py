# -*- coding: utf-8 -*-
"""CAD agent command approval — in-memory PoC.

CAD-AGENT-CAD-CONTROL-COMMAND-CONTRACT-01.

D5 결정: in-memory PoC, token 원문 저장 0건 (SHA256 hash 만), one-time
use 강제, DuplicateApprovalError 로 silent overwrite 방지.

browser_approval_verifier.py 패턴 따라하되, CAD 도메인 전용 store 분리.

본 트랙은 실제 실행 / DB write / 외부 호출 0건.
"""
from __future__ import annotations

import enum
import hashlib
import logging
import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Status enum (re-exported from command_contract 와 정합)
# ──────────────────────────────────────────────

class ApprovalRecordStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    USED = "USED"
    EXPIRED = "EXPIRED"


class DuplicateApprovalError(ValueError):
    """create_approval 가 동일 approval_id 로 두 번 호출되면 발생."""


class ApprovalNotFound(LookupError):
    pass


# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

_TOKEN_BYTES = 32  # 256-bit token
_DEFAULT_EXPIRY_SECONDS = 900  # 15분


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(token: str) -> str:
    """SHA256 hex digest — token 원문 저장 0건의 핵심."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _gen_token() -> str:
    """URL-safe 256-bit token. 본 모듈에서 호출자에게 1회만 반환."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


# ──────────────────────────────────────────────
# Approval record (in-memory only)
# ──────────────────────────────────────────────

@dataclass
class ApprovalRecord:
    """in-memory approval record. token 원문 저장 금지 — token_hash 만."""
    approvalId: str
    commandId: str
    toolId: str
    tokenHash: str
    status: ApprovalRecordStatus
    createdAt: datetime
    expiresAt: datetime
    approvedAt: Optional[datetime] = None
    usedAt: Optional[datetime] = None
    rejectedAt: Optional[datetime] = None

    # NOTE: token 원문 필드 없음. raw_text 없음.

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        now = now or _utcnow()
        return now >= self.expiresAt

    def snapshot(self) -> Dict[str, str]:
        return {
            "approvalId": self.approvalId,
            "commandId": self.commandId,
            "toolId": self.toolId,
            "status": self.status.value,
            "createdAt": self.createdAt.isoformat(),
            "expiresAt": self.expiresAt.isoformat(),
            "approvedAt": (
                self.approvedAt.isoformat() if self.approvedAt else None
            ),
            "usedAt": self.usedAt.isoformat() if self.usedAt else None,
            "rejectedAt": (
                self.rejectedAt.isoformat() if self.rejectedAt else None
            ),
        }


# ──────────────────────────────────────────────
# In-memory store
# ──────────────────────────────────────────────

class CadCommandApprovalStore:
    """단일 process 내 in-memory approval store. thread-safe.

    파일/DB write 0건. token 원문 0건 보존. SHA256 hash 만.
    """

    def __init__(self, expiry_seconds: int = _DEFAULT_EXPIRY_SECONDS) -> None:
        self._lock = threading.Lock()
        self._records: Dict[str, ApprovalRecord] = {}
        self._expiry_seconds = expiry_seconds

    def create_approval(
        self,
        command_id: str,
        tool_id: str,
        *,
        expiry_seconds: Optional[int] = None,
    ) -> tuple:
        """(approval_id, raw_token) 1회 반환 — raw token 은 호출자만 보유.

        store 에는 hash 만 저장. 동일 approval_id 재발급은
        DuplicateApprovalError.
        """
        if not command_id:
            raise ValueError("command_id required")
        approval_id = "appr_" + secrets.token_urlsafe(12)
        with self._lock:
            if approval_id in self._records:
                # secrets.token_urlsafe collision 은 사실상 0 — 방어적 검증
                raise DuplicateApprovalError(
                    f"duplicate approval_id: {approval_id}"
                )
            raw_token = _gen_token()
            now = _utcnow()
            exp = now + timedelta(
                seconds=expiry_seconds or self._expiry_seconds,
            )
            self._records[approval_id] = ApprovalRecord(
                approvalId=approval_id,
                commandId=command_id,
                toolId=tool_id,
                tokenHash=_hash_token(raw_token),
                status=ApprovalRecordStatus.PENDING,
                createdAt=now,
                expiresAt=exp,
            )
            logger.info(
                "cad approval created: approval_id=%s tool=%s (hash only)",
                approval_id, tool_id,
            )
            return approval_id, raw_token

    def get_record(self, approval_id: str) -> ApprovalRecord:
        with self._lock:
            r = self._records.get(approval_id)
            if r is None:
                raise ApprovalNotFound(approval_id)
            return r

    def approve(self, approval_id: str) -> ApprovalRecord:
        """관리자 승인 — token 매개변수 없음 (hash 만 보유). status: PENDING→APPROVED."""
        with self._lock:
            r = self._records.get(approval_id)
            if r is None:
                raise ApprovalNotFound(approval_id)
            if r.is_expired():
                r.status = ApprovalRecordStatus.EXPIRED
                return r
            if r.status != ApprovalRecordStatus.PENDING:
                # idempotency: 이미 APPROVED / USED / REJECTED / EXPIRED 면 그대로
                return r
            r.status = ApprovalRecordStatus.APPROVED
            r.approvedAt = _utcnow()
            return r

    def reject(self, approval_id: str) -> ApprovalRecord:
        with self._lock:
            r = self._records.get(approval_id)
            if r is None:
                raise ApprovalNotFound(approval_id)
            if r.status not in (
                ApprovalRecordStatus.PENDING, ApprovalRecordStatus.APPROVED,
            ):
                return r
            r.status = ApprovalRecordStatus.REJECTED
            r.rejectedAt = _utcnow()
            return r

    def verify(self, approval_id: str, token: str) -> bool:
        """token hash 일치 + 상태가 APPROVED + 미만료 인지 검증. consume 0."""
        with self._lock:
            r = self._records.get(approval_id)
            if r is None:
                return False
            if r.is_expired():
                r.status = ApprovalRecordStatus.EXPIRED
                return False
            if r.status != ApprovalRecordStatus.APPROVED:
                return False
            return _hash_token(token) == r.tokenHash

    def consume(self, approval_id: str, token: str) -> bool:
        """one-time use — verify 후 USED 상태로 전환. 재사용 거부."""
        with self._lock:
            r = self._records.get(approval_id)
            if r is None:
                return False
            if r.is_expired():
                r.status = ApprovalRecordStatus.EXPIRED
                return False
            if r.status != ApprovalRecordStatus.APPROVED:
                return False
            if _hash_token(token) != r.tokenHash:
                return False
            r.status = ApprovalRecordStatus.USED
            r.usedAt = _utcnow()
            return True

    def snapshot_all(self) -> Dict[str, Dict[str, str]]:
        with self._lock:
            return {k: r.snapshot() for k, r in self._records.items()}


# 기본 싱글톤 — 단일 process in-memory
DEFAULT_APPROVAL_STORE: CadCommandApprovalStore = CadCommandApprovalStore()


__all__ = [
    "ApprovalRecordStatus",
    "DuplicateApprovalError",
    "ApprovalNotFound",
    "ApprovalRecord",
    "CadCommandApprovalStore",
    "DEFAULT_APPROVAL_STORE",
]

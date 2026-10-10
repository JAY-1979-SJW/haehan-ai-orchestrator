"""DB-backed browser approval store (BROWSER-5).

SQLite PoC implementation of the approval store interface.
Designed to be a drop-in replacement for PersistentBrowserApprovalStore (JSONL).

Security invariants:
- approval_token (raw) NEVER stored in DB
- final_approval_token NEVER stored
- token_hash stored only
- typed_text, password, OTP, cookie, session NEVER stored
- All sensitive fields stripped before DB write

DB schema:
    browser_approvals table — see _CREATE_TABLE_SQL
    Indexes: approval_id (unique), status, created_at

Thread safety:
    Single shared sqlite3.Connection with threading.Lock.
    check_same_thread=False + explicit locking = safe for PoC use.

Production path:
    Replace sqlite3 connection with SQLAlchemy engine targeting PostgreSQL.
    Schema and interface are identical.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path

from core.agent_runtime.browser.approval.browser_approval_errors import DuplicateApprovalError
from core.agent_runtime.browser.approval.browser_approval_persistent_store import BrowserApprovalRecord

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS browser_approvals (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    approval_id             TEXT    NOT NULL UNIQUE,
    action_type             TEXT    NOT NULL,
    selector                TEXT    NOT NULL,
    token_hash              TEXT    NOT NULL,
    status                  TEXT    NOT NULL DEFAULT 'approved',
    risk_level              TEXT    NOT NULL DEFAULT 'low',
    final_approval_required INTEGER NOT NULL DEFAULT 0,
    created_at              TEXT    NOT NULL,
    expires_at              TEXT,
    used_at                 TEXT,
    revoked_at              TEXT,
    metadata_json           TEXT
);
"""

_CREATE_INDEXES_SQL = [
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_approval_id ON browser_approvals(approval_id);",
    "CREATE INDEX IF NOT EXISTS idx_status       ON browser_approvals(status);",
    "CREATE INDEX IF NOT EXISTS idx_created_at   ON browser_approvals(created_at);",
]

# Fields that MUST NOT appear in DB rows (defense-in-depth validation)
_FORBIDDEN_DB_COLUMNS: frozenset[str] = frozenset(
    {
        "approval_token",
        "final_approval_token",
        "raw_token",
        "typed_text",
        "password",
        "otp",
        "cookie",
        "session",
        "authorization",
        "localstorage",
        "sessionstorage",
    }
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _row_to_record(row: sqlite3.Row) -> BrowserApprovalRecord:
    return BrowserApprovalRecord(
        approval_id=row["approval_id"],
        action_type=row["action_type"],
        selector=row["selector"],
        token_hash=row["token_hash"],
        status=row["status"],
        risk_level=row["risk_level"],
        final_approval_required=bool(row["final_approval_required"]),
        expires_at=_parse_dt(row["expires_at"]),
        created_at=_parse_dt(row["created_at"]) or datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class SQLiteBrowserApprovalStore:
    """SQLite-backed approval store.

    Drop-in replacement for PersistentBrowserApprovalStore.
    Identical public interface: create_approval / get / mark_used / revoke / clear.

    Args:
        db_path: Path to SQLite file. None or ":memory:" for in-memory (tests).
    """

    def __init__(self, db_path: Path | None = None) -> None:
        path_str = str(db_path) if db_path else ":memory:"
        self._db_path = path_str
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection = sqlite3.connect(path_str, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(_CREATE_TABLE_SQL)
            for sql in _CREATE_INDEXES_SQL:
                self._conn.execute(sql)
            self._conn.commit()

    # ------------------------------------------------------------------
    # Public interface (matches BrowserApprovalStore + PersistentBrowserApprovalStore)

    def create_approval(  # noqa: PLR0913 - 공개 API 시그니처 유지(저장소 3종 공통 인터페이스)
        self,
        approval_id: str,
        action_type: str,
        selector: str,
        approval_token: str,  # raw token — hash computed and discarded
        risk_level: str = "low",
        final_approval_required: bool = False,
        expires_in_seconds: int | None = None,
    ) -> BrowserApprovalRecord:
        """Create approval record. Raw token never reaches the DB."""
        token_hash = _hash_token(approval_token)  # hash and discard
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=expires_in_seconds) if expires_in_seconds else None

        with self._lock:
            try:
                self._conn.execute(
                    """
                    INSERT INTO browser_approvals
                        (approval_id, action_type, selector, token_hash, status,
                         risk_level, final_approval_required, created_at, expires_at)
                    VALUES (?, ?, ?, ?, 'approved', ?, ?, ?, ?)
                    """,
                    (
                        approval_id,
                        action_type,
                        selector,
                        token_hash,
                        risk_level,
                        1 if final_approval_required else 0,
                        now.isoformat(),
                        expires_at.isoformat() if expires_at else None,
                    ),
                )
                self._conn.commit()
            except sqlite3.IntegrityError as exc:
                # UNIQUE constraint on approval_id — translate to common policy
                self._conn.rollback()
                raise DuplicateApprovalError(f"approval_id already exists: {approval_id}") from exc

        logger.info("db approval created: %s", approval_id)
        return BrowserApprovalRecord(
            approval_id=approval_id,
            action_type=action_type,
            selector=selector,
            token_hash=token_hash,
            status="approved",
            risk_level=risk_level,
            final_approval_required=final_approval_required,
            expires_at=expires_at,
            created_at=now,
        )

    def get(self, approval_id: str) -> BrowserApprovalRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM browser_approvals WHERE approval_id = ?",
                (approval_id,),
            ).fetchone()
        return _row_to_record(row) if row else None

    def mark_used(self, approval_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE browser_approvals SET status = 'used', used_at = ? WHERE approval_id = ?",
                (_now_iso(), approval_id),
            )
            self._conn.commit()
        if cur.rowcount > 0:
            logger.info("db approval marked used: %s", approval_id)
            return True
        return False

    def revoke(self, approval_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE browser_approvals SET status = 'revoked', revoked_at = ? WHERE approval_id = ?",
                (_now_iso(), approval_id),
            )
            self._conn.commit()
        if cur.rowcount > 0:
            logger.info("db approval revoked: %s", approval_id)
            return True
        return False

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM browser_approvals")
            self._conn.commit()

    # ------------------------------------------------------------------
    # Extra helpers (not in base interface)

    def list_pending(self) -> list[str]:
        """Return approval_ids with status='approved' (for tray status display)."""
        with self._lock:
            rows = self._conn.execute("SELECT approval_id FROM browser_approvals WHERE status = 'approved'").fetchall()
        return [r["approval_id"] for r in rows]

    def get_column_names(self) -> list[str]:
        """Return DB schema column names (for security validation in tests)."""
        with self._lock:
            rows = self._conn.execute("PRAGMA table_info(browser_approvals)").fetchall()
        return [r["name"] for r in rows]

    def close(self) -> None:
        # DB 커넥션 close() 실패 무시 - 리소스 정리 코드일 뿐, 승인 데이터는 이미 커밋된 상태라 무결성 영향 없음
        with contextlib.suppress(Exception):
            self._conn.close()


# Alias for use in production migration path
DatabaseBrowserApprovalStore = SQLiteBrowserApprovalStore

__all__ = [
    "_FORBIDDEN_DB_COLUMNS",
    "DatabaseBrowserApprovalStore",
    "SQLiteBrowserApprovalStore",
]

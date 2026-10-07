"""L7 Persistence — 메일 순차 대량 발송 승인서·발송 이력·수신거부·정지 플래그 (sqlite).

기준서: docs/specs/2026-10-02_mail_bulk_sequential.md (하나팩스 `fax_authorization_store` 와 같은 설계)
스키마 버전: `sqlite_schema.apply_schema`. 이 DB 파일은 이 모듈만 소유한다.

- **승인된 범위는 수정하지 않는다.** 수신자·제목·본문·첨부·성격을 바꾸려면 새 승인서를 만든다.
- **발송 이력은 추가만 한다**(수정·삭제 없음) — 중복 발송 방지와 감사의 근거.
- 전체 주소는 이 DB 에만 둔다. 반환·로그에는 호출자가 마스킹해서 쓴다. 비밀번호·첨부 원본은 저장하지 않는다.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ai_orchestrator.paths.runtime import storage_dir

from ai_orchestrator.persistence.sqlite_schema import apply_schema, set_busy_timeout

_DB_PATH = storage_dir() / "mail_bulk.db"

# 발송 이력 상태
SENT = "sent"  # SMTP 가 수신자를 받아 감
FAILED = "failed"  # 요청 전에 또는 명확히 거부됨(재시도 가능)
UNKNOWN = "unknown"  # 요청은 나갔으나 결과 불확실 — 재전송 금지, 사람이 확인
DRY_RUN = "dry_run"  # 드라이런(실제 전송 없음)
_LOG_STATUSES = (SENT, FAILED, UNKNOWN, DRY_RUN)

_KILL_SWITCH_KEY = "kill_switch"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _schema_v1(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS authorizations (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            account TEXT NOT NULL,
            kind TEXT NOT NULL,
            recipients TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            attachments TEXT NOT NULL DEFAULT '[]',
            attachments_hash TEXT NOT NULL DEFAULT '',
            document_hash TEXT NOT NULL,
            scope_hash TEXT NOT NULL,
            live INTEGER NOT NULL DEFAULT 0,
            approved INTEGER NOT NULL DEFAULT 0,
            approved_by TEXT,
            approved_at TEXT,
            approved_scope_hash TEXT,
            revoked INTEGER NOT NULL DEFAULT 0,
            revoked_by TEXT,
            revoked_at TEXT,
            paused INTEGER NOT NULL DEFAULT 0,
            paused_reason TEXT NOT NULL DEFAULT '',
            paused_at TEXT,
            test_sent_at TEXT,
            valid_from TEXT,
            valid_until TEXT,
            interval_sec INTEGER NOT NULL,
            max_per_run INTEGER NOT NULL,
            max_per_day INTEGER NOT NULL,
            max_total INTEGER NOT NULL,
            allowed_start TEXT NOT NULL,
            allowed_end TEXT NOT NULL,
            created_by TEXT,
            created_at TEXT NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS send_log (
            id TEXT PRIMARY KEY,
            authorization_id TEXT NOT NULL,
            email TEXT NOT NULL,
            document_hash TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_mb_log_auth ON send_log(authorization_id, created_at)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_mb_log_dedupe ON send_log(email, document_hash, status)")
    con.execute("""
        CREATE TABLE IF NOT EXISTS opt_out (
            email TEXT PRIMARY KEY,
            reason TEXT NOT NULL DEFAULT '',
            added_by TEXT,
            added_at TEXT NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS flags (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_by TEXT,
            updated_at TEXT NOT NULL
        )
    """)


# 한 번 배포된 단계는 수정하지 않고 새 단계를 뒤에 추가한다
_SCHEMA_STEPS = [_schema_v1]


@contextmanager
def _conn():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(_DB_PATH), timeout=30, isolation_level=None)
    set_busy_timeout(con)
    con.row_factory = sqlite3.Row
    try:
        apply_schema(con, _SCHEMA_STEPS)
        yield con
    finally:
        con.close()


def _authorization(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["recipients"] = json.loads(data["recipients"])
    data["attachments"] = json.loads(data["attachments"])
    for key in ("live", "approved", "revoked", "paused"):
        data[key] = bool(data[key])
    return data


# ── 승인서 ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NewAuthorization:
    """승인서 생성 입력. 범위(수신자·제목·본문·첨부·성격)는 생성 후 바꿀 수 없다."""

    name: str
    account: str
    kind: str
    recipients: list[dict[str, str]]
    subject: str
    body: str
    attachments: list[dict[str, Any]]
    attachments_hash: str
    document_hash: str
    scope_hash: str
    interval_sec: int
    max_per_run: int
    max_per_day: int
    max_total: int
    allowed_start: str
    allowed_end: str
    valid_from: str | None
    valid_until: str | None
    created_by: str


def create_authorization(new: NewAuthorization) -> dict[str, Any]:
    """승인 대기 상태(approved=0, live=0)로 만든다. 승인은 `approve()` 로만 한다."""
    auth_id = uuid.uuid4().hex
    with _conn() as con:
        con.execute(
            "INSERT INTO authorizations (id, name, account, kind, recipients, subject, body, attachments,"
            " attachments_hash, document_hash, scope_hash, interval_sec, max_per_run, max_per_day, max_total,"
            " allowed_start, allowed_end, valid_from, valid_until, created_by, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                auth_id,
                new.name,
                new.account,
                new.kind,
                json.dumps(new.recipients, ensure_ascii=False),
                new.subject,
                new.body,
                json.dumps(new.attachments, ensure_ascii=False),
                new.attachments_hash,
                new.document_hash,
                new.scope_hash,
                new.interval_sec,
                new.max_per_run,
                new.max_per_day,
                new.max_total,
                new.allowed_start,
                new.allowed_end,
                new.valid_from,
                new.valid_until,
                new.created_by,
                _now(),
            ),
        )
    return get_authorization(auth_id)  # type: ignore[return-value]


def get_authorization(auth_id: str) -> dict[str, Any] | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM authorizations WHERE id=?", (auth_id,)).fetchone()
    return _authorization(row) if row else None


def list_authorizations() -> list[dict[str, Any]]:
    with _conn() as con:
        rows = con.execute("SELECT * FROM authorizations ORDER BY created_at DESC").fetchall()
    return [_authorization(r) for r in rows]


def mark_test_sent(auth_id: str) -> None:
    """본인 주소 시험 발송을 마쳤다고 기록한다(승인 전 필수 단계)."""
    with _conn() as con:
        cur = con.execute("UPDATE authorizations SET test_sent_at=? WHERE id=?", (_now(), auth_id))
        if cur.rowcount == 0:
            raise ValueError("승인서를 찾을 수 없습니다")


def approve(auth_id: str, *, user: str, live: bool = False) -> dict[str, Any]:
    """승인한다. 승인 당시의 범위 해시를 고정한다(이후 수정 불가).

    기본 live=False(드라이런). 실전송은 `live=True` 를 명시해야 하고, **본인 시험 발송을 마친 승인서만** 실전송으로 승인된다.
    """
    with _conn() as con:
        row = con.execute("SELECT * FROM authorizations WHERE id=?", (auth_id,)).fetchone()
        if row is None:
            raise ValueError("승인서를 찾을 수 없습니다")
        if row["revoked"]:
            raise ValueError("취소된 승인서는 승인할 수 없습니다")
        if row["approved"]:
            raise ValueError("이미 승인된 승인서입니다 — 내용을 바꾸려면 새 승인서를 만드세요")
        if live and not row["test_sent_at"]:
            raise ValueError("본인 주소 시험 발송을 먼저 해야 실전송으로 승인할 수 있습니다")
        con.execute(
            "UPDATE authorizations SET approved=1, approved_by=?, approved_at=?, approved_scope_hash=scope_hash, live=?"
            " WHERE id=? AND approved=0 AND revoked=0",
            (user, _now(), 1 if live else 0, auth_id),
        )
    return get_authorization(auth_id)  # type: ignore[return-value]


def revoke(auth_id: str, *, user: str) -> dict[str, Any]:
    """승인서를 취소한다(즉시 중단). 되돌릴 수 없다."""
    with _conn() as con:
        cur = con.execute(
            "UPDATE authorizations SET revoked=1, revoked_by=?, revoked_at=? WHERE id=?", (user, _now(), auth_id)
        )
        if cur.rowcount == 0:
            raise ValueError("승인서를 찾을 수 없습니다")
    return get_authorization(auth_id)  # type: ignore[return-value]


def pause(auth_id: str, reason: str) -> None:
    """자동 멈춤. 사람이 `resume()` 하기 전에는 정책이 보내지 않는다."""
    with _conn() as con:
        cur = con.execute(
            "UPDATE authorizations SET paused=1, paused_reason=?, paused_at=? WHERE id=?",
            (reason[:200], _now(), auth_id),
        )
        if cur.rowcount == 0:
            raise ValueError("승인서를 찾을 수 없습니다")


def resume(auth_id: str) -> dict[str, Any]:
    """멈춘 승인서를 사람이 확인한 뒤 재개한다(취소된 승인서는 재개 불가)."""
    with _conn() as con:
        row = con.execute("SELECT revoked FROM authorizations WHERE id=?", (auth_id,)).fetchone()
        if row is None:
            raise ValueError("승인서를 찾을 수 없습니다")
        if row["revoked"]:
            raise ValueError("취소된 승인서는 재개할 수 없습니다")
        con.execute("UPDATE authorizations SET paused=0, paused_reason='', paused_at=NULL WHERE id=?", (auth_id,))
    return get_authorization(auth_id)  # type: ignore[return-value]


# ── 발송 이력(추가만) ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class SendRecord:
    authorization_id: str
    email: str
    document_hash: str
    status: str
    message: str = ""


def record_send(record: SendRecord) -> str:
    if record.status not in _LOG_STATUSES:
        raise ValueError(f"알 수 없는 발송 상태: {record.status}")
    log_id = uuid.uuid4().hex
    with _conn() as con:
        con.execute(
            "INSERT INTO send_log (id, authorization_id, email, document_hash, status, message, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (
                log_id,
                record.authorization_id,
                record.email,
                record.document_hash,
                record.status,
                record.message[:300],
                _now(),
            ),
        )
    return log_id


def _emails_with_status(document_hash: str, status: str) -> set[str]:
    with _conn() as con:
        rows = con.execute(
            "SELECT DISTINCT email FROM send_log WHERE document_hash=? AND status=?", (document_hash, status)
        ).fetchall()
    return {r["email"] for r in rows}


def sent_emails(document_hash: str) -> set[str]:
    """이 내용으로 이미 **성공**한 주소."""
    return _emails_with_status(document_hash, SENT)


def unknown_emails(document_hash: str) -> set[str]:
    """결과를 확정하지 못한 주소 — 사람이 확인하기 전에는 재전송하지 않는다."""
    return _emails_with_status(document_hash, UNKNOWN)


def count_sent(authorization_id: str, *, since_iso: str | None = None) -> int:
    """이 승인서로 보낸 건수(성공 + 결과 불명 — 불명도 이미 나갔을 수 있어 한도에 포함)."""
    sql = "SELECT COUNT(*) FROM send_log WHERE authorization_id=? AND status IN (?, ?)"
    params: list[Any] = [authorization_id, SENT, UNKNOWN]
    if since_iso:
        sql += " AND created_at >= ?"
        params.append(since_iso)
    with _conn() as con:
        return int(con.execute(sql, params).fetchone()[0])


def count_by_status(authorization_id: str) -> dict[str, int]:
    """진행 화면용: 상태별 건수."""
    with _conn() as con:
        rows = con.execute(
            "SELECT status, COUNT(*) AS n FROM send_log WHERE authorization_id=? GROUP BY status", (authorization_id,)
        ).fetchall()
    return {r["status"]: int(r["n"]) for r in rows}


def list_send_log(authorization_id: str, limit: int = 200) -> list[dict[str, Any]]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM send_log WHERE authorization_id=? ORDER BY created_at DESC LIMIT ?",
            (authorization_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


# ── 수신거부 ──────────────────────────────────────────────────────────────


def add_opt_out(email: str, *, reason: str = "", user: str = "") -> None:
    with _conn() as con:
        con.execute(
            "INSERT OR IGNORE INTO opt_out (email, reason, added_by, added_at) VALUES (?,?,?,?)",
            (email, reason[:200], user, _now()),
        )


def opt_out_emails() -> set[str]:
    with _conn() as con:
        rows = con.execute("SELECT email FROM opt_out").fetchall()
    return {r["email"] for r in rows}


# ── 전역 정지(킬 스위치) ─────────────────────────────────────────────────────


def set_kill_switch(on: bool, *, user: str) -> None:
    with _conn() as con:
        con.execute(
            "INSERT INTO flags (key, value, updated_by, updated_at) VALUES (?,?,?,?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_by=excluded.updated_by,"
            " updated_at=excluded.updated_at",
            (_KILL_SWITCH_KEY, "1" if on else "0", user, _now()),
        )


def kill_switch_on() -> bool:
    """정지 상태 여부. **정지 플래그를 읽지 못하면 정지로 간주한다(fail-closed).**"""
    try:
        with _conn() as con:
            row = con.execute("SELECT value FROM flags WHERE key=?", (_KILL_SWITCH_KEY,)).fetchone()
    except sqlite3.Error:
        return True
    return bool(row) and row["value"] == "1"

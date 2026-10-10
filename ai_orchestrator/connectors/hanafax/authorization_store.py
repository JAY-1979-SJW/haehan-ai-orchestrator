"""L7 Persistence — 하나팩스 발송 승인서·발송 이력·수신거부·정지 플래그 (sqlite).

기준서: docs/specs/2026-10-02_hanafax_auto_send.md
스키마 버전: `sqlite_schema.apply_schema` (docs/specs/2026-10-01_sqlite_schema_versioning.md). 이 DB 파일은 이 모듈만 소유한다.

설계 원칙
- **승인된 범위는 수정하지 않는다.** 수신자·제목·문서를 바꾸려면 새 승인서를 만들어 다시 승인받는다(해시 불일치의 근본 해결).
- **발송 이력은 추가만 한다**(수정·삭제 없음). 중복 발송 방지와 감사의 근거다.
- 전체 수신번호는 이 DB 에만 둔다. 반환·로그에는 호출자가 마스킹해서 쓴다.
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

_DB_PATH = storage_dir() / "fax_authorizations.db"

# 발송 이력 상태
SENT = "sent"  # 접수번호까지 확인된 성공
FAILED = "failed"  # 요청이 나가기 전에 명확히 실패(재시도 가능)
UNKNOWN = "unknown"  # 요청은 나갔으나 결과를 확정하지 못함 — 재전송 금지, 사람이 확인
DRY_RUN = "dry_run"  # 드라이런(실제 전송 없음)
DELIVERED = "delivered"  # 전송결과 화면에서 최종 성공을 확인
DELIVERY_FAILED = "delivery_failed"  # 전송결과 화면에서 최종 실패를 확인(접수 후 전달 실패) — 사람이 확인하기 전에는 자동 재전송하지 않는다
CLAIMED = "claimed"  # 전송 직전 선점 기록 — 결과 기록 전에 프로세스가 죽거나 기록이 실패해도 재전송하지 않게 한다

_KILL_SWITCH_KEY = "kill_switch"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _schema_v1(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS authorizations (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            recipients TEXT NOT NULL,
            subject TEXT NOT NULL,
            document_hash TEXT NOT NULL,
            document_ref TEXT NOT NULL DEFAULT '',
            scope_hash TEXT NOT NULL,
            live INTEGER NOT NULL DEFAULT 0,
            approved INTEGER NOT NULL DEFAULT 0,
            approved_by TEXT,
            approved_at TEXT,
            approved_scope_hash TEXT,
            revoked INTEGER NOT NULL DEFAULT 0,
            revoked_by TEXT,
            revoked_at TEXT,
            valid_from TEXT,
            valid_until TEXT,
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
            fax_digits TEXT NOT NULL,
            document_hash TEXT NOT NULL,
            status TEXT NOT NULL,
            job_id TEXT,
            message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_send_log_auth ON send_log(authorization_id, created_at)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_send_log_dedupe ON send_log(fax_digits, document_hash, status)")
    con.execute("""
        CREATE TABLE IF NOT EXISTS opt_out (
            fax_digits TEXT PRIMARY KEY,
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
    con = sqlite3.connect(str(_DB_PATH), timeout=30, isolation_level=None)  # 자동 커밋
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
    for key in ("live", "approved", "revoked"):
        data[key] = bool(data[key])
    return data


# ── 승인서 ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NewAuthorization:
    """승인서 생성 입력. 범위(수신자·제목·문서)는 생성 후 바꿀 수 없다."""

    name: str
    recipients: list[dict[str, str]]
    subject: str
    document_hash: str
    document_ref: str
    scope_hash: str
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
            "INSERT INTO authorizations (id, name, recipients, subject, document_hash, document_ref, scope_hash,"
            " max_per_run, max_per_day, max_total, allowed_start, allowed_end, valid_from, valid_until,"
            " created_by, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                auth_id,
                new.name,
                json.dumps(new.recipients, ensure_ascii=False),
                new.subject,
                new.document_hash,
                new.document_ref,
                new.scope_hash,
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


def approve(auth_id: str, *, user: str, live: bool = False) -> dict[str, Any]:
    """승인한다. 승인 당시의 범위 해시를 `approved_scope_hash` 로 고정한다(이후 수정 불가).

    기본 live=False(드라이런). 실전송은 `live=True` 를 명시해야 한다. 이미 승인·취소된 승인서는 다시 승인하지 않는다.
    """
    with _conn() as con:
        row = con.execute("SELECT * FROM authorizations WHERE id=?", (auth_id,)).fetchone()
        if row is None:
            raise ValueError("승인서를 찾을 수 없습니다")
        if row["revoked"]:
            raise ValueError("취소된 승인서는 승인할 수 없습니다")
        if row["approved"]:
            raise ValueError("이미 승인된 승인서입니다 — 내용을 바꾸려면 새 승인서를 만드세요")
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


# ── 발송 이력(추가만) ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class SendRecord:
    authorization_id: str
    fax_digits: str
    document_hash: str
    status: str
    job_id: str | None = None
    message: str = ""


def record_send(record: SendRecord) -> str:
    if record.status not in (SENT, FAILED, UNKNOWN, DRY_RUN, CLAIMED, DELIVERED, DELIVERY_FAILED):
        raise ValueError(f"알 수 없는 발송 상태: {record.status}")
    log_id = uuid.uuid4().hex
    with _conn() as con:
        con.execute(
            "INSERT INTO send_log (id, authorization_id, fax_digits, document_hash, status, job_id, message, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (
                log_id,
                record.authorization_id,
                record.fax_digits,
                record.document_hash,
                record.status,
                record.job_id,
                record.message[:300],
                _now(),
            ),
        )
    return log_id


def _latest_by_number(document_hash: str) -> dict[str, str]:
    """이 문서의 번호별 **가장 최근 상태**(드라이런 제외)."""
    with _conn() as con:
        rows = con.execute(
            "SELECT fax_digits, status FROM send_log WHERE document_hash=? ORDER BY rowid", (document_hash,)
        ).fetchall()
    return {r["fax_digits"]: r["status"] for r in rows if r["status"] != DRY_RUN}


def sent_numbers(document_hash: str) -> set[str]:
    """이 문서로 이미 보낸(접수 sent·최종 성공 delivered) 수신번호 — 번호별 가장 최근 상태 기준(해소·재전송 이후 상태 반영)."""
    return {n for n, status in _latest_by_number(document_hash).items() if status in (SENT, DELIVERED)}


def unknown_numbers(document_hash: str) -> set[str]:
    """사람이 확인해야 하는 수신번호 — 번호별 **가장 최근 상태**가 unknown·claimed(선점만 하고 결과 미기록)·delivery_failed(전송결과상 최종 실패)인 번호.

    사람이 확인하기 전에는 자동으로 다시 보내지 않는다. 이후 sent/failed 가 기록되면(사람이 해소) 더 이상 pending 이 아니다.
    """
    return {n for n, status in _latest_by_number(document_hash).items() if status in (UNKNOWN, CLAIMED, DELIVERY_FAILED)}


def pending_sent(authorization_id: str) -> list[dict[str, Any]]:
    """전송결과 대조 대상 — 번호별 가장 최근 상태가 sent(접수됨)이고 아직 최종 결과가 없는 기록(번호·시각·문서 해시)."""
    with _conn() as con:
        rows = con.execute(
            "SELECT fax_digits, status, created_at, document_hash FROM send_log WHERE authorization_id=? AND status != ? ORDER BY rowid",
            (authorization_id, DRY_RUN),
        ).fetchall()
    latest = {r["fax_digits"]: dict(r) for r in rows}
    return [r for r in latest.values() if r["status"] == SENT]


def count_sent(authorization_id: str, *, since_iso: str | None = None) -> int:
    """이 승인서로 보낸 건수 — **번호별 가장 최근 상태**가 성공·결과 불명·선점(전송 요청 직전)인 번호 수.

    불명·선점도 이미 나갔을 수 있어 한도에 포함한다. 사람이 '발송되지 않음'으로 해소하면(failed 기록) 그 번호는 빠지고,
    '발송됨'으로 해소하면(sent 기록) 같은 번호가 두 번 세어지지 않는다. since_iso 가 있으면 그 시각 이후 기록만 본다.
    """
    sql = "SELECT fax_digits, status FROM send_log WHERE authorization_id=? AND status != ?"
    params: list[Any] = [authorization_id, DRY_RUN]
    if since_iso:
        sql += " AND created_at >= ?"
        params.append(since_iso)
    with _conn() as con:
        rows = con.execute(sql + " ORDER BY rowid", params).fetchall()
    latest = {r["fax_digits"]: r["status"] for r in rows}
    return sum(1 for status in latest.values() if status in (SENT, UNKNOWN, CLAIMED, DELIVERED, DELIVERY_FAILED))


def list_send_log(authorization_id: str, limit: int = 200) -> list[dict[str, Any]]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM send_log WHERE authorization_id=? ORDER BY created_at DESC LIMIT ?",
            (authorization_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


# ── 수신거부 ──────────────────────────────────────────────────────────────


def add_opt_out(fax_digits: str, *, reason: str = "", user: str = "") -> None:
    with _conn() as con:
        con.execute(
            "INSERT OR IGNORE INTO opt_out (fax_digits, reason, added_by, added_at) VALUES (?,?,?,?)",
            (fax_digits, reason[:200], user, _now()),
        )


def opt_out_numbers() -> set[str]:
    with _conn() as con:
        rows = con.execute("SELECT fax_digits FROM opt_out").fetchall()
    return {r["fax_digits"] for r in rows}


# ── 일반 플래그(승인 PIN 해시·실패 횟수 등) ─────────────────────────────────────


def get_flag(key: str) -> str | None:
    with _conn() as con:
        row = con.execute("SELECT value FROM flags WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def set_flag(key: str, value: str, *, user: str = "") -> None:
    with _conn() as con:
        con.execute(
            "INSERT INTO flags (key, value, updated_by, updated_at) VALUES (?,?,?,?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_by=excluded.updated_by,"
            " updated_at=excluded.updated_at",
            (key, value, user, _now()),
        )


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

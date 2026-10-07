"""L7 Persistence — 사람 발급 1회용 승인 기록(sqlite). 저장·원자 갱신(CAS)만 담당하고 정책은 모른다.

설계서: docs/architecture/R2D2_HUMAN_APPROVAL_PLAN.md §3. 정책(해시 계산·허용된 발급 경로·감사·예외)은
`ai_orchestrator/gates/human_approval.py`(L2)가 맡고, 이 모듈은 그 정책이 시킨 상태 전이를 **단일 SQL 갱신**으로 수행한다.
스키마 버전은 `sqlite_schema.apply_schema`(PRAGMA user_version) 로 관리한다. 이 DB 파일은 이 모듈만 소유한다.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .sqlite_schema import apply_schema, set_busy_timeout

PENDING, APPROVED, USED, EXPIRED, REJECTED, REVOKED = "pending", "approved", "used", "expired", "rejected", "revoked"


def db_path() -> Path:
    env = os.environ.get("HUMAN_APPROVAL_DB")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[1] / "storage" / "human_approvals.db"


def _schema_v1(con: sqlite3.Connection) -> None:
    con.execute(
        """CREATE TABLE IF NOT EXISTS approvals (
            id TEXT PRIMARY KEY,
            op TEXT NOT NULL,
            target_hash TEXT NOT NULL,
            target_preview TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL,
            content_snapshot TEXT NOT NULL,
            requested_by TEXT NOT NULL,
            requested_at REAL NOT NULL,
            status TEXT NOT NULL,
            approved_by TEXT,
            approved_at REAL,
            approved_via TEXT,
            expires_at REAL,
            max_uses INTEGER NOT NULL DEFAULT 1,
            uses INTEGER NOT NULL DEFAULT 0,
            used_at REAL,
            schedule_job_id TEXT
        )"""
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_approvals_lookup ON approvals(op, target_hash, content_hash, status)")


_SCHEMA_STEPS = (_schema_v1,)
SCHEMA_VERSION = len(_SCHEMA_STEPS)


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), timeout=30, isolation_level=None)  # 명시적 트랜잭션(BEGIN IMMEDIATE)
    set_busy_timeout(con)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA journal_mode=WAL")
        apply_schema(con, _SCHEMA_STEPS)
        yield con
    finally:
        con.close()


def _dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return None if row is None else dict(row)


def insert_request(  # noqa: PLR0913 - 저장 계층의 열 단위 입력(정책 계층이 계산해 넘긴다)
    rid: str,
    op: str,
    target_hash: str,
    target_preview: str,
    content_hash: str,
    content_snapshot: str,
    requested_by: str,
    requested_at: float,
    max_uses: int,
    schedule_job_id: str | None,
) -> None:
    with _conn() as con:
        con.execute(
            "INSERT INTO approvals (id, op, target_hash, target_preview, content_hash, content_snapshot, requested_by,"
            " requested_at, status, max_uses, schedule_job_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                rid,
                op,
                target_hash,
                target_preview,
                content_hash,
                content_snapshot,
                requested_by,
                requested_at,
                PENDING,
                max_uses,
                schedule_job_id,
            ),
        )


def approve_cas(rid: str, approved_by: str, via: str, ts: float, expires_at: float) -> dict[str, Any] | None:
    """pending → approved 를 한 번의 갱신으로. 이미 다른 상태면 None."""
    with _conn() as con:
        row = con.execute(
            "UPDATE approvals SET status=?, approved_by=?, approved_at=?, approved_via=?, expires_at=?"
            " WHERE id=? AND status=? RETURNING *",
            (APPROVED, approved_by, ts, via, expires_at, rid, PENDING),
        ).fetchone()
    return _dict(row)


def reject_cas(rid: str, by: str, ts: float) -> bool:
    with _conn() as con:
        cur = con.execute(
            "UPDATE approvals SET status=?, approved_by=?, approved_at=? WHERE id=? AND status=?",
            (REJECTED, by, ts, rid, PENDING),
        )
        return cur.rowcount == 1


def revoke_cas(rid: str) -> bool:
    with _conn() as con:
        cur = con.execute(
            "UPDATE approvals SET status=? WHERE id=? AND status IN (?,?)", (REVOKED, rid, PENDING, APPROVED)
        )
        return cur.rowcount == 1


def revoke_for_job(job_id: str) -> int:
    with _conn() as con:
        cur = con.execute(
            "UPDATE approvals SET status=? WHERE schedule_job_id=? AND status IN (?,?)",
            (REVOKED, job_id, PENDING, APPROVED),
        )
        return cur.rowcount


_CONSUME_SQL = (
    "UPDATE approvals SET uses = uses + 1, used_at = ?,"
    " status = CASE WHEN uses + 1 >= max_uses THEN ? ELSE status END"
    " WHERE id = (SELECT id FROM approvals WHERE op = ? AND target_hash = ? AND content_hash = ?"
    "   AND status = ? AND expires_at > ? AND uses < max_uses AND {job_clause}"
    " ORDER BY approved_at LIMIT 1)"
    " AND status = ? AND uses < max_uses RETURNING *"
)


def consume_cas(op: str, target_hash: str, content_hash: str, job_id: str | None, now: float) -> dict[str, Any] | None:
    """같은 (op, 대상, 내용)의 approved 1건을 **원자적으로** 소진한다. 없거나 만료·소진이면 None.

    job_id 가 있으면 그 예약에 묶인 승인만, 없으면 예약에 묶이지 않은 승인만 대상이다.
    `BEGIN IMMEDIATE` 로 쓰기 잠금을 먼저 잡아 프로세스 간 경쟁에서도 정확히 1건만 소진된다.
    """
    job_clause = "schedule_job_id = ?" if job_id is not None else "schedule_job_id IS NULL"
    sql = _CONSUME_SQL.format(job_clause=job_clause)  # 코드 상수 조각만 끼워 넣는다(값은 모두 바인딩)
    params: list[Any] = [now, USED, op, target_hash, content_hash, APPROVED, now]
    if job_id is not None:
        params.append(job_id)
    params.append(APPROVED)
    with _conn() as con:
        con.execute("BEGIN IMMEDIATE")
        try:
            row = con.execute(sql, params).fetchone()
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    return _dict(row)


def get(rid: str) -> dict[str, Any] | None:
    with _conn() as con:
        return _dict(con.execute("SELECT * FROM approvals WHERE id=?", (rid,)).fetchone())


def list_by_status(status: str) -> list[dict[str, Any]]:
    with _conn() as con:
        rows = con.execute("SELECT * FROM approvals WHERE status=? ORDER BY requested_at", (status,)).fetchall()
    return [dict(r) for r in rows]


def expire_due(now: float) -> int:
    with _conn() as con:
        cur = con.execute("UPDATE approvals SET status=? WHERE status=? AND expires_at <= ?", (EXPIRED, APPROVED, now))
        return cur.rowcount

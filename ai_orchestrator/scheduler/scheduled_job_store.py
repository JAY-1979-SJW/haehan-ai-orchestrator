"""L7 Persistence — 사용자 예약 작업 SQLite (jobs, runs).

기준서: docs/specs/2026-10-01_user_scheduled_jobs.md
시각은 UTC ISO(`+00:00`) 문자열로 저장해 문자열 비교로 순서를 가린다.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from ai_orchestrator.paths.runtime import storage_dir

from ..persistence.sqlite_schema import (
    add_column_if_missing,
    apply_schema,
    set_busy_timeout,
)

_DB_PATH = storage_dir() / "scheduled_jobs.db"

_JOB_FIELDS = {
    "name",
    "params",
    "recurrence",
    "status",
    "next_run_at",
    "last_run_at",
    "last_status",
    "last_message",
}
_JSON_FIELDS = {"params", "recurrence"}


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="seconds")


def _schema_v1(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            action TEXT NOT NULL,
            params TEXT NOT NULL DEFAULT '{}',
            recurrence TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            next_run_at TEXT,
            last_run_at TEXT,
            last_status TEXT,
            last_message TEXT,
            created_by TEXT,
            created_at TEXT NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            scheduled_for TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL,
            message TEXT NOT NULL DEFAULT '',
            decided_by TEXT
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_runs_job ON runs(job_id, started_at)")


def _schema_v2_runs_decided_by(con: sqlite3.Connection) -> None:
    # 승인 흐름 도입 전에 만든 DB 보정
    add_column_if_missing(con, "runs", "decided_by", "TEXT")


# 한 번 배포된 단계는 수정하지 않고 새 단계를 뒤에 추가한다(docs/specs/2026-10-01_sqlite_schema_versioning.md)
_SCHEMA_STEPS = [_schema_v1, _schema_v2_runs_decided_by]


@contextmanager
def _conn():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(_DB_PATH), timeout=30, isolation_level=None)  # 자동 커밋, 선점만 명시 트랜잭션
    set_busy_timeout(con)
    con.row_factory = sqlite3.Row
    try:
        apply_schema(con, _SCHEMA_STEPS)
        yield con
    finally:
        con.close()


def _job(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    for key in _JSON_FIELDS:
        d[key] = json.loads(d[key])
    return d


def create_job(
    *, name: str, action: str, params: dict, recurrence: dict, next_run_at: str | None, created_by: str
) -> dict[str, Any]:
    job_id = uuid.uuid4().hex
    with _conn() as con:
        con.execute(
            "INSERT INTO jobs (id, name, action, params, recurrence, status, next_run_at, created_by, created_at)"
            " VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)",
            (
                job_id,
                name,
                action,
                json.dumps(params, ensure_ascii=False),
                json.dumps(recurrence, ensure_ascii=False),
                next_run_at,
                created_by,
                iso(datetime.now(UTC)),
            ),
        )
    return get_job(job_id)  # type: ignore[return-value]


def get_job(job_id: str) -> dict[str, Any] | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return _job(row) if row else None


def list_jobs() -> list[dict[str, Any]]:
    with _conn() as con:
        rows = con.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
    return [_job(r) for r in rows]


def update_job(job_id: str, **fields: Any) -> dict[str, Any] | None:
    unknown = set(fields) - _JOB_FIELDS
    if unknown:
        raise ValueError(f"수정할 수 없는 항목: {sorted(unknown)}")
    if fields:
        values = [json.dumps(v, ensure_ascii=False) if k in _JSON_FIELDS else v for k, v in fields.items()]
        sets = ", ".join(f"{k}=?" for k in fields)
        with _conn() as con:
            con.execute(
                f"UPDATE jobs SET {sets} WHERE id=?", (*values, job_id)
            )  # 컬럼명은 _JOB_FIELDS 허용 목록으로 제한됨
    return get_job(job_id)


def delete_job(job_id: str) -> bool:
    with _conn() as con:
        con.execute("DELETE FROM runs WHERE job_id=?", (job_id,))
        cur = con.execute("DELETE FROM jobs WHERE id=?", (job_id,))
    return cur.rowcount > 0


def _new_run(
    con: sqlite3.Connection,
    job_id: str,
    scheduled_for: str,
    started_at: str,
    status: str = "running",
    message: str = "",
) -> dict[str, Any]:
    run = {
        "id": uuid.uuid4().hex,
        "job_id": job_id,
        "scheduled_for": scheduled_for,
        "started_at": started_at,
        "finished_at": None,
        "status": status,
        "message": message,
        "decided_by": None,
    }
    con.execute(
        "INSERT INTO runs (id, job_id, scheduled_for, started_at, status, message) VALUES (?, ?, ?, ?, ?, ?)",
        (run["id"], job_id, scheduled_for, started_at, status, message),
    )
    return run


def create_run(
    job_id: str, scheduled_for: str, started_at: str, status: str = "running", message: str = ""
) -> dict[str, Any]:
    with _conn() as con:
        return _new_run(con, job_id, scheduled_for, started_at, status, message)


def claim_due(
    now: str,
    advance: Callable[[dict[str, Any], str], str | None],
    initial: Callable[[dict[str, Any]], tuple[str, str]] = lambda job: ("running", ""),
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """실행 시각이 된 활성 작업을 한 트랜잭션으로 선점한다.

    각 작업의 다음 실행 시각을 먼저 갱신(`advance` 가 None 이면 done)하고 회차를 만든다(`initial` 이 정한 상태·메시지, 기본 running).
    다른 프로세스·틱이 같은 작업을 다시 집지 못한다.
    """
    claimed: list[tuple[dict[str, Any], dict[str, Any]]] = []
    with _conn() as con:
        con.execute("BEGIN IMMEDIATE")
        try:
            rows = con.execute(
                "SELECT * FROM jobs WHERE status='active' AND next_run_at IS NOT NULL AND next_run_at<=?"
                " ORDER BY next_run_at",
                (now,),
            ).fetchall()
            for row in rows:
                job = _job(row)
                nxt = advance(job, now)
                if nxt is None:
                    con.execute("UPDATE jobs SET next_run_at=NULL, status='done' WHERE id=?", (job["id"],))
                else:
                    con.execute("UPDATE jobs SET next_run_at=? WHERE id=?", (nxt, job["id"]))
                status, message = initial(job)
                claimed.append((job, _new_run(con, job["id"], job["next_run_at"], now, status, message)))
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
    return claimed


def finish_run(run_id: str, status: str, message: str, finished_at: str) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE runs SET status=?, message=?, finished_at=? WHERE id=?",
            (status, message[:500], finished_at, run_id),
        )


def list_runs(job_id: str, limit: int = 20) -> list[dict[str, Any]]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM runs WHERE job_id=? ORDER BY started_at DESC, rowid DESC LIMIT ?", (job_id, limit)
        ).fetchall()
    return [dict(r) for r in rows]


def recover_stale_runs(finished_at: str) -> int:
    """서버가 도중에 멈춰 `running` 으로 남은 회차를 실패로 정리한다."""
    with _conn() as con:
        cur = con.execute(
            "UPDATE runs SET status='failed', message='서버가 중단되어 완료되지 못했습니다', finished_at=?"
            " WHERE status='running'",
            (finished_at,),
        )
    return cur.rowcount


def get_run(run_id: str) -> dict[str, Any] | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    return dict(row) if row else None


def transition_run(
    run_id: str,
    *,
    from_status: str,
    to_status: str,
    message: str = "",
    decided_by: str | None = None,
    finished_at: str | None = None,
) -> bool:
    """회차 상태를 `from_status` 일 때만 바꾼다(원자적). 이미 다른 상태면 False — 같은 회차를 두 번 승인하지 못하게 한다."""
    with _conn() as con:
        cur = con.execute(
            "UPDATE runs SET status=?, message=?, decided_by=COALESCE(?, decided_by), finished_at=COALESCE(?, finished_at)"
            " WHERE id=? AND status=?",
            (to_status, message[:500], decided_by, finished_at, run_id, from_status),
        )
    return cur.rowcount == 1


def list_runs_with_status(status: str) -> list[dict[str, Any]]:
    """해당 상태의 회차를 작업 정보와 함께(오래된 순)."""
    with _conn() as con:
        rows = con.execute(
            "SELECT r.*, j.name AS job_name, j.action AS job_action, j.params AS job_params"
            " FROM runs r JOIN jobs j ON j.id = r.job_id WHERE r.status=? ORDER BY r.started_at",
            (status,),
        ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["job_params"] = json.loads(d["job_params"])
        result.append(d)
    return result

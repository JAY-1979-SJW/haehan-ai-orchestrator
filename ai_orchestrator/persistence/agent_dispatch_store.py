"""L7 Persistence — AI 에이전트 작업 분배(분배안·하위 작업 진행) 저장소 (sqlite).

기준서: docs/specs/2026-10-02_app_agent_dispatch.md (P3). 이 DB 파일은 이 모듈만 소유한다.
스키마 버전: `sqlite_schema.apply_schema`.

- 분배안(dispatches)은 상태가 `planning → proposed → approved(running) → completed|failed|cancelled` 로만 흐른다.
- **승인된 분배안의 하위 작업 구성(역할·프롬프트·자원·의존)은 바꾸지 않는다.** 진행 상태·결과만 갱신한다.
- 결과 본문은 길이를 잘라 저장한다. 비밀번호·토큰은 저장하지 않는다(호출자가 prompt 에 넣지 않는다).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .sqlite_schema import apply_schema

_DB_PATH = Path(__file__).resolve().parents[1] / "storage" / "agent_dispatch.db"

# 분배안 상태
PLANNING, PROPOSED, RUNNING, COMPLETED, FAILED, CANCELLED = (
    "planning",
    "proposed",
    "running",
    "completed",
    "failed",
    "cancelled",
)
FINAL_STATUSES = (COMPLETED, FAILED, CANCELLED)

RESULT_MAX_CHARS = 20000


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _schema_v1(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS dispatches (
            id TEXT PRIMARY KEY,
            goal TEXT NOT NULL,
            status TEXT NOT NULL,
            max_parallel INTEGER NOT NULL,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            planner_agent_id TEXT NOT NULL DEFAULT '',
            planner_task_id TEXT NOT NULL DEFAULT '',
            approved_by TEXT,
            approved_at TEXT,
            finished_at TEXT,
            note TEXT NOT NULL DEFAULT ''
        )""")
    con.execute("""
        CREATE TABLE IF NOT EXISTS subtasks (
            dispatch_id TEXT NOT NULL,
            tid TEXT NOT NULL,
            position INTEGER NOT NULL,
            title TEXT NOT NULL,
            role TEXT NOT NULL,
            prompt TEXT NOT NULL,
            resources TEXT NOT NULL,
            depends_on TEXT NOT NULL,
            budget_usd REAL NOT NULL,
            timeout_sec INTEGER NOT NULL,
            state TEXT NOT NULL DEFAULT 'pending',
            agent_id TEXT NOT NULL DEFAULT '',
            task_id TEXT NOT NULL DEFAULT '',
            result_text TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '',
            started_at TEXT,
            finished_at TEXT,
            PRIMARY KEY (dispatch_id, tid)
        )""")


# 한 번 배포된 단계는 수정하지 않고 새 단계를 뒤에 추가한다
_SCHEMA_STEPS = [_schema_v1]


@contextmanager
def _conn():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(_DB_PATH), timeout=30, isolation_level=None)
    con.row_factory = sqlite3.Row
    try:
        apply_schema(con, _SCHEMA_STEPS)
        yield con
    finally:
        con.close()


def _subtask(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["resources"] = json.loads(data["resources"])
    data["depends_on"] = json.loads(data["depends_on"])
    return data


# ── 분배안 ───────────────────────────────────────────────────────────────
def create_dispatch(
    *, goal: str, max_parallel: int, created_by: str, planner_agent_id: str, planner_task_id: str
) -> str:
    did = uuid.uuid4().hex
    with _conn() as con:
        con.execute(
            "INSERT INTO dispatches (id, goal, status, max_parallel, created_by, created_at,"
            " planner_agent_id, planner_task_id) VALUES (?,?,?,?,?,?,?,?)",
            (did, goal, PLANNING, max_parallel, created_by, _now(), planner_agent_id, planner_task_id),
        )
    return did


def get_dispatch(did: str) -> dict[str, Any] | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM dispatches WHERE id=?", (did,)).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["subtasks"] = [
            _subtask(r) for r in con.execute("SELECT * FROM subtasks WHERE dispatch_id=? ORDER BY position", (did,))
        ]
    return data


def list_dispatches(limit: int = 30) -> list[dict[str, Any]]:
    with _conn() as con:
        rows = con.execute(
            "SELECT id, goal, status, max_parallel, created_by, created_at, finished_at, note"
            " FROM dispatches ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (max(1, min(100, limit)),),
        ).fetchall()
    return [dict(r) for r in rows]


def set_status(did: str, status: str, *, note: str = "", only_from: tuple[str, ...] | None = None) -> bool:
    """상태 전이. only_from 을 주면 현재 상태가 그중 하나일 때만 바꾼다(동시 호출 방어). 바뀌었으면 True."""
    finished = _now() if status in FINAL_STATUSES else None
    with _conn() as con:
        sql = "UPDATE dispatches SET status=?, note=?, finished_at=COALESCE(?, finished_at) WHERE id=?"
        args: list[Any] = [status, note[:500], finished, did]
        if only_from:
            sql += f" AND status IN ({','.join('?' * len(only_from))})"
            args += list(only_from)
        return con.execute(sql, args).rowcount == 1


def save_plan(did: str, tasks: list[dict[str, Any]]) -> bool:
    """계획 단계가 끝나면 하위 작업을 저장하고 proposed 로 바꾼다(planning 일 때만)."""
    with _conn() as con:
        con.execute("BEGIN IMMEDIATE")
        try:
            row = con.execute("SELECT status FROM dispatches WHERE id=?", (did,)).fetchone()
            if row is None or row["status"] != PLANNING:
                con.execute("ROLLBACK")
                return False
            for pos, t in enumerate(tasks):
                con.execute(
                    "INSERT INTO subtasks (dispatch_id, tid, position, title, role, prompt, resources,"
                    " depends_on, budget_usd, timeout_sec) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        did,
                        t["id"],
                        pos,
                        t["title"],
                        t["role"],
                        t["prompt"],
                        json.dumps(t.get("resources") or [], ensure_ascii=False),
                        json.dumps(t.get("depends_on") or [], ensure_ascii=False),
                        float(t["budget_usd"]),
                        int(t["timeout_sec"]),
                    ),
                )
            con.execute("UPDATE dispatches SET status=? WHERE id=?", (PROPOSED, did))
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    return True


def approve(did: str, approved_by: str) -> bool:
    """proposed → running. 한 번만 성공한다."""
    with _conn() as con:
        return (
            con.execute(
                "UPDATE dispatches SET status=?, approved_by=?, approved_at=? WHERE id=? AND status=?",
                (RUNNING, approved_by, _now(), did, PROPOSED),
            ).rowcount
            == 1
        )


# ── 하위 작업 진행 ───────────────────────────────────────────────────────
def update_subtask(did: str, tid: str, **fields: Any) -> None:
    allowed = {"state", "agent_id", "task_id", "result_text", "error", "started_at", "finished_at"}
    bad = set(fields) - allowed
    if bad:
        raise ValueError(f"갱신할 수 없는 필드: {sorted(bad)}")
    if "result_text" in fields:
        fields["result_text"] = str(fields["result_text"])[:RESULT_MAX_CHARS]
    if "error" in fields:
        fields["error"] = str(fields["error"])[:500]
    if not fields:
        return
    sets = ", ".join(f"{k}=?" for k in fields)
    with _conn() as con:
        con.execute(f"UPDATE subtasks SET {sets} WHERE dispatch_id=? AND tid=?", [*fields.values(), did, tid])


def running_dispatch_ids() -> list[str]:
    with _conn() as con:
        return [r["id"] for r in con.execute("SELECT id FROM dispatches WHERE status=?", (RUNNING,))]

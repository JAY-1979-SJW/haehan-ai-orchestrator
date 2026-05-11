"""CDP 작업 DB — 로그인 세션 목록 + 작업 로그를 SQLite에 저장.

테이블:
  sessions   — 사이트별 로그인 세션 현황
  task_logs  — 모든 작업 실행 로그

위치: data/cdp.db
"""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "cdp.db"


# ── 연결 ──────────────────────────────────────────────────────────

@contextmanager
def _conn() -> Generator[sqlite3.Connection, None, None]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH), timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# ── 초기화 ────────────────────────────────────────────────────────

def init_db() -> None:
    """테이블이 없으면 생성."""
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                site_name     TEXT PRIMARY KEY,
                display       TEXT NOT NULL,
                logged_in     INTEGER NOT NULL DEFAULT 0,   -- 0/1
                session_file  TEXT,
                last_checked  TEXT,
                last_login    TEXT,
                updated_at    TEXT
            );

            CREATE TABLE IF NOT EXISTS site_requests (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                requested_at  TEXT NOT NULL,
                site_name     TEXT NOT NULL,
                task_name     TEXT NOT NULL DEFAULT '',
                task_args     TEXT,                         -- JSON
                source        TEXT DEFAULT 'cli'           -- cli / api / mcp 등
            );

            CREATE INDEX IF NOT EXISTS idx_site_requests_site
                ON site_requests(site_name, requested_at DESC);

            CREATE TABLE IF NOT EXISTS task_logs (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at    TEXT NOT NULL,
                finished_at   TEXT,
                site_name     TEXT NOT NULL,
                task_name     TEXT NOT NULL,
                task_args     TEXT,                         -- JSON
                status        TEXT NOT NULL DEFAULT 'running',  -- running/success/fail/timeout
                duration_sec  REAL,
                error_msg     TEXT,
                detail        TEXT                          -- 자유형식 추가 정보
            );

            CREATE INDEX IF NOT EXISTS idx_task_logs_site
                ON task_logs(site_name, started_at DESC);
        """)


# ── 사용자 요청 사이트 ────────────────────────────────────────────

def log_request(
    site_name: str,
    task_name: str = "",
    task_args: list[str] | None = None,
    source: str = "cli",
) -> int:
    """사용자가 요청한 사이트/작업을 기록. request_id 반환."""
    import json
    now = _now()
    with _conn() as con:
        cur = con.execute("""
            INSERT INTO site_requests (requested_at, site_name, task_name, task_args, source)
            VALUES (?, ?, ?, ?, ?)
        """, (now, site_name, task_name,
              json.dumps(task_args or [], ensure_ascii=False), source))
        return cur.lastrowid  # type: ignore[return-value]


def get_site_requests(
    site_name: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """요청 이력 조회."""
    with _conn() as con:
        if site_name:
            rows = con.execute("""
                SELECT * FROM site_requests
                WHERE site_name = ?
                ORDER BY requested_at DESC LIMIT ?
            """, (site_name, limit)).fetchall()
        else:
            rows = con.execute("""
                SELECT * FROM site_requests
                ORDER BY requested_at DESC LIMIT ?
            """, (limit,)).fetchall()
    return [dict(r) for r in rows]


def get_request_summary() -> list[dict]:
    """사이트별 요청 횟수 + 마지막 요청 시각 집계."""
    with _conn() as con:
        rows = con.execute("""
            SELECT site_name,
                   COUNT(*)        AS total,
                   MAX(requested_at) AS last_requested_at
            FROM site_requests
            GROUP BY site_name
            ORDER BY total DESC
        """).fetchall()
    return [dict(r) for r in rows]


# ── 세션 ──────────────────────────────────────────────────────────

def upsert_session(
    site_name: str,
    display: str,
    logged_in: bool,
    session_file: str = "",
    login_event: bool = False,
) -> None:
    """세션 현황 갱신. login_event=True 이면 last_login도 업데이트."""
    now = _now()
    with _conn() as con:
        existing = con.execute(
            "SELECT last_login FROM sessions WHERE site_name = ?", (site_name,)
        ).fetchone()
        last_login = (now if login_event else (existing["last_login"] if existing else None))

        con.execute("""
            INSERT INTO sessions (site_name, display, logged_in, session_file,
                                  last_checked, last_login, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(site_name) DO UPDATE SET
                display       = excluded.display,
                logged_in     = excluded.logged_in,
                session_file  = excluded.session_file,
                last_checked  = excluded.last_checked,
                last_login    = excluded.last_login,
                updated_at    = excluded.updated_at
        """, (site_name, display, int(logged_in), session_file, now, last_login, now))


def get_sessions() -> list[dict]:
    """전체 세션 목록 반환."""
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM sessions ORDER BY site_name"
        ).fetchall()
    return [dict(r) for r in rows]


# ── 작업 로그 ─────────────────────────────────────────────────────

def log_start(site_name: str, task_name: str, task_args: list[str]) -> int:
    """작업 시작 기록. log_id 반환."""
    import json
    now = _now()
    with _conn() as con:
        cur = con.execute("""
            INSERT INTO task_logs (started_at, site_name, task_name, task_args, status)
            VALUES (?, ?, ?, ?, 'running')
        """, (now, site_name, task_name, json.dumps(task_args, ensure_ascii=False)))
        return cur.lastrowid  # type: ignore[return-value]


def log_finish(
    log_id: int,
    status: str,           # success / fail / timeout
    error_msg: str = "",
    detail: str = "",
) -> None:
    """작업 완료 기록."""
    now = _now()
    with _conn() as con:
        started = con.execute(
            "SELECT started_at FROM task_logs WHERE id = ?", (log_id,)
        ).fetchone()
        duration = None
        if started:
            try:
                t0 = datetime.fromisoformat(started["started_at"])
                duration = (datetime.now(timezone.utc) - t0).total_seconds()
            except Exception:
                pass
        con.execute("""
            UPDATE task_logs
            SET finished_at = ?, status = ?, duration_sec = ?,
                error_msg = ?, detail = ?
            WHERE id = ?
        """, (now, status, duration, error_msg or None, detail or None, log_id))


def get_task_logs(
    site_name: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """작업 로그 조회. site_name 지정 시 해당 사이트만."""
    with _conn() as con:
        if site_name:
            rows = con.execute("""
                SELECT * FROM task_logs
                WHERE site_name = ?
                ORDER BY started_at DESC LIMIT ?
            """, (site_name, limit)).fetchall()
        else:
            rows = con.execute("""
                SELECT * FROM task_logs
                ORDER BY started_at DESC LIMIT ?
            """, (limit,)).fetchall()
    return [dict(r) for r in rows]


# ── CLI (python scripts/cdp_db.py) ───────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def print_sessions() -> None:
    rows = get_sessions()
    if not rows:
        print("  세션 기록 없음")
        return
    print(f"  {'사이트':<12} {'표시명':<20} {'로그인':<8} {'마지막 로그인':<25} {'확인'}")
    print("  " + "-" * 80)
    for r in rows:
        logged = "✓ 됨" if r["logged_in"] else "✗ 안됨"
        print(f"  {r['site_name']:<12} {r['display']:<20} {logged:<8} "
              f"{(r['last_login'] or '-'):<25} {r['last_checked'] or '-'}")


def print_site_requests(site_name: str | None = None, limit: int = 30) -> None:
    rows = get_site_requests(site_name, limit)
    if not rows:
        print("  요청 기록 없음")
        return
    print(f"  {'#':<5} {'요청시각':<22} {'사이트':<10} {'작업':<12} {'인수':<20} 출처")
    print("  " + "-" * 80)
    for r in rows:
        args = r.get("task_args") or "[]"
        try:
            import json
            args = " ".join(json.loads(args)) or "-"
        except Exception:
            pass
        print(f"  {r['id']:<5} {r['requested_at']:<22} {r['site_name']:<10} "
              f"{r['task_name'] or '-':<12} {args[:20]:<20} {r['source']}")


def print_request_summary() -> None:
    rows = get_request_summary()
    if not rows:
        print("  요청 기록 없음")
        return
    print(f"  {'사이트':<12} {'요청횟수':>8}  {'마지막 요청'}")
    print("  " + "-" * 50)
    for r in rows:
        print(f"  {r['site_name']:<12} {r['total']:>8}  {r['last_requested_at']}")


def print_task_logs(site_name: str | None = None, limit: int = 20) -> None:
    rows = get_task_logs(site_name, limit)
    if not rows:
        print("  로그 없음")
        return
    print(f"  {'#':<5} {'시작':<22} {'사이트':<10} {'작업':<12} {'상태':<10} {'소요':<8} 오류")
    print("  " + "-" * 85)
    for r in rows:
        dur = f"{r['duration_sec']:.1f}s" if r["duration_sec"] is not None else "-"
        err = (r["error_msg"] or "")[:40]
        print(f"  {r['id']:<5} {r['started_at']:<22} {r['site_name']:<10} "
              f"{r['task_name']:<12} {r['status']:<10} {dur:<8} {err}")


if __name__ == "__main__":
    import sys
    init_db()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "sessions"
    if cmd == "sessions":
        print("\n[로그인 세션 목록]")
        print_sessions()
    elif cmd == "logs":
        site = sys.argv[2] if len(sys.argv) > 2 else None
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else 20
        print(f"\n[작업 로그{' — ' + site if site else ''}]")
        print_task_logs(site, limit)
    elif cmd == "requests":
        site = sys.argv[2] if len(sys.argv) > 2 else None
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else 30
        if site == "summary":
            print("\n[사이트 요청 집계]")
            print_request_summary()
        else:
            print(f"\n[사용자 요청 이력{' — ' + site if site else ''}]")
            print_site_requests(site, limit)
    else:
        print("사용법: python scripts/cdp_db.py [sessions|logs|requests] [site] [limit]")
        print("        python scripts/cdp_db.py requests summary")

"""작업 단위 로그 — op_log v1.0

모든 주요 작업의 시작/종료/소요시간/결과를 기록한다.
critical_logger(감사추적)와 app.log(디버그)의 중간 레이어.

저장 위치:
  - data/logs/ops.log     (텍스트 — 실시간 모니터링용)
  - data/cdp.db ops_log   (SQLite — 조회/통계용)

사용법:
    # 1) 데코레이터
    from scripts.op_log import op_logged

    @op_logged("goto")
    def goto(target: str) -> None:
        ...

    # 2) 컨텍스트 매니저
    from scripts.op_log import op_context

    with op_context("eum_extract", site="eum.cw.or.kr") as ctx:
        result = do_extract()
        ctx.set_result(count=len(result))

    # 3) 단발 호출
    from scripts.op_log import log_op
    log_op("mail_send", ok=True, to="vendor@x.com", subject="...")

CLI:
    python scripts/cdp_client.py op-log list
    python scripts/cdp_client.py op-log tail
    python scripts/cdp_client.py op-log stats
"""
from __future__ import annotations

import contextlib
import functools
import json
import sqlite3
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable, Generator

import logging

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "data" / "logs"
OPS_LOG_FILE = LOG_DIR / "ops.log"
DB_PATH = ROOT / "data" / "cdp.db"

_FMT = "%(asctime)s  [%(op_name)-24s] %(levelname)-4s  %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"

_logger: logging.Logger | None = None


def _init() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("op_log")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if not logger.handlers:
        fh = RotatingFileHandler(
            OPS_LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        fh.setFormatter(logging.Formatter(_FMT, datefmt=_DATE_FMT))
        fh.setLevel(logging.DEBUG)
        logger.addHandler(fh)

    _init_db()
    _logger = logger
    return logger


def _init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        con = sqlite3.connect(str(DB_PATH), timeout=10)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("""
            CREATE TABLE IF NOT EXISTS ops_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          TEXT    NOT NULL,
                op_name     TEXT    NOT NULL,
                status      TEXT    NOT NULL DEFAULT 'ok',  -- ok|fail|start
                duration_ms INTEGER,
                message     TEXT,
                metadata    TEXT,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_ops_name ON ops_log(op_name)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_ops_ts   ON ops_log(ts)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_ops_status ON ops_log(status)")
        con.commit()
        con.close()
    except Exception:
        pass


def _write_db(op_name: str, status: str, duration_ms: int | None,
              message: str, metadata: dict) -> int:
    try:
        con = sqlite3.connect(str(DB_PATH), timeout=10)
        cur = con.execute(
            """INSERT INTO ops_log (ts, op_name, status, duration_ms, message, metadata)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                datetime.now().isoformat(timespec="milliseconds"),
                op_name,
                status,
                duration_ms,
                message[:500] if message else "",
                json.dumps(metadata, ensure_ascii=False, default=str) if metadata else None,
            ),
        )
        con.commit()
        row_id = int(cur.lastrowid or 0)
        con.close()
        return row_id
    except Exception:
        return 0


def log_op(op_name: str, *, ok: bool = True, duration_ms: int | None = None,
           message: str = "", **metadata: Any) -> None:
    """단발 작업 로그 기록."""
    logger = _init()
    status = "ok" if ok else "fail"
    meta_str = " | ".join(f"{k}={v}" for k, v in metadata.items()) if metadata else ""
    full_msg = f"{message}  {meta_str}".strip() if message or meta_str else "(완료)"
    if duration_ms is not None:
        full_msg = f"[{duration_ms}ms] {full_msg}"

    level = logging.INFO if ok else logging.WARNING
    logger.log(level, full_msg, extra={"op_name": op_name})
    _write_db(op_name, status, duration_ms, full_msg, metadata)


# ── 컨텍스트 매니저 ──────────────────────────────────────────────────

class _OpContext:
    def __init__(self, op_name: str, metadata: dict):
        self._op_name = op_name
        self._meta = metadata
        self._t0: float = 0.0
        self._extra: dict = {}
        self._ok: bool = True
        self._msg: str = ""

    def set_result(self, msg: str = "", ok: bool = True, **kwargs: Any) -> None:
        self._msg = msg
        self._ok = ok
        self._extra.update(kwargs)

    def __enter__(self) -> "_OpContext":
        self._t0 = time.perf_counter()
        logger = _init()
        logger.debug("시작", extra={"op_name": self._op_name})
        _write_db(self._op_name, "start", None,
                  "시작 " + " ".join(f"{k}={v}" for k, v in self._meta.items()),
                  self._meta)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        elapsed = int((time.perf_counter() - self._t0) * 1000)
        if exc_type is not None:
            self._ok = False
            self._msg = f"{exc_type.__name__}: {exc_val}"
        combined = {**self._meta, **self._extra}
        log_op(self._op_name, ok=self._ok, duration_ms=elapsed,
               message=self._msg, **combined)
        return False  # 예외 전파


@contextlib.contextmanager
def op_context(op_name: str, **metadata: Any) -> Generator[_OpContext, None, None]:
    """작업 컨텍스트 매니저."""
    ctx = _OpContext(op_name, metadata)
    ctx.__enter__()
    try:
        yield ctx
    except Exception as exc:
        ctx.__exit__(type(exc), exc, None)
        raise
    else:
        ctx.__exit__(None, None, None)


# ── 데코레이터 ────────────────────────────────────────────────────────

def op_logged(op_name: str, *, log_args: list[str] | None = None) -> Callable:
    """함수 실행을 op_log로 자동 기록하는 데코레이터.

    Args:
        op_name: 작업 이름
        log_args: 기록할 인자 이름 목록 (None이면 첫 번째 위치 인자만)
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            t0 = time.perf_counter()
            # 첫 번째 인자 또는 지정 인자 추출
            meta: dict[str, Any] = {}
            if log_args:
                import inspect
                sig = inspect.signature(fn)
                bound = sig.bind_partial(*args, **kwargs)
                bound.apply_defaults()
                for a in log_args:
                    if a in bound.arguments:
                        meta[a] = bound.arguments[a]
            elif args:
                meta["arg0"] = str(args[0])[:120]
            try:
                result = fn(*args, **kwargs)
                elapsed = int((time.perf_counter() - t0) * 1000)
                log_op(op_name, ok=True, duration_ms=elapsed, **meta)
                return result
            except Exception as exc:
                elapsed = int((time.perf_counter() - t0) * 1000)
                log_op(op_name, ok=False, duration_ms=elapsed,
                       message=f"{type(exc).__name__}: {exc}", **meta)
                raise
        return wrapper
    return decorator


# ── 조회 API ─────────────────────────────────────────────────────────

def query_recent(op_name: str | None = None, limit: int = 50,
                 status: str | None = None) -> list[dict]:
    """최근 작업 로그 조회."""
    _init_db()
    try:
        con = sqlite3.connect(str(DB_PATH), timeout=5)
        con.row_factory = sqlite3.Row
        clauses, params = ["1=1"], []
        if op_name:
            clauses.append("op_name LIKE ?")
            params.append(f"%{op_name}%")
        if status:
            clauses.append("status = ?")
            params.append(status)
        params.append(limit)
        rows = con.execute(
            f"SELECT * FROM ops_log WHERE {' AND '.join(clauses)} "
            f"ORDER BY id DESC LIMIT ?", params
        ).fetchall()
        con.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def query_stats(hours: int = 24) -> list[dict]:
    """최근 N시간 op_name별 통계."""
    _init_db()
    try:
        con = sqlite3.connect(str(DB_PATH), timeout=5)
        since = datetime.fromtimestamp(time.time() - hours * 3600).isoformat(timespec="seconds")
        rows = con.execute(
            """SELECT op_name,
                      COUNT(*) total,
                      SUM(CASE WHEN status='ok' THEN 1 ELSE 0 END) ok_cnt,
                      SUM(CASE WHEN status='fail' THEN 1 ELSE 0 END) fail_cnt,
                      ROUND(AVG(CASE WHEN duration_ms IS NOT NULL THEN duration_ms END),0) avg_ms
               FROM ops_log
               WHERE ts > ? AND status != 'start'
               GROUP BY op_name ORDER BY total DESC""",
            (since,),
        ).fetchall()
        con.close()
        return [{"op_name": r[0], "total": r[1], "ok": r[2], "fail": r[3], "avg_ms": r[4]}
                for r in rows]
    except Exception:
        return []

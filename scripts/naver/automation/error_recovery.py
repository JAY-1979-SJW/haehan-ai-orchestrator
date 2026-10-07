"""에러 자동 복구 + 통계 + 알림.

기능:
  - 함수 데코레이터로 에러 자동 캐치 + 재시도
  - 에러 분류 (네트워크/인증/UI/타임아웃)
  - 복구 전략 자동 선택
  - 에러 DB 저장 + 통계
  - 임계치 초과 시 알림 발송
"""

from __future__ import annotations

import functools
import sqlite3
import time
import traceback
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime

from ai_orchestrator.paths.runtime import data_dir
from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger
from scripts.common.sqlite_helpers import init_sqlite_schema

_log = get_logger(__name__)
DB_PATH = data_dir() / "cdp.db"


def _init_db():
    init_sqlite_schema(
        DB_PATH,
        (
            """
        CREATE TABLE IF NOT EXISTS error_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            function_name TEXT,
            category TEXT,
            error_msg TEXT,
            traceback TEXT,
            attempts INTEGER,
            recovered INTEGER,
            args_repr TEXT
        )
    """,
            "CREATE INDEX IF NOT EXISTS idx_err_ts ON error_log(ts)",
            "CREATE INDEX IF NOT EXISTS idx_err_cat ON error_log(category)",
        ),
    )


def categorize_error(exc: Exception) -> str:
    """에러 메시지에서 카테고리 추출."""
    msg = str(exc).lower()
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    if "network" in msg or "connection" in msg or "econnreset" in msg:
        return "network"
    if "not found" in msg or "no element" in msg or "locator" in msg:
        return "ui_element"
    if "login" in msg or "auth" in msg or "session" in msg:
        return "auth"
    if "permission" in msg or "forbidden" in msg:
        return "permission"
    return "unknown"


class ErrorRecovery:
    """에러 자동 복구 + 통계."""

    def __init__(self, page=None, notification_channels: list[str] | None = None):
        self.page = page
        self.notification_channels = notification_channels or ["console"]
        _init_db()

    def log_error(self, func_name: str, exc: Exception, attempts: int, recovered: bool, args_repr: str = "") -> None:
        category = categorize_error(exc)
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            """INSERT INTO error_log
               (ts, function_name, category, error_msg, traceback, attempts, recovered, args_repr)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now().isoformat(timespec="seconds"),
                func_name,
                category,
                str(exc)[:300],
                traceback.format_exc()[:2000],
                attempts,
                1 if recovered else 0,
                args_repr[:300],
            ),
        )
        conn.commit()
        conn.close()
        log_critical(
            "OTHER",
            f"에러 기록: {func_name} ({category})",
            func=func_name,
            error_category=category,
            recovered=recovered,
            mode="error_logged",
        )

    def with_retry(
        self,
        func: Callable,
        max_attempts: int = 3,
        delay_s: float = 1.0,
        backoff: float = 1.5,
        recovery_action: Callable | None = None,
    ) -> Callable:
        """함수 데코레이터 — 에러 발생 시 자동 재시도 + 복구 액션."""

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            attempt = 0
            while attempt < max_attempts:
                attempt += 1
                try:
                    result = func(*args, **kwargs)
                    if attempt > 1:
                        _log.info("[recovery] %s 복구 성공 (시도 %d)", func.__name__, attempt)
                    return result
                except Exception as e:  # noqa: BLE001 - 자동화 공용 오류복구 데코레이터 — 함수 실행 실패 시 카테고리 분류 후 재시도, 세션복구 시도 자체가 실패해도 무시하고 다음 재시도로 넘어감(복구 실패가 상위 예외 전파를 막지 않음)
                    last_exc = e
                    category = categorize_error(e)
                    _log.warning("[recovery] %s 실패 #%d (%s): %s", func.__name__, attempt, category, str(e)[:80])

                    if attempt < max_attempts:
                        # 카테고리별 복구 액션
                        if category == "auth" and self.page:
                            try:
                                from scripts.naver.automation.session_manager import SessionManager

                                sm = SessionManager(self.page)
                                sm.check_and_recover(force=True)
                            except Exception:  # noqa: BLE001 - 세션 복구 시도(SessionManager.check_and_recover 등) 실패는 무시하고 다음 재시도 루프로 진행 — 복구 실패해도 최종적으로 상위에서 예외가 다시 던져짐
                                pass
                        elif recovery_action:
                            with suppress(Exception):
                                recovery_action()
                        time.sleep(delay_s * (backoff ** (attempt - 1)))

            # 최종 실패
            self.log_error(
                func.__name__,
                last_exc,
                attempt,
                recovered=False,
                args_repr=f"args={args}, kwargs={list(kwargs.keys())}",
            )
            return {
                "ok": False,
                "error": str(last_exc)[:200],
                "attempts": attempt,
                "category": categorize_error(last_exc),
            }

        return wrapper

    def stats(self, days: int = 7) -> dict:
        """에러 통계 (최근 N일)."""
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT category, COUNT(*) count,
                      SUM(recovered) recovered,
                      AVG(attempts) avg_attempts
               FROM error_log
               WHERE ts >= datetime('now', ?, 'localtime')
               GROUP BY category
               ORDER BY count DESC""",
            (f"-{days} days",),
        ).fetchall()
        total = sum(r["count"] for r in rows)
        conn.close()
        return {
            "ok": True,
            "days": days,
            "total_errors": total,
            "by_category": [dict(r) for r in rows],
        }

    def check_alert_threshold(self, max_errors_per_hour: int = 10) -> dict:
        """임계치 초과 에러 발생 시 알림."""
        conn = sqlite3.connect(str(DB_PATH))
        cnt = conn.execute(
            "SELECT COUNT(*) FROM error_log WHERE ts >= datetime('now', '-1 hour', 'localtime')"
        ).fetchone()[0]
        conn.close()

        if cnt >= max_errors_per_hour:
            from scripts.naver.automation.integration.notification_hub import NotificationHub

            hub = NotificationHub(self.page)
            hub.notify(
                f"⚠ 에러 발생 임계치 초과: 최근 1시간 {cnt}건",
                channels=self.notification_channels,
                level="error",
            )
            log_critical(
                "OTHER",
                f"에러 임계치 초과: {cnt}/{max_errors_per_hour}",
                count=cnt,
                threshold=max_errors_per_hour,
                mode="error_threshold_alert",
            )
            return {"ok": True, "alerted": True, "count": cnt}
        return {"ok": True, "alerted": False, "count": cnt}

    def recent_errors(self, limit: int = 20, category: str | None = None) -> list[dict]:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        sql = "SELECT * FROM error_log"
        args: list[str | int] = []
        if category:
            sql += " WHERE category = ?"
            args.append(category)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        rows = conn.execute(sql, args).fetchall()
        conn.close()
        return [dict(r) for r in rows]

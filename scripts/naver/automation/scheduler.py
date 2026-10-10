"""정기 실행 스케줄러 — 작업 등록 + 시간 기반 실행.

지원:
  - cron 표현식 (시간 기반)
  - interval (N분마다)
  - 일회성 (specific datetime)

DB: data/cdp.db.scheduled_tasks

사용:
  from scripts.naver.automation.scheduler import Scheduler
  sch = Scheduler()
  sch.add_task("daily_inventory", "0 9 * * *",  # 매일 9시
               "scripts.naver.smartstore.automation.inventory_monitor:InventoryMonitor.check_low_stock")
  sch.start()  # 백그라운드 루프
"""

from __future__ import annotations

import importlib
import json
import sqlite3
import threading
from datetime import datetime
from typing import Any

from ai_orchestrator.paths.runtime import data_dir
from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger
from scripts.common.sqlite_helpers import execute_one_change

_log = get_logger(__name__)
DB_PATH = data_dir() / "cdp.db"


def _init_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            kind TEXT NOT NULL,  -- 'cron' | 'interval' | 'once'
            cron_expr TEXT,
            interval_s INTEGER,
            run_at TEXT,
            module TEXT NOT NULL,
            callable TEXT NOT NULL,
            args_json TEXT,
            enabled INTEGER DEFAULT 1,
            last_run TEXT,
            last_result TEXT,
            run_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def _parse_cron_minute(cron: str, now: datetime) -> bool:
    """간단한 cron 매처 (분 정밀도). 예: '0 9 * * *' = 매일 9시 0분."""
    parts = cron.split()
    if len(parts) != 5:
        return False
    minute, hour, day, month, weekday = parts

    def match(field, val):
        if field == "*":
            return True
        if "," in field:
            return str(val) in field.split(",")
        if "/" in field:
            base, step = field.split("/")
            base_val = 0 if base == "*" else int(base)
            return (val - base_val) % int(step) == 0
        if "-" in field:
            a, b = field.split("-")
            return int(a) <= val <= int(b)
        return str(val) == field

    return (
        match(minute, now.minute)
        and match(hour, now.hour)
        and match(day, now.day)
        and match(month, now.month)
        and match(weekday, now.isoweekday() % 7)
    )


class Scheduler:
    """경량 cron 스케줄러."""

    def __init__(self):
        _init_db()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def add_task(self, name: str, schedule: str, target: str, args: dict | None = None) -> dict:
        """작업 등록.

        Args:
            name: 고유 이름
            schedule: cron 표현식 ("0 9 * * *") 또는 "every 5m" 또는 ISO datetime
            target: "module.path:callable" 또는 "module.path:Class.method"
            args: 호출 args (kwargs)
        """
        kind = "cron"
        cron_expr: str | None = schedule
        interval_s = None
        run_at = None

        if schedule.startswith("every "):
            kind = "interval"
            unit_str = schedule[6:].strip()
            num = int("".join(c for c in unit_str if c.isdigit()) or 60)
            if unit_str.endswith("m"):
                interval_s = num * 60
            elif unit_str.endswith("h"):
                interval_s = num * 3600
            elif unit_str.endswith("s"):
                interval_s = num
            else:
                interval_s = num * 60
            cron_expr = None
        elif "T" in schedule:  # ISO
            kind = "once"
            run_at = schedule
            cron_expr = None

        if ":" not in target:
            return {"ok": False, "error": "target must be 'module:callable'"}
        module, callable_name = target.split(":", 1)

        conn = sqlite3.connect(str(DB_PATH))
        try:
            conn.execute(
                """INSERT OR REPLACE INTO scheduled_tasks
                   (name, kind, cron_expr, interval_s, run_at, module, callable, args_json, enabled)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (
                    name,
                    kind,
                    cron_expr,
                    interval_s,
                    run_at,
                    module,
                    callable_name,
                    json.dumps(args or {}, ensure_ascii=False),
                ),
            )
            conn.commit()
            log_critical(
                "OTHER", f"스케줄 작업 등록: {name}", name=name, kind=kind, target=target, mode="scheduler_add"
            )
            return {"ok": True, "name": name, "kind": kind}
        finally:
            conn.close()

    def list_tasks(self) -> list[dict]:
        _init_db()
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM scheduled_tasks ORDER BY id").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def remove_task(self, name: str) -> dict:
        return execute_one_change(DB_PATH, "DELETE FROM scheduled_tasks WHERE name = ?", (name,))

    def _should_run(self, task: dict, now: datetime) -> bool:
        if not task.get("enabled"):
            return False
        kind = task.get("kind")
        last_run = task.get("last_run")
        if kind == "cron":
            if not _parse_cron_minute(task["cron_expr"], now):
                return False
            # 같은 분에 중복 실행 방지
            if last_run:
                last = datetime.fromisoformat(last_run)
                if last.replace(second=0, microsecond=0) == now.replace(second=0, microsecond=0):
                    return False
            return True
        if kind == "interval":
            if not last_run:
                return True
            last = datetime.fromisoformat(last_run)
            return (now - last).total_seconds() >= task["interval_s"]
        if kind == "once":
            if last_run:
                return False
            target_time = datetime.fromisoformat(task["run_at"])
            return now >= target_time
        return False

    def _execute(self, task: dict) -> dict:
        try:
            mod = importlib.import_module(task["module"])
            callable_path = task["callable"]
            args = json.loads(task.get("args_json") or "{}")
            obj: Any = mod
            for part in callable_path.split("."):
                obj = getattr(obj, part)
            # 클래스 메서드일 경우 — 인스턴스 생성 필요
            if isinstance(obj, type) or "." in callable_path:
                # Class.method 형식이면 인스턴스 생성
                if "." in callable_path:
                    class_name, method_name = callable_path.rsplit(".", 1)
                    cls = getattr(mod, class_name)
                    instance = cls()
                    result = getattr(instance, method_name)(**args)
                else:
                    result = obj(**args)
            else:
                result = obj(**args)
            return {"ok": True, "result": str(result)[:500]}
        except Exception as e:  # noqa: BLE001 - 등록된 작업 실행 결과를 ok/error dict로 캡처, tick 루프 내 오류는 로깅 후 다음 tick에서 계속 — 성공 위장 없음
            return {"ok": False, "error": str(e)[:200]}

    def tick(self) -> list[dict]:
        """1회 실행 — 등록된 작업 중 실행 시점 도래한 것 처리."""
        now = datetime.now()
        executed = []
        updates: list[tuple[str, str, int]] = []
        for task in self.list_tasks():
            if self._should_run(task, now):
                _log.info("[scheduler] 실행: %s", task["name"])
                result = self._execute(task)
                updates.append(
                    (now.isoformat(timespec="seconds"), json.dumps(result, ensure_ascii=False)[:1000], task["id"])
                )
                executed.append({"task": task["name"], "result": result})
                log_critical(
                    "OTHER",
                    f"스케줄 실행: {task['name']}",
                    name=task["name"],
                    ok=result.get("ok"),
                    mode="scheduler_run",
                )
        if updates:  # 결과 저장 — 연결 한 번에 모아서(EFF-03: 반복문 안 sqlite3.connect 금지)
            conn = sqlite3.connect(str(DB_PATH))
            try:
                conn.executemany(
                    """UPDATE scheduled_tasks
                       SET last_run = ?, last_result = ?, run_count = run_count + 1
                       WHERE id = ?""",
                    updates,
                )
                conn.commit()
            finally:
                conn.close()
        return executed

    def start(self, interval_s: int = 60) -> None:
        """백그라운드 루프 시작 (별도 스레드)."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()

        def loop():
            while not self._stop.is_set():
                try:
                    self.tick()
                except Exception as e:  # noqa: BLE001 - 등록된 작업 실행 결과를 ok/error dict로 캡처, tick 루프 내 오류는 로깅 후 다음 tick에서 계속 — 성공 위장 없음
                    _log.error("[scheduler] tick 오류: %s", e)
                self._stop.wait(interval_s)

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()
        _log.info("[scheduler] 시작 (interval %ds)", interval_s)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

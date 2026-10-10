"""SQLite 단발 실행 공용 함수(표준 라이브러리만) — 스키마 초기화·변경 1건 실행.

naver 자동화 모듈들의 _init_db(테이블·인덱스 CREATE IF NOT EXISTS)와
Scheduler.remove_task·BlogSchedule.cancel(변경 1건 + 영향 행 여부)이 SQL 만 다르게
똑같이 복사해 쓰던 "연결 → 실행 → commit → close" 본문을 한 곳으로 모았다.
DB 경로는 호출 시점에 넘긴다(시험이 각 모듈 DB_PATH 를 바꿔 끼우는 방식 유지).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any


def init_sqlite_schema(db_path: str | Path, statements: Iterable[str]) -> None:
    """db_path 에 연결해 statements(CREATE TABLE/INDEX IF NOT EXISTS …)를 차례로 실행하고 commit 한다."""
    conn = sqlite3.connect(str(db_path))
    for sql in statements:
        conn.execute(sql)
    conn.commit()
    conn.close()


def execute_one_change(db_path: str | Path, sql: str, params: Sequence[Any]) -> dict:
    """변경 SQL 1건(UPDATE/DELETE)을 실행·commit 하고 {"ok": 영향 행이 1개 이상인지} 를 돌려준다."""
    conn = sqlite3.connect(str(db_path))
    cur = conn.execute(sql, params)
    conn.commit()
    conn.close()
    return {"ok": cur.rowcount > 0}

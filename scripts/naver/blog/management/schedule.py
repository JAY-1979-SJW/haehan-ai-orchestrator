"""블로그 예약 발행 관리.

기능:
  - 예약 발행 일정 등록
  - 임시저장 → 예약 발행 전환
  - 예약 일정 시간 조정
  - DB 기반 예약 큐
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import Page

from ai_orchestrator.paths.runtime import data_dir
from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger
from scripts.common.sqlite_helpers import execute_one_change, init_sqlite_schema

_log = get_logger(__name__)
ROOT = Path(__file__).resolve().parents[4]
DB_PATH = data_dir() / "cdp.db"


def _init_db():
    init_sqlite_schema(
        DB_PATH,
        (
            """
        CREATE TABLE IF NOT EXISTS blog_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scheduled_at TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT,
            tags TEXT,
            category TEXT,
            visibility TEXT DEFAULT 'public',
            status TEXT DEFAULT 'pending',
            published_url TEXT,
            published_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """,
            "CREATE INDEX IF NOT EXISTS idx_blogsch_at ON blog_schedule(scheduled_at)",
        ),
    )


class BlogSchedule:
    """블로그 예약 발행 큐."""

    def __init__(self, page: Page):
        self.page = page
        _init_db()

    def queue(
        self,
        scheduled_at: datetime,
        title: str,
        body: str,
        tags: list[str] | None = None,
        category: str | None = None,
        visibility: str = "public",
    ) -> dict:
        """예약 등록."""
        import json

        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.execute(
            """INSERT INTO blog_schedule
               (scheduled_at, title, body, tags, category, visibility)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                scheduled_at.isoformat(timespec="seconds"),
                title,
                body,
                json.dumps(tags or [], ensure_ascii=False),
                category,
                visibility,
            ),
        )
        conn.commit()
        sid = cur.lastrowid
        conn.close()
        log_critical(
            "OTHER",
            f"블로그 예약 등록: {title[:30]}",
            title=title,
            at=scheduled_at.isoformat(),
            mode="blog_schedule_queue",
        )
        return {"ok": True, "id": sid, "scheduled_at": scheduled_at.isoformat()}

    def list_pending(self, days_ahead: int = 30) -> list[dict]:
        """발행 대기 중인 예약 목록."""
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        until = (datetime.now() + timedelta(days=days_ahead)).isoformat(timespec="seconds")
        rows = conn.execute(
            """SELECT * FROM blog_schedule
               WHERE status = 'pending' AND scheduled_at <= ?
               ORDER BY scheduled_at""",
            (until,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def process_due(self, approval: str | None = None) -> dict:
        """예약 시간 도래한 글 자동 발행. approval 은 사용자가 직접 입력한 승인 문구(없으면 GateBlocked)."""
        import json

        from scripts.common.gate import require_approved

        require_approved("blog_publish", approval, via="blog_schedule_process_due")

        now = datetime.now().isoformat(timespec="seconds")
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM blog_schedule WHERE status = 'pending' AND scheduled_at <= ?",
            (now,),
        ).fetchall()
        conn.close()

        results = []
        from scripts.naver.blog.writer import BlogWriter

        for row in rows:
            row = dict(row)
            bw = BlogWriter(self.page)
            r = {"id": row["id"], "title": row["title"]}
            try:
                bw.open()
                bw.set_title(row["title"])
                bw.write_body(row["body"] or "")
                if row.get("tags"):
                    bw.set_tags(json.loads(row["tags"]))
                pr = bw.publish(wait_verify_s=8)
                # DB 업데이트
                conn = sqlite3.connect(str(DB_PATH))
                conn.execute(
                    """UPDATE blog_schedule
                       SET status = ?, published_url = ?, published_at = ?
                       WHERE id = ?""",
                    (
                        "published" if pr.get("ok") else "failed",
                        pr.get("url"),
                        datetime.now().isoformat(timespec="seconds"),
                        row["id"],
                    ),
                )
                conn.commit()
                conn.close()
                r["result"] = pr
                log_critical(
                    "OTHER",
                    f"예약 발행: {row['title'][:30]}",
                    id=row["id"],
                    ok=pr.get("ok"),
                    mode="blog_schedule_publish",
                )
            except Exception as e:  # noqa: BLE001 - 블로그 예약발행 실행 루프 - 개별 예약 항목 처리 실패는 error 필드에 기록 후 다음 항목 계속 진행, 실제 발행 자체는 이 except 밖의 별도 publish 호출/게이트가 담당
                r["error"] = str(e)[:200]
            results.append(r)
        return {"ok": True, "processed": len(results), "results": results}

    def cancel(self, schedule_id: int) -> dict:
        return execute_one_change(DB_PATH, "UPDATE blog_schedule SET status = 'cancelled' WHERE id = ?", (schedule_id,))

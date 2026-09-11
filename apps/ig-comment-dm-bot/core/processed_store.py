"""이미 DM 발송한 댓글 ID 기록 — 동일 댓글에 중복 DM을 보내지 않도록 방지."""

from __future__ import annotations

import sqlite3

from core.app_paths import get_data_dir

_DB_PATH = get_data_dir() / "processed_comments.db"


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS processed_comments (
            comment_id TEXT PRIMARY KEY,
            keyword TEXT,
            processed_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    return conn


def is_processed(comment_id: str) -> bool:
    with _connect() as conn:
        row = conn.execute("SELECT 1 FROM processed_comments WHERE comment_id = ?", (comment_id,)).fetchone()
        return row is not None


def mark_processed(comment_id: str, keyword: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO processed_comments (comment_id, keyword) VALUES (?, ?)",
            (comment_id, keyword),
        )

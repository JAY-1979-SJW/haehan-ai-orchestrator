"""gonobi 수집 결과 DB (stdlib sqlite3, L7 Persistence).

테이블:
  gonobi_posts  — 포스트 메타 + 본문
  gonobi_images — 이미지 URL 목록
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ai_orchestrator.paths.runtime import data_dir

_DEFAULT_DB = data_dir() / "gonobi.db"  # 예전 parents[5] 는 저장소 밖(상위 폴더)이었다 — 번들·데스크톱에서 data_dir 로

DDL_POSTS = """
CREATE TABLE IF NOT EXISTS gonobi_posts (
    log_no          TEXT PRIMARY KEY,
    category_no     TEXT NOT NULL,
    category_name   TEXT NOT NULL,
    our_category    TEXT NOT NULL DEFAULT '',
    url             TEXT NOT NULL,
    title           TEXT NOT NULL DEFAULT '',
    body            TEXT NOT NULL DEFAULT '',
    tags            TEXT NOT NULL DEFAULT '',
    written_at      TEXT NOT NULL DEFAULT '',
    collected_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
)
"""

DDL_IMAGES = """
CREATE TABLE IF NOT EXISTS gonobi_images (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    log_no      TEXT NOT NULL,
    image_url   TEXT NOT NULL,
    UNIQUE(log_no, image_url)
)
"""


@contextmanager
def open_db(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    p = path or _DEFAULT_DB
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(DDL_POSTS)
        conn.execute(DDL_IMAGES)
        conn.commit()
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def upsert_post(conn: sqlite3.Connection, post: dict) -> bool:
    """포스트 저장(신규) 또는 업데이트. 신규면 True 반환."""
    existing = conn.execute("SELECT log_no FROM gonobi_posts WHERE log_no=?", (post["log_no"],)).fetchone()

    import json

    tags_str = json.dumps(post.get("tags", []), ensure_ascii=False)

    if existing:
        conn.execute(
            """UPDATE gonobi_posts SET title=?, body=?, tags=?, written_at=?,
               our_category=?, collected_at=datetime('now','localtime')
               WHERE log_no=?""",
            (
                post.get("title", ""),
                post.get("body", ""),
                tags_str,
                post.get("written_at", ""),
                post.get("our_category", ""),
                post["log_no"],
            ),
        )
        return False

    conn.execute(
        """INSERT INTO gonobi_posts
           (log_no, category_no, category_name, our_category, url, title, body, tags, written_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            post["log_no"],
            post.get("category_no", ""),
            post.get("category_name", ""),
            post.get("our_category", ""),
            post.get("url", ""),
            post.get("title", ""),
            post.get("body", ""),
            tags_str,
            post.get("written_at", ""),
        ),
    )
    return True


def upsert_images(conn: sqlite3.Connection, log_no: str, images: list[str]) -> int:
    """이미지 URL 저장. 추가된 건수 반환."""
    added = 0
    for url in images:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO gonobi_images (log_no, image_url) VALUES (?,?)",
                (log_no, url),
            )
            if conn.execute("SELECT changes()").fetchone()[0]:
                added += 1
        except Exception:  # noqa: BLE001 - SQLite 트랜잭션 컨텍스트 매니저 - 예외 발생 시 rollback() 후 raise로 그대로 재발생시켜 예외를 삼키지 않음(운영 DB 스키마 변경이 아닌 gonobi_posts 캐시 테이블 트랜잭션), pass-only 두번째 except는 중복 삽입 등 단건 실패를 skip하는 카운팅 루프
            pass
    return added


def get_posts(conn: sqlite3.Connection, our_category: str = "", limit: int = 100, offset: int = 0) -> list[dict]:
    q = "SELECT * FROM gonobi_posts"
    params: list = []
    if our_category:
        q += " WHERE our_category=?"
        params.append(our_category)
    q += " ORDER BY collected_at DESC LIMIT ? OFFSET ?"
    params += [limit, offset]
    return [dict(r) for r in conn.execute(q, params).fetchall()]


def get_post(conn: sqlite3.Connection, log_no: str) -> dict | None:
    row = conn.execute("SELECT * FROM gonobi_posts WHERE log_no=?", (log_no,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["images"] = [
        r["image_url"] for r in conn.execute("SELECT image_url FROM gonobi_images WHERE log_no=?", (log_no,)).fetchall()
    ]
    return d


def reclassify_untagged(conn: sqlite3.Connection, limit: int = 100) -> int:
    """our_category가 비어있는 포스트를 키워드 규칙으로 재분류. 업데이트 건수 반환."""
    from .classifier import classify_post

    rows = conn.execute(
        "SELECT log_no, title, body FROM gonobi_posts WHERE our_category='' LIMIT ?",
        (limit,),
    ).fetchall()
    updated = 0
    for row in rows:
        cat = classify_post(row["title"], row["body"])
        conn.execute(
            "UPDATE gonobi_posts SET our_category=? WHERE log_no=?",
            (cat, row["log_no"]),
        )
        updated += 1
    conn.commit()
    return updated


def count_posts(conn: sqlite3.Connection) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM gonobi_posts").fetchone()[0]
    by_cat = conn.execute("SELECT our_category, COUNT(*) as cnt FROM gonobi_posts GROUP BY our_category").fetchall()
    return {"total": total, "by_category": {r["our_category"]: r["cnt"] for r in by_cat}}

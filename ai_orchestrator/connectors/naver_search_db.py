"""네이버 검색 수집 결과 DB 적재 (stdlib sqlite3).

방침:
- 프로젝트의 기존 영속 저장 패턴이 JSONL flat-file 이므로, 여기도 외부 의존성
  없이 stdlib `sqlite3` 만 사용한다. SQLAlchemy/ORM 도입하지 않는다.
- 중복 방지는 UNIQUE 인덱스 + ``INSERT OR IGNORE`` 로 구현.
  * blog: link UNIQUE
  * shopping: product_id UNIQUE — product_id 공란이면 insert 대상에서 제외(WARN)
- 쓰기 경로는 Jobs 레이어가 live + 기능 플래그 on 일 때만 호출한다.
- 본 모듈은 네트워크 / 시크릿 / 세션과 무관 — 민감정보 로그 없음.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ai_orchestrator.paths.runtime import data_dir

logger = logging.getLogger(__name__)


TABLE_BLOG = "naver_blog_posts"
TABLE_SHOP = "naver_shopping_items"


_BLOG_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {TABLE_BLOG} (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    query          TEXT NOT NULL,
    title          TEXT NOT NULL DEFAULT '',
    link           TEXT NOT NULL UNIQUE,
    blogger_name   TEXT NOT NULL DEFAULT '',
    blogger_link   TEXT NOT NULL DEFAULT '',
    description    TEXT NOT NULL DEFAULT '',
    post_date      TEXT NOT NULL DEFAULT '',
    collected_at   TEXT NOT NULL,
    source         TEXT NOT NULL DEFAULT 'naver_blog'
);
CREATE INDEX IF NOT EXISTS ix_{TABLE_BLOG}_query     ON {TABLE_BLOG}(query);
CREATE INDEX IF NOT EXISTS ix_{TABLE_BLOG}_post_date ON {TABLE_BLOG}(post_date);
"""

_SHOP_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {TABLE_SHOP} (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    query          TEXT NOT NULL,
    title          TEXT NOT NULL DEFAULT '',
    link           TEXT NOT NULL DEFAULT '',
    image          TEXT NOT NULL DEFAULT '',
    lprice         INTEGER,
    hprice         INTEGER,
    mall_name      TEXT NOT NULL DEFAULT '',
    product_id     TEXT NOT NULL UNIQUE,
    product_type   TEXT NOT NULL DEFAULT '',
    brand          TEXT NOT NULL DEFAULT '',
    maker          TEXT NOT NULL DEFAULT '',
    category1      TEXT NOT NULL DEFAULT '',
    category2      TEXT NOT NULL DEFAULT '',
    category3      TEXT NOT NULL DEFAULT '',
    category4      TEXT NOT NULL DEFAULT '',
    collected_at   TEXT NOT NULL,
    source         TEXT NOT NULL DEFAULT 'naver_shop'
);
CREATE INDEX IF NOT EXISTS ix_{TABLE_SHOP}_query  ON {TABLE_SHOP}(query);
CREATE INDEX IF NOT EXISTS ix_{TABLE_SHOP}_lprice ON {TABLE_SHOP}(lprice);
"""


@dataclass
class InsertStats:
    inserted_count: int = 0
    duplicate_count: int = 0
    skipped_count: int = 0  # unique 키 공란 등 insert 대상 제외
    # 3단계 증분용 — 호출자가 consecutive duplicate 를 페이지 경계 넘어 추적할 때 사용.
    consecutive_duplicates: int = 0  # 이 호출이 종료될 때의 연속 duplicate 카운터.
    stopped_early: bool = False  # threshold 에 걸려서 조기 종료됐는지.

    def to_dict(self) -> dict:
        return {
            "inserted_count": self.inserted_count,
            "duplicate_count": self.duplicate_count,
            "skipped_count": self.skipped_count,
            "consecutive_duplicates": self.consecutive_duplicates,
            "stopped_early": self.stopped_early,
        }


# ── env / 경로 ──────────────────────────────────────────────────
def is_db_enabled() -> bool:
    v = os.environ.get("NAVER_SEARCH_DB_ENABLED", "").strip().lower()
    return v in {"1", "true", "yes", "on"}


def default_db_path() -> Path:
    override = os.environ.get("NAVER_SEARCH_DB_PATH", "").strip()
    if override:
        return Path(override)
    # ai_orchestrator/connectors/X.py → repo root /data/naver_search.db
    return data_dir() / "naver_search.db"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ── 연결 + 스키마 ───────────────────────────────────────────────
@contextmanager
def open_db(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """sqlite 연결 + 스키마 초기화. 호출자가 commit/rollback 을 관리할 필요 없음
    (컨텍스트 종료 시 commit, 예외 시 rollback)."""
    p = path or default_db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        with conn:  # transaction
            conn.executescript(_BLOG_SCHEMA)
            conn.executescript(_SHOP_SCHEMA)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def count_rows(conn: sqlite3.Connection, table: str) -> int:
    if table not in (TABLE_BLOG, TABLE_SHOP):
        raise ValueError(f"unknown table: {table!r}")
    cur = conn.execute(f"SELECT COUNT(*) FROM {table}")  # nosec B608 - 테이블명은 모듈 상수, 조건/정렬은 고정 조각이고 값은 ? 바인딩(사용자 입력 미결합)
    row = cur.fetchone()
    return int(row[0]) if row else 0


# ── INSERT (중복 방지) ──────────────────────────────────────────
_BLOG_COLS = (
    "query",
    "title",
    "link",
    "blogger_name",
    "blogger_link",
    "description",
    "post_date",
    "collected_at",
    "source",
)
_SHOP_COLS = (
    "query",
    "title",
    "link",
    "image",
    "lprice",
    "hprice",
    "mall_name",
    "product_id",
    "product_type",
    "brand",
    "maker",
    "category1",
    "category2",
    "category3",
    "category4",
    "collected_at",
    "source",
)


def _cur_changes(conn: sqlite3.Connection) -> int:
    cur = conn.execute("SELECT changes()")
    row = cur.fetchone()
    return int(row[0]) if row else 0


def insert_blog_items(
    conn: sqlite3.Connection,
    query: str,
    items: Iterable[dict],
    *,
    collected_at: str | None = None,
) -> InsertStats:
    """blog 결과를 link 기준 UNIQUE 로 적재.

    link 공란 항목은 skipped 처리 (WARN 로그).
    """
    ts = collected_at or _utc_now_iso()
    stats = InsertStats()
    cols_csv = ", ".join(_BLOG_COLS)
    placeholders = ", ".join("?" for _ in _BLOG_COLS)
    sql = f"INSERT OR IGNORE INTO {TABLE_BLOG} ({cols_csv}) VALUES ({placeholders})"

    for it in items:
        link = (it.get("link") or "").strip()
        if not link:
            stats.skipped_count += 1
            logger.warning("[NAVER-BLOG-DB-SKIP] reason=missing_link")
            continue
        values = (
            query,
            (it.get("title") or "").strip(),
            link,
            (it.get("blogger_name") or "").strip(),
            (it.get("blogger_link") or "").strip(),
            (it.get("description") or "").strip(),
            (it.get("post_date") or "").strip(),
            ts,
            (it.get("source") or "naver_blog"),
        )
        conn.execute(sql, values)
        if _cur_changes(conn) > 0:
            stats.inserted_count += 1
        else:
            stats.duplicate_count += 1
    return stats


def insert_shopping_items(
    conn: sqlite3.Connection,
    query: str,
    items: Iterable[dict],
    *,
    collected_at: str | None = None,
    stop_after_consecutive_duplicates: int | None = None,
    consecutive_duplicates_start: int = 0,
) -> InsertStats:
    """shopping 결과를 product_id 기준 UNIQUE 로 적재.

    product_id 공란 항목은 skipped 처리 (WARN 로그) — 임의 해시 키 생성 금지.

    increments / resets:
        - INSERT 성공 → consecutive 리셋 (0)
        - UNIQUE 충돌(duplicate) → consecutive += 1
        - product_id 공란(skipped) → consecutive 유지 (중립 이벤트)

    조기 종료:
        stop_after_consecutive_duplicates 가 주어지고 연속 duplicate 가 그 값에
        도달하면 남은 items 는 건너뛰고 즉시 반환. `stats.stopped_early=True`.
        호출자는 `stats.consecutive_duplicates` 를 다음 페이지 호출 시
        `consecutive_duplicates_start` 로 넘겨서 경계를 이어간다.
    """
    ts = collected_at or _utc_now_iso()
    stats = InsertStats()
    cols_csv = ", ".join(_SHOP_COLS)
    placeholders = ", ".join("?" for _ in _SHOP_COLS)
    sql = f"INSERT OR IGNORE INTO {TABLE_SHOP} ({cols_csv}) VALUES ({placeholders})"
    consecutive = int(max(0, consecutive_duplicates_start))

    for it in items:
        pid = (it.get("product_id") or "").strip()
        if not pid:
            stats.skipped_count += 1
            logger.warning("[NAVER-SHOPPING-DB-SKIP] reason=missing_product_id")
            continue
        values = (
            query,
            (it.get("title") or "").strip(),
            (it.get("link") or "").strip(),
            (it.get("image") or "").strip(),
            it.get("lprice") if isinstance(it.get("lprice"), int) else None,
            it.get("hprice") if isinstance(it.get("hprice"), int) else None,
            (it.get("mall_name") or "").strip(),
            pid,
            (it.get("product_type") or "").strip(),
            (it.get("brand") or "").strip(),
            (it.get("maker") or "").strip(),
            (it.get("category1") or "").strip(),
            (it.get("category2") or "").strip(),
            (it.get("category3") or "").strip(),
            (it.get("category4") or "").strip(),
            ts,
            (it.get("source") or "naver_shop"),
        )
        conn.execute(sql, values)
        if _cur_changes(conn) > 0:
            stats.inserted_count += 1
            consecutive = 0
        else:
            stats.duplicate_count += 1
            consecutive += 1
            if stop_after_consecutive_duplicates is not None and consecutive >= stop_after_consecutive_duplicates:
                stats.consecutive_duplicates = consecutive
                stats.stopped_early = True
                return stats

    stats.consecutive_duplicates = consecutive
    return stats


__all__ = [
    "TABLE_BLOG",
    "TABLE_SHOP",
    "InsertStats",
    "count_rows",
    "default_db_path",
    "insert_blog_items",
    "insert_shopping_items",
    "is_db_enabled",
    "open_db",
]

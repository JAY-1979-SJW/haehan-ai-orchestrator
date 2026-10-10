"""Naver 검색 DB read-only 조회 레이어.

FastAPI 라우터와 운영 점검 스크립트에서 공통으로 사용한다.
- stdlib sqlite3 만 사용 (기존 프로젝트 의존성 철학 유지).
- 쓰기 없음. 스키마 변경 없음.
- DB 파일이 존재하지 않으면 모든 함수가 안전한 fallback 값을 반환한다
  (임의 파일 생성 금지).
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.naver.shopping import naver_search_db as db_mod

logger = logging.getLogger(__name__)


# ── 정렬 허용 값 ────────────────────────────────────────────────
SHOP_SORT_COLLECTED_DESC = "collected_at_desc"
SHOP_SORT_LPRICE_ASC = "lprice_asc"
SHOP_SORT_LPRICE_DESC = "lprice_desc"
SHOP_SORT_ALLOWED = {
    SHOP_SORT_COLLECTED_DESC,
    SHOP_SORT_LPRICE_ASC,
    SHOP_SORT_LPRICE_DESC,
}


# ── 공통 헬퍼 ──────────────────────────────────────────────────
def _resolve_db_path(db_path: Path | None) -> Path:
    return db_path or db_mod.default_db_path()


def _readonly_connect(path: Path) -> sqlite3.Connection | None:
    """파일이 있을 때만 연결. 없으면 None.

    sqlite 의 URI 모드(`file:...?mode=ro`)로 열어 쓰기 시도 자체를 차단한다.
    """
    if not path.is_file():
        return None
    try:
        uri = f"file:{path.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.warning("[NAVER-QUERIES-CONNECT-FAIL] err=%s", type(e).__name__)
        return None


def _clamp(v: int | None, lo: int, hi: int, default: int) -> int:
    try:
        i = int(v) if v is not None else default
    except (TypeError, ValueError):
        i = default
    return max(lo, min(i, hi))


# ── blog 조회 ──────────────────────────────────────────────────
_BLOG_SELECT_COLS = (
    "query",
    "title",
    "link",
    "blogger_name",
    "post_date",
    "collected_at",
    "source",
)


@dataclass
class QueryPage:
    total: int
    items: list
    limit: int
    offset: int

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "items": self.items,
            "limit": self.limit,
            "offset": self.offset,
        }


def search_blog_posts(
    *,
    db_path: Path | None = None,
    query: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> QueryPage:
    """naver_blog_posts 에서 read-only 조회.

    post_date 가 비어 있는 행은 NULLS LAST 형태로 뒤로 보낸다.
    2차 정렬: collected_at DESC.
    """
    lim = _clamp(limit, 1, 200, 50)
    off = _clamp(offset, 0, 10_000_000, 0)
    path = _resolve_db_path(db_path)
    conn = _readonly_connect(path)
    if conn is None:
        return QueryPage(total=0, items=[], limit=lim, offset=off)
    try:
        where: list[str] = []
        params: list[Any] = []
        if query:
            where.append("query = ?")
            params.append(query)
        if date_from:
            where.append("post_date >= ?")
            params.append(date_from)
        if date_to:
            where.append("post_date <= ?")
            params.append(date_to)
        where_sql = (" WHERE " + " AND ".join(where)) if where else ""

        total_row = conn.execute(
            f"SELECT COUNT(*) FROM {db_mod.TABLE_BLOG}{where_sql}",  # nosec B608 - 테이블명은 모듈 상수, 조건/정렬은 고정 조각이고 값은 ? 바인딩(사용자 입력 미결합)
            tuple(params),
        ).fetchone()
        total = int(total_row[0]) if total_row else 0

        cols_csv = ", ".join(_BLOG_SELECT_COLS)
        rows = conn.execute(
            f"SELECT {cols_csv} FROM {db_mod.TABLE_BLOG}{where_sql} "  # nosec B608 - 테이블명은 모듈 상수, 조건/정렬은 고정 조각이고 값은 ? 바인딩(사용자 입력 미결합)
            f"ORDER BY CASE WHEN post_date IS NULL OR post_date = '' THEN 1 ELSE 0 END, "
            f"post_date DESC, collected_at DESC "
            f"LIMIT ? OFFSET ?",
            tuple(params) + (lim, off),  # noqa: RUF005
        ).fetchall()
        items = [dict(r) for r in rows]
        return QueryPage(total=total, items=items, limit=lim, offset=off)
    finally:
        conn.close()


# ── shopping 조회 ──────────────────────────────────────────────
_SHOP_SELECT_COLS = (
    "query",
    "title",
    "link",
    "lprice",
    "hprice",
    "mall_name",
    "brand",
    "maker",
    "product_id",
    "collected_at",
    "source",
)


def search_shopping_items(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수, 인자 묶음 변경 시 API 영향)
    *,
    db_path: Path | None = None,
    query: str | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    brand: str | None = None,
    mall_name: str | None = None,
    sort: str = SHOP_SORT_COLLECTED_DESC,
    limit: int = 50,
    offset: int = 0,
) -> QueryPage:
    lim = _clamp(limit, 1, 200, 50)
    off = _clamp(offset, 0, 10_000_000, 0)
    sort_key = sort if sort in SHOP_SORT_ALLOWED else SHOP_SORT_COLLECTED_DESC
    path = _resolve_db_path(db_path)
    conn = _readonly_connect(path)
    if conn is None:
        return QueryPage(total=0, items=[], limit=lim, offset=off)
    try:
        where: list[str] = []
        params: list[Any] = []
        if query:
            where.append("query = ?")
            params.append(query)
        if min_price is not None:
            where.append("lprice IS NOT NULL AND lprice >= ?")
            params.append(int(min_price))
        if max_price is not None:
            where.append("lprice IS NOT NULL AND lprice <= ?")
            params.append(int(max_price))
        if brand:
            where.append("brand = ?")
            params.append(brand)
        if mall_name:
            where.append("mall_name = ?")
            params.append(mall_name)
        where_sql = (" WHERE " + " AND ".join(where)) if where else ""

        total_row = conn.execute(
            f"SELECT COUNT(*) FROM {db_mod.TABLE_SHOP}{where_sql}",  # nosec B608 - 테이블명은 모듈 상수, 조건/정렬은 고정 조각이고 값은 ? 바인딩(사용자 입력 미결합)
            tuple(params),
        ).fetchone()
        total = int(total_row[0]) if total_row else 0

        if sort_key == SHOP_SORT_LPRICE_ASC:
            order = "CASE WHEN lprice IS NULL THEN 1 ELSE 0 END, lprice ASC, collected_at DESC"
        elif sort_key == SHOP_SORT_LPRICE_DESC:
            order = "CASE WHEN lprice IS NULL THEN 1 ELSE 0 END, lprice DESC, collected_at DESC"
        else:
            order = "collected_at DESC"

        cols_csv = ", ".join(_SHOP_SELECT_COLS)
        rows = conn.execute(
            f"SELECT {cols_csv} FROM {db_mod.TABLE_SHOP}{where_sql} ORDER BY {order} LIMIT ? OFFSET ?",  # nosec B608 - 테이블명은 모듈 상수, 조건/정렬은 고정 조각이고 값은 ? 바인딩(사용자 입력 미결합)
            tuple(params) + (lim, off),  # noqa: RUF005
        ).fetchall()
        items = [dict(r) for r in rows]
        return QueryPage(total=total, items=items, limit=lim, offset=off)
    finally:
        conn.close()


# ── status 조회 ─────────────────────────────────────────────────
@dataclass
class SearchStatus:
    status: str  # "PASS" | "WARN"
    db_enabled: bool
    db_exists: bool
    db_path_basename: str
    state_path_basename: str
    state_exists: bool
    row_counts: dict | None  # {"naver_blog_posts": int, "naver_shopping_items": int}
    latest_collected_at: dict  # {"blog": str|None, "shopping": str|None}
    last_blog_queries: list  # [{"query": str, "last_collected_at": str}]
    last_shop_queries: list
    warnings: list  # 사람이 읽을 짧은 코드 목록
    # 5단계: 스케줄 실행 기록 (최근 N건, 최신순)
    recent_runs: list = None  # type: ignore[assignment]
    last_success_at: str | None = None
    last_warn_at: str | None = None
    last_fail_at: str | None = None

    def __post_init__(self) -> None:
        if self.recent_runs is None:
            self.recent_runs = []

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "db_enabled": self.db_enabled,
            "db_exists": self.db_exists,
            "db_path_basename": self.db_path_basename,
            "state_path_basename": self.state_path_basename,
            "state_exists": self.state_exists,
            "row_counts": self.row_counts,
            "latest_collected_at": self.latest_collected_at,
            "last_blog_queries": self.last_blog_queries,
            "last_shop_queries": self.last_shop_queries,
            "warnings": self.warnings,
            "recent_runs": self.recent_runs,
            "last_success_at": self.last_success_at,
            "last_warn_at": self.last_warn_at,
            "last_fail_at": self.last_fail_at,
        }


def _check_table(table: str) -> str:
    """f-string SQL 에 들어가는 테이블명은 허용 목록(블로그/쇼핑 테이블) 값만 통과시킨다."""
    if table not in (db_mod.TABLE_BLOG, db_mod.TABLE_SHOP):
        raise ValueError(f"unknown table: {table!r}")
    return table


def _top_queries(conn: sqlite3.Connection, table: str, n: int = 5) -> list:
    table = _check_table(table)
    rows = conn.execute(
        f"SELECT query, MAX(collected_at) AS last_collected_at "  # nosec B608 - 테이블명은 모듈 상수, 조건/정렬은 고정 조각이고 값은 ? 바인딩(사용자 입력 미결합)
        f"FROM {table} WHERE query IS NOT NULL AND query != '' "
        f"GROUP BY query ORDER BY last_collected_at DESC LIMIT ?",
        (int(n),),
    ).fetchall()
    return [{"query": r["query"], "last_collected_at": r["last_collected_at"]} for r in rows]


def _max_collected_at(conn: sqlite3.Connection, table: str) -> str | None:
    table = _check_table(table)
    row = conn.execute(f"SELECT MAX(collected_at) FROM {table}").fetchone()  # nosec B608 - 테이블명은 모듈 상수, 조건/정렬은 고정 조각이고 값은 ? 바인딩(사용자 입력 미결합)
    v = row[0] if row else None
    return v if isinstance(v, str) and v else None


def _extract_timestamps(runs: list) -> tuple:
    """recent_runs 에서 last_success_at / last_warn_at / last_fail_at 추출."""
    last_success: str | None = None
    last_warn: str | None = None
    last_fail: str | None = None
    for r in runs:
        s = r.get("status", "")
        ts = r.get("finished_at") or r.get("started_at")
        if s == "ok" and last_success is None:
            last_success = ts
        elif s == "warn" and last_warn is None:
            last_warn = ts
        elif s == "fail" and last_fail is None:
            last_fail = ts
        if last_success and last_warn and last_fail:
            break
    return last_success, last_warn, last_fail


def get_search_status(
    *,
    db_path: Path | None = None,
    state_path: Path | None = None,
    run_log_path: Path | None = None,
    top_n: int = 5,
    recent_runs_n: int = 10,
) -> SearchStatus:
    """현재 DB / state / 실행 기록의 요약 상태. 민감정보 없음."""
    from scripts.naver.shopping import naver_search_state as state_mod

    db_p = _resolve_db_path(db_path)
    state_p = state_path or state_mod.default_state_path()
    db_enabled = db_mod.is_db_enabled()
    db_exists = db_p.is_file()
    state_exists = state_p.is_file()

    warnings: list = []
    row_counts: dict | None = None
    latest: dict[str, str | None] = {"blog": None, "shopping": None}
    last_blog_q: list = []
    last_shop_q: list = []

    if db_enabled and not db_exists:
        warnings.append("DB_ENABLED_BUT_FILE_MISSING")
    if not db_enabled:
        warnings.append("DB_DISABLED")
    if not state_exists:
        warnings.append("STATE_FILE_MISSING")

    if db_exists:
        conn = _readonly_connect(db_p)
        if conn is None:
            warnings.append("DB_OPEN_FAILED")
        else:
            try:
                row_counts = {
                    db_mod.TABLE_BLOG: int(conn.execute(f"SELECT COUNT(*) FROM {db_mod.TABLE_BLOG}").fetchone()[0]),  # nosec B608 - 테이블명은 모듈 상수, 조건/정렬은 고정 조각이고 값은 ? 바인딩(사용자 입력 미결합)
                    db_mod.TABLE_SHOP: int(conn.execute(f"SELECT COUNT(*) FROM {db_mod.TABLE_SHOP}").fetchone()[0]),  # nosec B608 - 테이블명은 모듈 상수, 조건/정렬은 고정 조각이고 값은 ? 바인딩(사용자 입력 미결합)
                }
                latest["blog"] = _max_collected_at(conn, db_mod.TABLE_BLOG)
                latest["shopping"] = _max_collected_at(conn, db_mod.TABLE_SHOP)
                last_blog_q = _top_queries(conn, db_mod.TABLE_BLOG, top_n)
                last_shop_q = _top_queries(conn, db_mod.TABLE_SHOP, top_n)
            except sqlite3.Error as e:
                warnings.append(f"DB_QUERY_ERROR:{type(e).__name__}")
            finally:
                conn.close()

    # 5단계: 실행 기록 로드 (실패해도 기존 status 판정에 영향 없음)
    from scripts.naver.shopping.naver_search_run_log import load_recent_runs

    try:
        recent_runs = load_recent_runs(recent_runs_n, path=run_log_path)
    except Exception:  # noqa: BLE001 - 최근 실행 로그 조회 실패 시 빈 리스트로 폴백 — 상태 요약용 부가 정보일 뿐 검색 실행 자체에 영향 없음
        recent_runs = []
    last_success_at, last_warn_at, last_fail_at = _extract_timestamps(recent_runs)

    status = "WARN" if warnings else "PASS"
    return SearchStatus(
        status=status,
        db_enabled=db_enabled,
        db_exists=db_exists,
        # 민감도 방지 — 전체 경로 대신 basename 만 노출.
        db_path_basename=db_p.name,
        state_path_basename=state_p.name,
        state_exists=state_exists,
        row_counts=row_counts,
        latest_collected_at=latest,
        last_blog_queries=last_blog_q,
        last_shop_queries=last_shop_q,
        warnings=warnings,
        recent_runs=recent_runs,
        last_success_at=last_success_at,
        last_warn_at=last_warn_at,
        last_fail_at=last_fail_at,
    )


__all__ = [
    "SHOP_SORT_ALLOWED",
    "SHOP_SORT_COLLECTED_DESC",
    "SHOP_SORT_LPRICE_ASC",
    "SHOP_SORT_LPRICE_DESC",
    "QueryPage",
    "SearchStatus",
    "get_search_status",
    "search_blog_posts",
    "search_shopping_items",
]

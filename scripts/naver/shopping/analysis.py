"""조명 상품 DB 분석 모듈 — 검색·필터·통계·분류.

read-only URI 모드 (file:...?mode=ro) — 쓰기 없음, 스키마 변경 없음.
stdlib sqlite3 만 사용 (외부 의존성 없음).
"""

from __future__ import annotations

import logging
import math
import sqlite3
from pathlib import Path

from ai_orchestrator.paths.runtime import data_dir

logger = logging.getLogger(__name__)

# ── 상수 ────────────────────────────────────────────────────────────────────

TABLE = "naver_shopping_items"

_LARGE_MALLS = frozenset(
    {
        "네이버",
        "쿠팡",
        "G마켓",
        "옥션",
        "11번가",
        "롯데ON",
        "위메프",
        "티몬",
        "GS샵",
        "CJ온스타일",
        "홈앤쇼핑",
        "현대Hmall",
    }
)

PRICE_RANGES = [
    ("~1만", 0, 10_000),
    ("1~3만", 10_001, 30_000),
    ("3~5만", 30_001, 50_000),
    ("5~10만", 50_001, 100_000),
    ("10만~", 100_001, None),
]


# ── 내부 헬퍼 ────────────────────────────────────────────────────────────────


def _db_path() -> Path:
    """repo root / data / naver_search.db"""
    return data_dir() / "naver_search.db"


def _connect() -> sqlite3.Connection | None:
    p = _db_path()
    if not p.is_file():
        logger.warning("[ANALYSIS] DB 파일 없음: %s", p)
        return None
    try:
        uri = f"file:{p.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.warning("[ANALYSIS] DB 연결 실패: %s", e)
        return None


def _where_keywords(keywords: list[str] | None) -> tuple:
    """키워드 리스트 → (WHERE 절 문자열, params 리스트)"""
    if not keywords:
        return "", []
    placeholders = ", ".join("?" for _ in keywords)
    return f" WHERE query IN ({placeholders})", list(keywords)


# ── 공개 함수 ────────────────────────────────────────────────────────────────


def search_products(  # noqa: PLR0913 - 공개 시그니처 유지(동작 변경 금지 리팩터링)
    keyword: str | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    brand: str | None = None,
    mall: str | None = None,
    limit: int = 50,
    offset: int = 0,
    sort: str = "collected_at_desc",
) -> dict:
    """title / query LIKE 검색 + 필터.

    naver_search_queries.search_shopping_items 의 title-검색 보강 버전.
    결과 각 항목에 rank(1-based) 추가.
    """
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))

    conn = _connect()
    if conn is None:
        return {"total": 0, "items": [], "limit": limit, "offset": offset}

    try:
        where: list[str] = []
        params: list = []
        if keyword:
            where.append("(query LIKE ? OR title LIKE ?)")
            like = f"%{keyword}%"
            params.extend([like, like])
        if min_price is not None:
            where.append("lprice IS NOT NULL AND lprice >= ?")
            params.append(int(min_price))
        if max_price is not None:
            where.append("lprice IS NOT NULL AND lprice <= ?")
            params.append(int(max_price))
        if brand:
            where.append("brand = ?")
            params.append(brand)
        if mall:
            where.append("mall_name = ?")
            params.append(mall)
        where_sql = (" WHERE " + " AND ".join(where)) if where else ""

        _SORT_MAP = {
            "collected_at_desc": "collected_at DESC",
            "lprice_asc": "CASE WHEN lprice IS NULL THEN 1 ELSE 0 END, lprice ASC",
            "lprice_desc": "CASE WHEN lprice IS NULL THEN 1 ELSE 0 END, lprice DESC",
        }
        order_sql = _SORT_MAP.get(sort, "collected_at DESC")

        total_row = conn.execute(
            f"SELECT COUNT(*) FROM {TABLE}{where_sql}",  # nosec B608 - 테이블명은 모듈 상수, 조건/정렬은 고정 조각이고 값은 ? 바인딩(사용자 입력 미결합)
            tuple(params),
        ).fetchone()
        total = int(total_row[0]) if total_row else 0

        rows = conn.execute(
            f"SELECT query, title, link, lprice, hprice, mall_name, brand, maker, "  # nosec B608 - 테이블명은 모듈 상수, 조건/정렬은 고정 조각이고 값은 ? 바인딩(사용자 입력 미결합)
            f"product_id, collected_at, source "
            f"FROM {TABLE}{where_sql} ORDER BY {order_sql} LIMIT ? OFFSET ?",
            tuple(params) + (limit, offset),
        ).fetchall()

        items = []
        for i, r in enumerate(rows, start=offset + 1):
            d = dict(r)
            d["rank"] = i
            items.append(d)

        return {"total": total, "items": items, "limit": limit, "offset": offset}
    finally:
        conn.close()


def price_distribution(keywords: list[str] | None = None) -> dict:
    """가격 구간별 상품 수 집계.

    구간: ~1만 / 1~3만 / 3~5만 / 5~10만 / 10만~
    keywords 미지정 시 전체.
    """
    conn = _connect()
    if conn is None:
        return {"ranges": [], "keywords": keywords or []}

    try:
        where_sql, params = _where_keywords(keywords)
        sep = " AND " if where_sql else " WHERE "
        rows = conn.execute(
            f"SELECT lprice FROM {TABLE}{where_sql}{sep}lprice IS NOT NULL",  # nosec B608 - 테이블명은 모듈 상수, 조건/정렬은 고정 조각이고 값은 ? 바인딩(사용자 입력 미결합)
            tuple(params),
        ).fetchall()
        prices = [r[0] for r in rows if r[0] is not None]

        ranges = []
        for label, lo, hi in PRICE_RANGES:
            if hi is None:
                count = sum(1 for p in prices if p >= lo)
            else:
                count = sum(1 for p in prices if lo <= p <= hi)
            ranges.append({"label": label, "lo": lo, "hi": hi, "count": count})

        return {
            "ranges": ranges,
            "total_with_price": len(prices),
            "keywords": keywords or [],
        }
    finally:
        conn.close()


def mall_analysis(
    keywords: list[str] | None = None,
    top_n: int = 30,
    exclude_large: bool = False,
) -> dict:
    """업체별 집계: 상품수, 최저가, 평균가, 최고가, 브랜드수.

    대형몰과 전문 조명 업체를 분리하여 반환.
    exclude_large=True 이면 전문 업체만 포함.
    """
    conn = _connect()
    if conn is None:
        return {"malls": [], "total_malls": 0, "large_malls": [], "keywords": keywords or []}

    try:
        where_sql, params = _where_keywords(keywords)
        rows = conn.execute(
            f"SELECT mall_name, lprice, brand FROM {TABLE}{where_sql}",  # nosec B608 - 테이블명은 모듈 상수, 조건/정렬은 고정 조각이고 값은 ? 바인딩(사용자 입력 미결합)
            tuple(params),
        ).fetchall()

        agg: dict = {}
        for r in rows:
            name = r["mall_name"] or "미분류"
            price = r["lprice"]
            brand_val = r["brand"] or ""
            if name not in agg:
                agg[name] = {"count": 0, "prices": [], "brands": set()}
            agg[name]["count"] += 1
            if price is not None:
                agg[name]["prices"].append(price)
            if brand_val:
                agg[name]["brands"].add(brand_val)

        result_all = []
        for name, d in agg.items():
            prices = d["prices"]
            result_all.append(
                {
                    "mall_name": name,
                    "count": d["count"],
                    "min_price": min(prices) if prices else None,
                    "avg_price": int(sum(prices) / len(prices)) if prices else None,
                    "max_price": max(prices) if prices else None,
                    "brand_count": len(d["brands"]),
                    "is_large": name in _LARGE_MALLS,
                }
            )

        large = [m for m in result_all if m["is_large"]]
        specialist = [m for m in result_all if not m["is_large"]]
        specialist_sorted = sorted(specialist, key=lambda x: x["count"], reverse=True)
        large_sorted = sorted(large, key=lambda x: x["count"], reverse=True)

        if exclude_large:
            malls_out = specialist_sorted[:top_n]
        else:
            combined = sorted(result_all, key=lambda x: x["count"], reverse=True)
            malls_out = combined[:top_n]

        return {
            "malls": malls_out,
            "total_malls": len(agg),
            "specialist_count": len(specialist),
            "large_malls": large_sorted,
            "keywords": keywords or [],
        }
    finally:
        conn.close()


def brand_analysis(
    keywords: list[str] | None = None,
    top_n: int = 20,
) -> dict:
    """브랜드별 집계: 상품수, 가격 범위, 판매몰 수."""
    conn = _connect()
    if conn is None:
        return {"brands": [], "total_brands": 0, "keywords": keywords or []}

    try:
        where_sql, params = _where_keywords(keywords)
        rows = conn.execute(
            f"SELECT brand, lprice, mall_name FROM {TABLE}{where_sql}",  # nosec B608 - 테이블명은 모듈 상수, 조건/정렬은 고정 조각이고 값은 ? 바인딩(사용자 입력 미결합)
            tuple(params),
        ).fetchall()

        agg: dict = {}
        for r in rows:
            name = (r["brand"] or "").strip()
            if not name:
                continue
            price = r["lprice"]
            mall_val = r["mall_name"] or ""
            if name not in agg:
                agg[name] = {"count": 0, "prices": [], "malls": set()}
            agg[name]["count"] += 1
            if price is not None:
                agg[name]["prices"].append(price)
            if mall_val:
                agg[name]["malls"].add(mall_val)

        brands = []
        for name, d in agg.items():
            prices = d["prices"]
            brands.append(
                {
                    "brand": name,
                    "count": d["count"],
                    "min_price": min(prices) if prices else None,
                    "max_price": max(prices) if prices else None,
                    "mall_count": len(d["malls"]),
                }
            )

        brands_sorted = sorted(brands, key=lambda x: x["count"], reverse=True)[:top_n]
        return {
            "brands": brands_sorted,
            "total_brands": len(agg),
            "keywords": keywords or [],
        }
    finally:
        conn.close()


def category_analysis() -> dict:
    """category1 / category2 기준 집계."""
    conn = _connect()
    if conn is None:
        return {"by_category1": [], "by_category2": []}

    try:
        rows1 = conn.execute(
            f"SELECT category1, COUNT(*) as cnt FROM {TABLE} "  # nosec B608 - 테이블명은 모듈 상수, 조건/정렬은 고정 조각이고 값은 ? 바인딩(사용자 입력 미결합)
            f"WHERE category1 != '' GROUP BY category1 ORDER BY cnt DESC"
        ).fetchall()
        rows2 = conn.execute(
            f"SELECT category1, category2, COUNT(*) as cnt FROM {TABLE} "  # nosec B608 - 테이블명은 모듈 상수, 조건/정렬은 고정 조각이고 값은 ? 바인딩(사용자 입력 미결합)
            f"WHERE category2 != '' GROUP BY category1, category2 ORDER BY cnt DESC LIMIT 50"
        ).fetchall()
        return {
            "by_category1": [{"category": r["category1"], "count": r["cnt"]} for r in rows1],
            "by_category2": [
                {
                    "category1": r["category1"],
                    "category2": r["category2"],
                    "count": r["cnt"],
                }
                for r in rows2
            ],
        }
    finally:
        conn.close()


def competition_score(keyword: str) -> dict:
    """경쟁 강도 점수 (0~100).

    = 상품수(정규화)*0.4 + 가격분산(정규화)*0.3 + 업체수(정규화)*0.3
    높을수록 경쟁이 치열함.
    """
    conn = _connect()
    if conn is None:
        return {"keyword": keyword, "score": 0, "detail": {}}

    try:
        row = conn.execute(
            f"SELECT COUNT(*) FROM {TABLE} WHERE query = ?",  # nosec B608 - 테이블명은 모듈 상수, 조건/정렬은 고정 조각이고 값은 ? 바인딩(사용자 입력 미결합)
            (keyword,),
        ).fetchone()
        kw_count = int(row[0]) if row else 0

        row = conn.execute(
            f"SELECT MAX(cnt) FROM (SELECT COUNT(*) AS cnt FROM {TABLE} GROUP BY query)"  # nosec B608 - 테이블명은 모듈 상수, 조건/정렬은 고정 조각이고 값은 ? 바인딩(사용자 입력 미결합)
        ).fetchone()
        max_count = int(row[0]) if row and row[0] else 1

        rows = conn.execute(
            f"SELECT lprice FROM {TABLE} WHERE query = ? AND lprice IS NOT NULL",  # nosec B608 - 테이블명은 모듈 상수, 조건/정렬은 고정 조각이고 값은 ? 바인딩(사용자 입력 미결합)
            (keyword,),
        ).fetchall()
        prices = [r[0] for r in rows]
        if len(prices) >= 2:
            avg_p = sum(prices) / len(prices)
            variance = sum((p - avg_p) ** 2 for p in prices) / len(prices)
            std_price = math.sqrt(variance)
        else:
            std_price = 0.0

        row = conn.execute(
            f"SELECT COUNT(DISTINCT mall_name) FROM {TABLE} WHERE query = ?",  # nosec B608 - 테이블명은 모듈 상수, 조건/정렬은 고정 조각이고 값은 ? 바인딩(사용자 입력 미결합)
            (keyword,),
        ).fetchone()
        kw_malls = int(row[0]) if row else 0

        row = conn.execute(f"SELECT COUNT(DISTINCT mall_name) FROM {TABLE}").fetchone()  # nosec B608 - 테이블명은 모듈 상수, 조건/정렬은 고정 조각이고 값은 ? 바인딩(사용자 입력 미결합)
        total_malls = int(row[0]) if row and row[0] else 1

        n_count = min(kw_count / max_count, 1.0) if max_count else 0.0
        n_std = min(std_price / 100_000, 1.0)
        n_malls = min(kw_malls / total_malls, 1.0) if total_malls else 0.0
        score_100 = round((n_count * 0.4 + n_std * 0.3 + n_malls * 0.3) * 100, 1)

        return {
            "keyword": keyword,
            "score": score_100,
            "detail": {
                "product_count": kw_count,
                "max_count_in_db": max_count,
                "price_std": round(std_price, 1),
                "mall_count": kw_malls,
                "total_mall_count": total_malls,
                "n_count": round(n_count, 4),
                "n_std": round(n_std, 4),
                "n_malls": round(n_malls, 4),
            },
        }
    finally:
        conn.close()


def keyword_summary(keywords: list[str] | None = None) -> dict:
    """키워드별 요약: 상품수, 가격 min/avg/max, 업체수, 브랜드수."""
    conn = _connect()
    if conn is None:
        return {"keywords": [], "total_products": 0}

    try:
        if keywords:
            placeholders = ", ".join("?" for _ in keywords)
            rows = conn.execute(
                f"SELECT query, COUNT(*) AS cnt, "  # nosec B608 - 테이블명은 모듈 상수, 조건/정렬은 고정 조각이고 값은 ? 바인딩(사용자 입력 미결합)
                f"MIN(lprice) AS min_p, MAX(lprice) AS max_p, "
                f"COUNT(DISTINCT mall_name) AS malls, "
                f"COUNT(DISTINCT brand) AS brands "
                f"FROM {TABLE} WHERE query IN ({placeholders}) GROUP BY query",
                tuple(keywords),
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT query, COUNT(*) AS cnt, "  # nosec B608 - 테이블명은 모듈 상수, 조건/정렬은 고정 조각이고 값은 ? 바인딩(사용자 입력 미결합)
                f"MIN(lprice) AS min_p, MAX(lprice) AS max_p, "
                f"COUNT(DISTINCT mall_name) AS malls, "
                f"COUNT(DISTINCT brand) AS brands "
                f"FROM {TABLE} GROUP BY query ORDER BY cnt DESC"
            ).fetchall()

        result = []
        for r in rows:
            q = r["query"]
            avg_row = conn.execute(
                f"SELECT AVG(lprice) FROM {TABLE} WHERE query = ? AND lprice IS NOT NULL",  # nosec B608 - 테이블명은 모듈 상수, 조건/정렬은 고정 조각이고 값은 ? 바인딩(사용자 입력 미결합)
                (q,),
            ).fetchone()
            avg_price = int(avg_row[0]) if avg_row and avg_row[0] is not None else None
            result.append(
                {
                    "query": q,
                    "count": r["cnt"],
                    "min_price": r["min_p"],
                    "avg_price": avg_price,
                    "max_price": r["max_p"],
                    "mall_count": r["malls"],
                    "brand_count": r["brands"],
                }
            )

        total_row = conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()  # nosec B608 - 테이블명은 모듈 상수, 조건/정렬은 고정 조각이고 값은 ? 바인딩(사용자 입력 미결합)
        total = int(total_row[0]) if total_row else 0
        return {"keywords": result, "total_products": total}
    finally:
        conn.close()


__all__ = [
    "brand_analysis",
    "category_analysis",
    "competition_score",
    "keyword_summary",
    "mall_analysis",
    "price_distribution",
    "search_products",
]

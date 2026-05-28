"""Naver 검색 수집 read-only 조회 엔드포인트 (/api/v1/external/naver/*).

- 쓰기 API 없음. 모두 read-only.
- 기존 `require_role("admin","owner")` 패턴 재사용.
- 민감정보(client_id/secret/풀 경로) 응답 금지 — DB 레이어에서 basename 만 노출.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends

from ..audit_logger import log_event
from ..auth import require_role
from . import naver_search_queries as q
from .naver_search_jobs import run_naver_blog_search_job, run_naver_shopping_search_job

logger = logging.getLogger(__name__)


naver_search_router = APIRouter(
    prefix="/external/naver", tags=["naver-external"],
)


@naver_search_router.get("/blog-search")
def api_blog_search(
    query: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    t0 = time.monotonic()
    page = q.search_blog_posts(
        query=query, date_from=date_from, date_to=date_to,
        limit=limit, offset=offset,
    )
    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_BLOG_SEARCH_READ",
        task_id="-",
        actor=user["actor"], role=user["role"], decision="ok",
        note=f"total={page.total} returned={len(page.items)} duration_ms={duration_ms}",
    )
    return {**page.to_dict(), "duration_ms": duration_ms}


@naver_search_router.get("/shopping-search")
def api_shopping_search(
    query: Optional[str] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    brand: Optional[str] = None,
    mall_name: Optional[str] = None,
    sort: str = q.SHOP_SORT_COLLECTED_DESC,
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    t0 = time.monotonic()
    page = q.search_shopping_items(
        query=query,
        min_price=min_price, max_price=max_price,
        brand=brand, mall_name=mall_name,
        sort=sort, limit=limit, offset=offset,
    )
    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_SHOPPING_SEARCH_READ",
        task_id="-",
        actor=user["actor"], role=user["role"], decision="ok",
        note=f"total={page.total} returned={len(page.items)} "
             f"sort={sort} duration_ms={duration_ms}",
    )
    return {**page.to_dict(), "sort": sort, "duration_ms": duration_ms}


@naver_search_router.get("/search-status")
def api_search_status(
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    t0 = time.monotonic()
    status = q.get_search_status()
    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_SEARCH_STATUS_READ",
        task_id="-",
        actor=user["actor"], role=user["role"], decision=status.status,
        note=f"db_exists={status.db_exists} warnings={len(status.warnings)} "
             f"duration_ms={duration_ms}",
    )
    return {**status.to_dict(), "duration_ms": duration_ms}


@naver_search_router.post("/blog-search/run")
def api_run_blog_search(
    query: str,
    max_pages: int = 1,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """블로그 검색 즉시 실행 — dry_run=False, DB 적재."""
    t0 = time.monotonic()
    outcome = run_naver_blog_search_job(query=query, max_pages=max_pages)
    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_BLOG_SEARCH_RUN",
        task_id="-",
        actor=user["actor"], role=user["role"], decision=outcome.status,
        note=f"query={query} collected={outcome.collected} duration_ms={duration_ms}",
    )
    return {
        "status": outcome.status,
        "query": query,
        "collected": outcome.collected,
        "db_status": outcome.db_status,
        "duration_ms": duration_ms,
    }


@naver_search_router.post("/shopping-search/run")
def api_run_shopping_search(
    query: str,
    max_pages: int = 1,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """쇼핑 검색 즉시 실행 — dry_run=False, DB 적재."""
    t0 = time.monotonic()
    outcome = run_naver_shopping_search_job(query=query, max_pages=max_pages)
    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_SHOPPING_SEARCH_RUN",
        task_id="-",
        actor=user["actor"], role=user["role"], decision=outcome.status,
        note=f"query={query} collected={outcome.collected} duration_ms={duration_ms}",
    )
    return {
        "status": outcome.status,
        "query": query,
        "collected": outcome.collected,
        "db_status": outcome.db_status,
        "duration_ms": duration_ms,
    }


@naver_search_router.get("/shopping-search/history")
def api_shopping_history(
    query: Optional[str] = None,
    limit: int = 100,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """쇼핑 검색 수집 이력 조회 — 가격 비교 분석용."""
    t0 = time.monotonic()
    page = q.search_shopping_items(
        query=query, limit=limit, offset=0,
        sort=q.SHOP_SORT_COLLECTED_DESC,
    )
    duration_ms = int((time.monotonic() - t0) * 1000)

    # 키워드별 가격 통계 계산
    page_dict = page.to_dict()
    items = page_dict.get("items", [])
    stats: dict = {}
    for item in items:
        kw = item.get("query", "")
        price = item.get("lprice")
        if not kw or not price:
            continue
        if kw not in stats:
            stats[kw] = {"prices": [], "brands": set(), "mall_names": set()}
        stats[kw]["prices"].append(price)
        if item.get("brand"):
            stats[kw]["brands"].add(item["brand"])
        if item.get("mall_name"):
            stats[kw]["mall_names"].add(item["mall_name"])

    summary: dict = {}
    for kw, d in stats.items():
        prices = sorted(d["prices"])
        summary[kw] = {
            "count": len(prices),
            "min_price": prices[0] if prices else None,
            "max_price": prices[-1] if prices else None,
            "avg_price": int(sum(prices) / len(prices)) if prices else None,
            "brands": list(d["brands"])[:10],
            "mall_names": list(d["mall_names"])[:10],
        }

    log_event(
        "NAVER_SHOPPING_HISTORY_READ",
        task_id="-",
        actor=user["actor"], role=user["role"], decision="ok",
        note=f"total={page.total} duration_ms={duration_ms}",
    )
    return {**page_dict, "summary": summary, "duration_ms": duration_ms}


@naver_search_router.post("/shopping-search/crawl")
def api_crawl_shopping(
    query: str,
    limit: int = 40,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """CDP 브라우저 크롤링 — 리뷰·별점·구매수 포함 수집."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

    t0 = time.monotonic()
    try:
        from scripts.naver.shopping.crawl import crawl_shopping
        result = crawl_shopping(query=query, limit=limit)
    except Exception as e:
        logger.warning("[SHOPPING-CRAWL-ERR] %s", e)
        result = {"ok": False, "error": str(e)}

    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_SHOPPING_CRAWL",
        task_id="-", actor=user["actor"], role=user["role"],
        decision="ok" if result.get("ok") else "error",
        note=f"query={query} count={result.get('count',0)} duration_ms={duration_ms}",
    )
    return {**result, "duration_ms": duration_ms}


@naver_search_router.get("/shopping-search/crawl-report")
def api_crawl_report(
    query: str,
    days: int = 30,
    limit: int = 50,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """CDP 크롤링 수집 이력 보고서 — 리뷰·별점·구매수 포함."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

    t0 = time.monotonic()
    try:
        from scripts.naver.shopping.crawl import full_summary
        result = full_summary(query=query)
    except Exception as e:
        logger.warning("[SHOPPING-CRAWL-REPORT-ERR] %s", e)
        result = {"keyword": query, "count": 0, "error": str(e)}

    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_SHOPPING_CRAWL_REPORT",
        task_id="-", actor=user["actor"], role=user["role"], decision="ok",
        note=f"query={query} count={result.get('count',0)} duration_ms={duration_ms}",
    )
    return {**result, "duration_ms": duration_ms}


# ── 분석 엔드포인트 ──────────────────────────────────────────────


@naver_search_router.get("/shopping-search/analysis/price-dist")
def api_price_distribution(
    query: Optional[str] = None,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """가격 구간별 상품 수 집계."""
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))

    t0 = time.monotonic()
    try:
        from scripts.naver.shopping.analysis import price_distribution
        keywords = [query] if query else None
        result = price_distribution(keywords=keywords)
    except Exception as e:  # noqa: BLE001
        logger.warning("[SHOPPING-ANALYSIS-PRICE-DIST-ERR] %s", e)
        result = {"ranges": [], "error": str(e)}
    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_SHOPPING_ANALYSIS_PRICE_DIST",
        task_id="-", actor=user["actor"], role=user["role"], decision="ok",
        note=f"query={query} duration_ms={duration_ms}",
    )
    return {**result, "duration_ms": duration_ms}


@naver_search_router.get("/shopping-search/analysis/malls")
def api_mall_analysis(
    query: Optional[str] = None,
    top_n: int = 30,
    exclude_large: bool = False,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """업체별 집계: 상품수, 최저가, 평균가, 최고가, 브랜드수."""
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))

    t0 = time.monotonic()
    try:
        from scripts.naver.shopping.analysis import mall_analysis
        keywords = [query] if query else None
        result = mall_analysis(keywords=keywords, top_n=top_n, exclude_large=exclude_large)
    except Exception as e:  # noqa: BLE001
        logger.warning("[SHOPPING-ANALYSIS-MALLS-ERR] %s", e)
        result = {"malls": [], "total_malls": 0, "error": str(e)}
    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_SHOPPING_ANALYSIS_MALLS",
        task_id="-", actor=user["actor"], role=user["role"], decision="ok",
        note=f"query={query} top_n={top_n} duration_ms={duration_ms}",
    )
    return {**result, "duration_ms": duration_ms}


@naver_search_router.get("/shopping-search/analysis/brands")
def api_brand_analysis(
    query: Optional[str] = None,
    top_n: int = 20,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """브랜드별 집계: 상품수, 가격 범위, 판매몰 수."""
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))

    t0 = time.monotonic()
    try:
        from scripts.naver.shopping.analysis import brand_analysis
        keywords = [query] if query else None
        result = brand_analysis(keywords=keywords, top_n=top_n)
    except Exception as e:  # noqa: BLE001
        logger.warning("[SHOPPING-ANALYSIS-BRANDS-ERR] %s", e)
        result = {"brands": [], "total_brands": 0, "error": str(e)}
    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_SHOPPING_ANALYSIS_BRANDS",
        task_id="-", actor=user["actor"], role=user["role"], decision="ok",
        note=f"query={query} top_n={top_n} duration_ms={duration_ms}",
    )
    return {**result, "duration_ms": duration_ms}


@naver_search_router.get("/shopping-search/analysis/keywords")
def api_keyword_summary(
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """키워드별 요약: 상품수, 가격 min/avg/max, 업체수, 브랜드수."""
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))

    t0 = time.monotonic()
    try:
        from scripts.naver.shopping.analysis import keyword_summary
        result = keyword_summary()
    except Exception as e:  # noqa: BLE001
        logger.warning("[SHOPPING-ANALYSIS-KEYWORDS-ERR] %s", e)
        result = {"keywords": [], "total_products": 0, "error": str(e)}
    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_SHOPPING_ANALYSIS_KEYWORDS",
        task_id="-", actor=user["actor"], role=user["role"], decision="ok",
        note=f"duration_ms={duration_ms}",
    )
    return {**result, "duration_ms": duration_ms}


@naver_search_router.get("/shopping-search/analysis/competition")
def api_competition_score(
    query: str,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """키워드 경쟁 강도 점수 (0~100). 높을수록 경쟁 치열."""
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))

    t0 = time.monotonic()
    try:
        from scripts.naver.shopping.analysis import competition_score
        result = competition_score(query)
    except Exception as e:  # noqa: BLE001
        logger.warning("[SHOPPING-ANALYSIS-COMPETITION-ERR] %s", e)
        result = {"keyword": query, "score": 0, "error": str(e)}
    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_SHOPPING_ANALYSIS_COMPETITION",
        task_id="-", actor=user["actor"], role=user["role"], decision="ok",
        note=f"query={query} score={result.get('score')} duration_ms={duration_ms}",
    )
    return {**result, "duration_ms": duration_ms}


__all__ = ["naver_search_router"]

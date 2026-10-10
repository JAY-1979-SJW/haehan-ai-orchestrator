"""Naver 검색 수집 read-only 조회 엔드포인트 (/api/v1/external/naver/*).

- 쓰기 API 없음. 모두 read-only.
- 기존 `require_role("admin","owner")` 패턴 재사용.
- 민감정보(client_id/secret/풀 경로) 응답 금지 — DB 레이어에서 basename 만 노출.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends

from ai_orchestrator.audit.audit_logger import log_event
from ai_orchestrator.paths import repo_root
from scripts.naver.shopping import naver_search_queries as q
from scripts.naver.shopping.naver_search_jobs import run_naver_blog_search_job, run_naver_shopping_search_job
from tools.gates.auth import require_role

logger = logging.getLogger(__name__)


naver_search_router = APIRouter(
    prefix="/external/naver",
    tags=["naver-external"],
)


@naver_search_router.get("/blog-search")
def api_blog_search(
    query: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    t0 = time.monotonic()
    page = q.search_blog_posts(
        query=query,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_BLOG_SEARCH_READ",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"total={page.total} returned={len(page.items)} duration_ms={duration_ms}",
    )
    return {**page.to_dict(), "duration_ms": duration_ms}


@naver_search_router.get("/shopping-search")
def api_shopping_search(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수, 인자 묶음 변경 시 API 영향)
    query: str | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    brand: str | None = None,
    mall_name: str | None = None,
    sort: str = q.SHOP_SORT_COLLECTED_DESC,
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    t0 = time.monotonic()
    page = q.search_shopping_items(
        query=query,
        min_price=min_price,
        max_price=max_price,
        brand=brand,
        mall_name=mall_name,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_SHOPPING_SEARCH_READ",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"total={page.total} returned={len(page.items)} sort={sort} duration_ms={duration_ms}",
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
        actor=user["actor"],
        role=user["role"],
        decision=status.status,
        note=f"db_exists={status.db_exists} warnings={len(status.warnings)} duration_ms={duration_ms}",
    )
    return {**status.to_dict(), "duration_ms": duration_ms}


def _run_search_job(event: str, job_fn, query: str, max_pages: int, user: dict) -> dict:
    """공통화(G12 중복정리, 2026-10-09): api_run_blog_search·api_run_shopping_search 가
    event 이름과 실행 job 함수만 다르고 나머지(실행·로그·응답 모양)는 똑같던 구조동일
    중복(dup_gate G12) — 동작은 그대로, 각 라우트는 자기 event/job 으로 이 함수를 부르는
    1줄 래퍼."""
    t0 = time.monotonic()
    outcome = job_fn(query=query, max_pages=max_pages)
    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        event,
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision=outcome.status,
        note=f"query={query} inserted={outcome.inserted_count} duration_ms={duration_ms}",
    )
    return {
        "status": outcome.status,
        "query": query,
        "collected": outcome.inserted_count,
        "db_status": outcome.db_status,
        "duration_ms": duration_ms,
    }


@naver_search_router.post("/blog-search/run")
def api_run_blog_search(
    query: str,
    max_pages: int = 1,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """블로그 검색 즉시 실행 — dry_run=False, DB 적재."""
    return _run_search_job("NAVER_BLOG_SEARCH_RUN", run_naver_blog_search_job, query, max_pages, user)


@naver_search_router.post("/shopping-search/run")
def api_run_shopping_search(
    query: str,
    max_pages: int = 1,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """쇼핑 검색 즉시 실행 — dry_run=False, DB 적재."""
    return _run_search_job("NAVER_SHOPPING_SEARCH_RUN", run_naver_shopping_search_job, query, max_pages, user)


@naver_search_router.get("/shopping-search/history")
def api_shopping_history(
    query: str | None = None,
    limit: int = 100,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """쇼핑 검색 수집 이력 조회 — 가격 비교 분석용."""
    t0 = time.monotonic()
    page = q.search_shopping_items(
        query=query,
        limit=limit,
        offset=0,
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
        actor=user["actor"],
        role=user["role"],
        decision="ok",
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

    sys.path.insert(0, str(repo_root()))

    t0 = time.monotonic()
    try:
        from scripts.naver.shopping.crawl import crawl_shopping

        # crawl_shopping 의 실제 파라미터명은 keyword(query 아님) — kwarg 이름이 어긋나 있어
        # 매 호출마다 TypeError 로 실패하고 있었음(2026-09-29 defect_index #38, except 절이
        # 넓게 잡아 크래시 대신 조용히 빈 결과를 반환해 왔음 — 기능 자체가 한 번도 동작한 적 없었음).
        result = crawl_shopping(keyword=query, limit=limit)
    except Exception as e:  # noqa: BLE001 - 네이버 쇼핑 크롤링/분석 읽기전용 API - 실패시 빈 결과+error 필드 반환, warning 로그만 남김
        logger.warning("[SHOPPING-CRAWL-ERR] %s", e)
        result = {"ok": False, "error": str(e)}

    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_SHOPPING_CRAWL",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok" if result.get("ok") else "error",
        note=f"query={query} count={result.get('count', 0)} duration_ms={duration_ms}",
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

    sys.path.insert(0, str(repo_root()))

    t0 = time.monotonic()
    try:
        from scripts.naver.shopping.crawl import full_summary

        result = full_summary(query)  # full_summary(keyword: str) — 위치인자
    except Exception as e:  # noqa: BLE001 - 네이버 쇼핑 크롤링/분석 읽기전용 API - 실패시 빈 결과+error 필드 반환, warning 로그만 남김
        logger.warning("[SHOPPING-CRAWL-REPORT-ERR] %s", e)
        result = {"keyword": query, "count": 0, "error": str(e)}

    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_SHOPPING_CRAWL_REPORT",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"query={query} count={result.get('count', 0)} duration_ms={duration_ms}",
    )
    return {**result, "duration_ms": duration_ms}


# ── 분석 엔드포인트 ──────────────────────────────────────────────


@naver_search_router.get("/shopping-search/analysis/price-dist")
def api_price_distribution(
    query: str | None = None,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """가격 구간별 상품 수 집계."""
    import sys

    sys.path.insert(0, str(repo_root()))

    t0 = time.monotonic()
    try:
        from scripts.naver.shopping.analysis import price_distribution

        keywords = [query] if query else None
        result = price_distribution(keywords=keywords)
    except Exception as e:  # noqa: BLE001 - 네이버 쇼핑 크롤링/분석 읽기전용 API - 실패시 빈 결과+error 필드 반환, warning 로그만 남김
        logger.warning("[SHOPPING-ANALYSIS-PRICE-DIST-ERR] %s", e)
        result = {"ranges": [], "error": str(e)}
    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_SHOPPING_ANALYSIS_PRICE_DIST",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"query={query} duration_ms={duration_ms}",
    )
    return {**result, "duration_ms": duration_ms}


@naver_search_router.get("/shopping-search/analysis/malls")
def api_mall_analysis(
    query: str | None = None,
    top_n: int = 30,
    exclude_large: bool = False,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """업체별 집계: 상품수, 최저가, 평균가, 최고가, 브랜드수."""
    import sys

    sys.path.insert(0, str(repo_root()))

    t0 = time.monotonic()
    try:
        from scripts.naver.shopping.analysis import mall_analysis

        keywords = [query] if query else None
        result = mall_analysis(keywords=keywords, top_n=top_n, exclude_large=exclude_large)
    except Exception as e:  # noqa: BLE001 - 네이버 쇼핑 크롤링/분석 읽기전용 API - 실패시 빈 결과+error 필드 반환, warning 로그만 남김
        logger.warning("[SHOPPING-ANALYSIS-MALLS-ERR] %s", e)
        result = {"malls": [], "total_malls": 0, "error": str(e)}
    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_SHOPPING_ANALYSIS_MALLS",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"query={query} top_n={top_n} duration_ms={duration_ms}",
    )
    return {**result, "duration_ms": duration_ms}


@naver_search_router.get("/shopping-search/analysis/brands")
def api_brand_analysis(
    query: str | None = None,
    top_n: int = 20,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """브랜드별 집계: 상품수, 가격 범위, 판매몰 수."""
    import sys

    sys.path.insert(0, str(repo_root()))

    t0 = time.monotonic()
    try:
        from scripts.naver.shopping.analysis import brand_analysis

        keywords = [query] if query else None
        result = brand_analysis(keywords=keywords, top_n=top_n)
    except Exception as e:  # noqa: BLE001 - 네이버 쇼핑 크롤링/분석 읽기전용 API - 실패시 빈 결과+error 필드 반환, warning 로그만 남김
        logger.warning("[SHOPPING-ANALYSIS-BRANDS-ERR] %s", e)
        result = {"brands": [], "total_brands": 0, "error": str(e)}
    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_SHOPPING_ANALYSIS_BRANDS",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"query={query} top_n={top_n} duration_ms={duration_ms}",
    )
    return {**result, "duration_ms": duration_ms}


@naver_search_router.get("/shopping-search/analysis/keywords")
def api_keyword_summary(
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """키워드별 요약: 상품수, 가격 min/avg/max, 업체수, 브랜드수."""
    import sys

    sys.path.insert(0, str(repo_root()))

    t0 = time.monotonic()
    try:
        from scripts.naver.shopping.analysis import keyword_summary

        result = keyword_summary()
    except Exception as e:  # noqa: BLE001 - 네이버 쇼핑 크롤링/분석 읽기전용 API - 실패시 빈 결과+error 필드 반환, warning 로그만 남김
        logger.warning("[SHOPPING-ANALYSIS-KEYWORDS-ERR] %s", e)
        result = {"keywords": [], "total_products": 0, "error": str(e)}
    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_SHOPPING_ANALYSIS_KEYWORDS",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
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

    sys.path.insert(0, str(repo_root()))

    t0 = time.monotonic()
    try:
        from scripts.naver.shopping.analysis import competition_score

        result = competition_score(query)
    except Exception as e:  # noqa: BLE001 - 네이버 쇼핑 크롤링/분석 읽기전용 API - 실패시 빈 결과+error 필드 반환, warning 로그만 남김
        logger.warning("[SHOPPING-ANALYSIS-COMPETITION-ERR] %s", e)
        result = {"keyword": query, "score": 0, "error": str(e)}
    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_SHOPPING_ANALYSIS_COMPETITION",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"query={query} score={result.get('score')} duration_ms={duration_ms}",
    )
    return {**result, "duration_ms": duration_ms}


__all__ = ["naver_search_router"]

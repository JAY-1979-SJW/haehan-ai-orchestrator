"""네이버 뉴스 스크래핑 read-only 엔드포인트 (/api/v1/external/naver/news-*).

- CDP 브라우저 세션 기반 (scrape_news.py 재사용).
- 쓰기 API 없음. 모두 read-only.
- CDP 미연결 시 503 반환.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends

from ..audit_logger import log_event
from ..auth import require_role

logger = logging.getLogger(__name__)

naver_news_router = APIRouter(
    prefix="/external/naver",
    tags=["naver-news"],
)


def _import_scraper():
    import importlib
    return importlib.import_module("scripts.naver.scrape_news")


@naver_news_router.get("/news-main")
def api_news_main(
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """네이버 뉴스 메인 — 언론사별 기사 블록."""
    t0 = time.monotonic()
    try:
        m = _import_scraper()
        blocks = m.fetch_news()
    except Exception as exc:
        logger.error("news-main error: %s", exc)
        raise HTTPException(status_code=503, detail=f"CDP 브라우저 오류: {exc}")
    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_NEWS_MAIN_READ",
        task_id="-",
        actor=user["actor"], role=user["role"], decision="ok",
        note=f"blocks={len(blocks)} duration_ms={duration_ms}",
    )
    return {"blocks": blocks, "total": len(blocks), "duration_ms": duration_ms}


@naver_news_router.get("/news-search")
def api_news_search(
    query: str,
    page: int = 1,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """네이버 뉴스 검색."""
    if not query.strip():
        raise HTTPException(status_code=400, detail="query 필수")
    t0 = time.monotonic()
    try:
        m = _import_scraper()
        items = m.fetch_search(query.strip(), page=page)
    except Exception as exc:
        logger.error("news-search error: %s", exc)
        raise HTTPException(status_code=503, detail=f"CDP 브라우저 오류: {exc}")
    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_NEWS_SEARCH_READ",
        task_id="-",
        actor=user["actor"], role=user["role"], decision="ok",
        note=f"query={query!r} page={page} results={len(items)} duration_ms={duration_ms}",
    )
    return {"items": items, "total": len(items), "query": query, "page": page, "duration_ms": duration_ms}


@naver_news_router.get("/news-article")
def api_news_article(
    url: str,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """네이버 뉴스 기사 본문 + 요약."""
    if not url.strip():
        raise HTTPException(status_code=400, detail="url 필수")
    t0 = time.monotonic()
    try:
        m = _import_scraper()
        article = m.fetch_article(url.strip())
    except Exception as exc:
        logger.error("news-article error: %s", exc)
        raise HTTPException(status_code=503, detail=f"CDP 브라우저 오류: {exc}")
    if not article:
        raise HTTPException(status_code=404, detail="기사 추출 실패")
    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_NEWS_ARTICLE_READ",
        task_id="-",
        actor=user["actor"], role=user["role"], decision="ok",
        note=f"url={url[:80]} body_len={len(article.get('body',''))} duration_ms={duration_ms}",
    )
    return {**article, "duration_ms": duration_ms}


__all__ = ["naver_news_router"]

"""네이버 뉴스 read-only 엔드포인트 (/api/v1/external/naver/news-*).

- news-main : CDP 기반 (네이버 뉴스 메인 언론사별 블록)
- news-search: Naver OpenAPI 기반 (CDP 불필요, 25,000/일 허용)
- news-article: CDP 기반 (기사 본문 추출)
- 쓰기 API 없음. 모두 read-only.
"""

from __future__ import annotations

import html
import logging
import os
import time
import urllib.parse
import urllib.request

from fastapi import APIRouter, Depends, HTTPException

from tools.gates.auth import require_role

from ...audit.audit_logger import log_event

logger = logging.getLogger(__name__)

naver_news_router = APIRouter(
    prefix="/external/naver",
    tags=["naver-news"],
)


def _import_scraper():
    import importlib

    return importlib.import_module("scripts.naver.scrape_news")


def _naver_openapi_news(query: str, page: int = 1, display: int = 10) -> list[dict]:
    """Naver OpenAPI /v1/search/news.json 호출 — CDP 불필요."""
    client_id = os.environ.get("NAVER_OPENAPI_CLIENT_ID", "")
    client_secret = os.environ.get("NAVER_OPENAPI_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise RuntimeError("NAVER_OPENAPI_CLIENT_ID / SECRET 환경변수 미설정")

    start = (page - 1) * display + 1
    params = urllib.parse.urlencode({"query": query, "display": display, "start": start, "sort": "date"})
    url = f"https://openapi.naver.com/v1/search/news.json?{params}"

    req = urllib.request.Request(
        url,
        headers={
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
        },
    )
    import json

    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
        data = json.loads(resp.read().decode())

    items = []
    for it in data.get("items", []):
        items.append(
            {
                "title": html.unescape(it.get("title", "").replace("<b>", "").replace("</b>", "")),
                "url": it.get("originallink") or it.get("link", ""),
                "press": "",
                "datetime": it.get("pubDate", ""),
                "summary": html.unescape(it.get("description", "").replace("<b>", "").replace("</b>", "")),
            }
        )
    return items


@naver_news_router.get("/news-main")
def api_news_main(
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """네이버 뉴스 메인 — 언론사별 기사 블록 (CDP)."""
    t0 = time.monotonic()
    try:
        m = _import_scraper()
        blocks = m.fetch_news()
    except Exception as exc:
        logger.error("news-main error: %s", exc)
        raise HTTPException(status_code=503, detail=f"CDP 브라우저 오류: {exc}") from exc
    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_NEWS_MAIN_READ",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"blocks={len(blocks)} duration_ms={duration_ms}",
    )
    return {"blocks": blocks, "total": len(blocks), "duration_ms": duration_ms}


@naver_news_router.get("/news-search")
def api_news_search(
    query: str,
    page: int = 1,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """네이버 뉴스 검색 — Naver OpenAPI 기반 (CDP 불필요)."""
    if not query.strip():
        raise HTTPException(status_code=400, detail="query 필수")
    t0 = time.monotonic()
    try:
        items = _naver_openapi_news(query.strip(), page=page)
    except Exception as exc:
        logger.error("news-search error: %s", exc)
        raise HTTPException(status_code=503, detail=f"뉴스 검색 오류: {exc}") from exc
    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_NEWS_SEARCH_READ",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"query={query!r} page={page} results={len(items)} duration_ms={duration_ms}",
    )
    return {"items": items, "total": len(items), "query": query, "page": page, "duration_ms": duration_ms}


@naver_news_router.get("/news-article")
def api_news_article(
    url: str,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """네이버 뉴스 기사 본문 + 요약 (CDP)."""
    if not url.strip():
        raise HTTPException(status_code=400, detail="url 필수")
    t0 = time.monotonic()
    try:
        m = _import_scraper()
        article = m.fetch_article(url.strip())
    except Exception as exc:
        logger.error("news-article error: %s", exc)
        raise HTTPException(status_code=503, detail=f"CDP 브라우저 오류: {exc}") from exc
    if not article:
        raise HTTPException(status_code=404, detail="기사 추출 실패")
    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(
        "NAVER_NEWS_ARTICLE_READ",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"url={url[:80]} body_len={len(article.get('body', ''))} duration_ms={duration_ms}",
    )
    return {**article, "duration_ms": duration_ms}


__all__ = ["naver_news_router"]

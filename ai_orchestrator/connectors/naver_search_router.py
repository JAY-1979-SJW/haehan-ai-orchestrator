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


__all__ = ["naver_search_router"]

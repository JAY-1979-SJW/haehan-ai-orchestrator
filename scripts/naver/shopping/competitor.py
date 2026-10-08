"""경쟁사 조사 — 게이트 + 기존 CompetitorAnalysis 통합."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # repo root (2026-08-14: [4]는 저장소 밖 C:\work 를 가리켰음)
sys.path.insert(0, str(ROOT))

from .gate import gate_competitor  # noqa: E402  (sys.path 설정 후 import)
from .search import search_shopping  # noqa: E402  (sys.path 설정 후 import)


def analyze_competitor(keyword: str, display: int = 20) -> dict:
    """경쟁사 가격/상품 수집 — NOTIFY 게이트."""
    gate_competitor(keyword)
    result = search_shopping(keyword, display=display)
    return result


def price_summary(keyword: str) -> dict:
    """수집된 데이터에서 가격 통계 반환."""
    gate_competitor(keyword)
    from scripts.naver.shopping import naver_search_queries as q

    page = q.search_shopping_items(query=keyword, limit=100, offset=0)
    items = page.items
    prices = [i.get("lprice") for i in items if i.get("lprice")]
    if not prices:
        return {"keyword": keyword, "count": 0}
    return {
        "keyword": keyword,
        "count": len(prices),
        "min_price": min(prices),
        "max_price": max(prices),
        "avg_price": sum(prices) // len(prices),
        "items": items[:10],
    }

"""Naver Shopping competitor exploration helpers."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

from scripts.common.json_report import save_json_report
from scripts.naver.shopping.naver_shopping_collectors import collect_shopping_search

DATA_DIR = Path("data")
LATEST_PATH = DATA_DIR / "naver_shopping_competitors_latest.json"


def _prices(items: list[dict[str, Any]]) -> list[int]:
    return [int(p) for p in (item.get("lprice") or item.get("price") for item in items) if isinstance(p, int) and p >= 0]


def analyze_competitors(
    query: str,
    items: list[dict[str, Any]],
    *,
    my_price: int | None = None,
    my_mall: str = "",
) -> dict[str, Any]:
    prices = _prices(items)
    mall_counter = Counter((item.get("mall_name") or item.get("seller") or "").strip() for item in items)
    brand_counter = Counter((item.get("brand") or "").strip() for item in items)

    cheaper_count = 0
    if my_price is not None:
        cheaper_count = sum(1 for price in prices if price < my_price)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "workflow": "naver_shopping_competitor_explore",
        "query": query,
        "item_count": len(items),
        "source": "naver_openapi_shop_or_browser",
        "my_price": my_price,
        "my_mall": my_mall,
        "stats": {
            "min_price": min(prices) if prices else None,
            "max_price": max(prices) if prices else None,
            "avg_price": int(mean(prices)) if prices else None,
            "cheaper_than_my_price": cheaper_count if my_price is not None else None,
            "price_rank_estimate": cheaper_count + 1 if my_price is not None else None,
        },
        "top_malls": [{"mall": mall, "count": count} for mall, count in mall_counter.most_common(10) if mall],
        "top_brands": [{"brand": brand, "count": count} for brand, count in brand_counter.most_common(10) if brand],
        "items": items,
    }


def collect_openapi_competitors(
    query: str,
    *,
    display: int = 20,
    sort: str = "sim",
    my_price: int | None = None,
    my_mall: str = "",
) -> dict[str, Any]:
    result = collect_shopping_search(query, display=display, sort=sort)
    items = [item if isinstance(item, dict) else item.to_dict() for item in result.items]
    analysis = analyze_competitors(query, items, my_price=my_price, my_mall=my_mall)
    analysis["collection_status"] = result.status
    analysis["error_code"] = result.error_code
    analysis["error_message"] = result.error_message
    return analysis


def save_competitor_report(report: dict[str, Any], output: str | Path | None = None) -> Path:
    return save_json_report(report, DATA_DIR, LATEST_PATH, output)


def print_competitor_summary(report: dict[str, Any], path: Path) -> None:
    stats = report.get("stats", {})
    print("Naver Shopping competitor report")
    print(f"  query: {report.get('query')}")
    print(f"  status: {report.get('collection_status', report.get('status', 'ok'))}")
    print(f"  items: {report.get('item_count')}")
    print(f"  min/avg/max: {stats.get('min_price')} / {stats.get('avg_price')} / {stats.get('max_price')}")
    if stats.get("price_rank_estimate") is not None:
        print(f"  price_rank_estimate: {stats.get('price_rank_estimate')}")
    print(f"saved: {path}")


__all__ = [
    "analyze_competitors",
    "collect_openapi_competitors",
    "print_competitor_summary",
    "save_competitor_report",
]

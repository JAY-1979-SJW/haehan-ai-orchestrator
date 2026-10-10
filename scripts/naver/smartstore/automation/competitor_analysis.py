"""경쟁사 분석 — 네이버쇼핑 검색 + 가격 비교 + 리뷰 모니터링.

기능:
  - 키워드로 네이버쇼핑 상위 상품 자동 수집
  - 내 상품 vs 경쟁사 가격/리뷰 비교
  - 가격 변동 시계열 추적 (DB)
"""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page

from ai_orchestrator.paths.runtime import data_dir
from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger
from scripts.common.sqlite_helpers import init_sqlite_schema

_log = get_logger(__name__)
ROOT = Path(__file__).resolve().parents[3]
DB_PATH = data_dir() / "cdp.db"  # 예전 ROOT(parents[3])는 저장소 루트가 아니라 scripts/ 라 data/cdp.db 와 다른 DB 를 쓰던 버그


def _init_db():
    init_sqlite_schema(
        DB_PATH,
        (
            """
        CREATE TABLE IF NOT EXISTS competitor_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            keyword TEXT NOT NULL,
            seller TEXT,
            product_name TEXT,
            price INTEGER,
            review_count INTEGER,
            rating REAL,
            url TEXT
        )
    """,
            "CREATE INDEX IF NOT EXISTS idx_comp_kw ON competitor_prices(keyword, ts)",
        ),
    )


class CompetitorAnalysis:
    """경쟁사 가격/리뷰 자동 분석."""

    def __init__(self, page: Page):
        self.page = page

    def search_naver_shopping(self, keyword: str, limit: int = 20) -> list[dict]:
        """네이버쇼핑에서 키워드 검색 → 상위 상품 추출."""
        url = f"https://search.shopping.naver.com/search/all?query={keyword}"
        self.page.goto(url, timeout=20000, wait_until="domcontentloaded")
        time.sleep(3)

        products = self.page.evaluate(
            """
        (limit) => {
            const out = [];
            document.querySelectorAll('[class*="product_item"], li[class*="basicList_item"], [class*="search_item"]').forEach((el, i) => {
                if (i >= limit) return;
                const name = el.querySelector('[class*="title"], a[class*="link"]')?.innerText?.trim() || '';
                const priceText = el.querySelector('[class*="price"]')?.innerText?.trim() || '';
                const priceM = /([\\d,]+)/.exec(priceText);
                const price = priceM ? parseInt(priceM[1].replace(/,/g, '')) : null;
                const seller = el.querySelector('[class*="mall"], [class*="seller"]')?.innerText?.trim() || '';
                const reviewText = el.querySelector('[class*="review"]')?.innerText || '';
                const reviewM = /([\\d,]+)/.exec(reviewText);
                const reviews = reviewM ? parseInt(reviewM[1].replace(/,/g, '')) : null;
                const ratingText = el.querySelector('[class*="rating"], [class*="star"]')?.innerText || '';
                const ratingM = /([\\d.]+)/.exec(ratingText);
                const rating = ratingM ? parseFloat(ratingM[1]) : null;
                const link = el.querySelector('a')?.href || '';
                if (name) out.push({name: name.substring(0, 100), price, seller, reviews, rating, url: link.substring(0, 200)});
            });
            return out;
        }
        """,
            limit,
        )
        return products

    def track_competitors(self, keyword: str, limit: int = 20) -> dict:
        """경쟁사 가격 추적 + DB 시계열 저장."""
        products = self.search_naver_shopping(keyword, limit)
        if not products:
            return {"ok": False, "error": "no_products"}

        _init_db()
        now = datetime.now().isoformat(timespec="seconds")
        conn = sqlite3.connect(str(DB_PATH))
        for p in products:
            conn.execute(
                """INSERT INTO competitor_prices
                   (ts, keyword, seller, product_name, price, review_count, rating, url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    now,
                    keyword,
                    p.get("seller", ""),
                    p.get("name", ""),
                    p.get("price"),
                    p.get("reviews"),
                    p.get("rating"),
                    p.get("url", ""),
                ),
            )
        conn.commit()
        conn.close()

        # 통계
        prices = [p["price"] for p in products if p.get("price")]
        log_critical(
            "OTHER",
            f"경쟁사 가격 추적: '{keyword}' {len(products)}건",
            keyword=keyword,
            count=len(products),
            mode="competitor_track",
        )

        return {
            "ok": True,
            "keyword": keyword,
            "count": len(products),
            "products": products,
            "stats": {
                "min_price": min(prices) if prices else None,
                "max_price": max(prices) if prices else None,
                "avg_price": sum(prices) // len(prices) if prices else None,
            },
        }

    def price_history(self, keyword: str, days: int = 30) -> list[dict]:
        """키워드의 가격 시계열 조회."""
        _init_db()
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT ts, MIN(price) min_p, MAX(price) max_p, AVG(price) avg_p, COUNT(*) cnt
               FROM competitor_prices
               WHERE keyword = ? AND ts >= datetime('now', ?, 'localtime')
               GROUP BY date(ts)
               ORDER BY ts""",
            (keyword, f"-{days} days"),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def compare_with_my_price(self, keyword: str, my_price: int) -> dict:
        """내 가격 vs 경쟁사 비교."""
        r = self.track_competitors(keyword)
        if not r.get("ok"):
            return r
        stats = r["stats"]
        diff_avg = my_price - (stats["avg_price"] or my_price)
        ranking = sum(1 for p in r["products"] if p.get("price") and p["price"] < my_price) + 1
        return {
            "ok": True,
            "my_price": my_price,
            "competitor_stats": stats,
            "rank": ranking,  # 가격 순위 (낮을수록 저렴)
            "diff_from_avg": diff_avg,
            "recommendation": (
                "가격 경쟁력 양호" if diff_avg < 0 else "평균보다 비쌈 - 인하 검토" if diff_avg > 0 else "평균 수준"
            ),
        }

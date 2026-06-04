"""네이버쇼핑 CDP 크롤러 — 리뷰 수·별점·판매정보 포함 수집.

OpenAPI로 못 가져오는 항목:
  - review_count (리뷰 수)
  - rating       (별점)
  - rank         (검색 순위)
  - delivery     (배송 정보)

수집 대상: search.shopping.naver.com/search/all?query=<keyword>
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DB_PATH = ROOT / "data" / "shopping_competitor_v2.db"

# ── JS: 네이버쇼핑 텍스트 파싱 기반 추출 (SPA 대응) ──────────────────
_EXTRACT_JS = r"""
(limit) => {
    const items = [];
    // 가격(원) 포함 + 일정 크기 이상 블록 = 상품 카드
    const allEls = [...document.querySelectorAll('div,li,article,section')].filter(el => {
        const t = el.innerText || '';
        return t.includes('원') && t.length > 60 && t.length < 2500
            && el.querySelectorAll('a').length > 0
            && !el.querySelector('[class*="filter"]')
            && !el.querySelector('[class*="search_tool"]');
    });
    // 가장 작은 요소 우선 (상위 컨테이너 제거)
    const seen = new Set();
    const cards = allEls.filter(el => {
        for (const p of allEls) {
            if (p !== el && p.contains(el) && (el.innerText||'').length < (p.innerText||'').length * 0.8) return true;
        }
        return false;
    }).slice(0, limit);

    cards.forEach((card, idx) => {
        const txt = card.innerText || '';

        // 상품명: a 태그 중 적당한 길이
        let title = '';
        for (const a of card.querySelectorAll('a')) {
            const t = (a.innerText || '').trim().replace(/\s+/g,' ');
            if (t.length >= 6 && t.length <= 100
                && !t.match(/바로가기|찜하기|정보|브랜드|공식몰|더보기/)) {
                title = t; break;
            }
        }
        if (!title) return;

        // 가격
        const priceM = txt.match(/(\d[\d,]{2,})원/);
        const price = priceM ? parseInt(priceM[1].replace(/,/g,'')) : null;

        // 별점
        const ratingM = txt.match(/별점\s*([\d.]+)/);
        const rating = ratingM ? parseFloat(ratingM[1]) : null;

        // 리뷰 수
        const reviewM = txt.match(/리뷰\s*[(\[]?([\d,]+)[)\]]?/);
        const review_count = reviewM ? parseInt(reviewM[1].replace(/,/g,'')) : null;

        // 구매 수
        const buyM = txt.match(/구매\s*([\d,]+)/);
        const buy_count = buyM ? parseInt(buyM[1].replace(/,/g,'')) : null;

        // 찜 수
        const wishM = txt.match(/찜하기\s*([\d,]+)/);
        const wish_count = wishM ? parseInt(wishM[1].replace(/,/g,'')) : null;

        // 판매몰
        const mallM = txt.match(/([가-힣a-zA-Z0-9]+)정보\s*$/m);
        const mall = mallM ? mallM[1].trim().slice(0,30) : '';

        // 배송
        const delivM = txt.match(/(무료배송|내일배송|오늘출발|당일배송|[\d]+일 이내)/);
        const delivery = delivM ? delivM[1] : '';

        // 링크
        const linkEl = card.querySelector('a[href*="shopping.naver.com"]') || card.querySelector('a');
        const link = (linkEl||{}).href || '';

        items.push({
            rank: items.length + 1,
            title,
            price,
            mall,
            rating,
            review_count,
            buy_count,
            wish_count,
            delivery,
            link: link.slice(0,200),
        });
    });
    return items;
}
"""


def _init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shopping_items (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            collected_at TEXT NOT NULL,
            keyword      TEXT NOT NULL,
            rank         INTEGER,
            title        TEXT,
            price        INTEGER,
            mall         TEXT,
            brand        TEXT,
            review_count INTEGER,
            buy_count    INTEGER,
            wish_count   INTEGER,
            rating       REAL,
            delivery     TEXT,
            link         TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS ix_shop_kw ON shopping_items(keyword, collected_at)")
    conn.commit()
    conn.close()


def crawl_shopping(
    keyword: str,
    limit: int = 40,
    cdp_port: int = 9222,
) -> dict:
    """CDP 브라우저로 네이버쇼핑 크롤링 — 리뷰/별점 포함."""
    import urllib.request

    import websocket

    # CDP 탭 획득
    with urllib.request.urlopen(f"http://127.0.0.1:{cdp_port}/json/list", timeout=3) as r:
        pages = [t for t in json.loads(r.read()) if t.get("type") == "page"]
    if not pages:
        return {"ok": False, "error": "no_cdp_page"}

    tab = pages[0]
    ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=15, suppress_origin=True)

    def send(mid, method, params=None, timeout=15.0):
        ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            ws.settimeout(max(0.5, deadline - time.time()))
            try:
                m = json.loads(ws.recv())
                if m.get("id") == mid:
                    return m
            except Exception:
                return {}
        return {}

    # 페이지 이동
    url = f"https://search.shopping.naver.com/search/all?query={keyword}&sort=rel"
    send(1, "Page.navigate", {"url": url}, timeout=15)
    time.sleep(4)

    # 스크롤 (더 많은 상품 로딩)
    for _ in range(3):
        send(2, "Runtime.evaluate", {"expression": "window.scrollBy(0, 1200)"})
        time.sleep(1)

    # 상품 추출
    r = send(
        3,
        "Runtime.evaluate",
        {
            "expression": f"JSON.stringify(({_EXTRACT_JS})({limit}))",
            "returnByValue": True,
        },
        timeout=15,
    )
    ws.close()

    raw = r.get("result", {}).get("result", {}).get("value", "[]")
    try:
        products = json.loads(raw)
    except Exception:
        products = []

    # 제목 기준 중복 제거 + 재순위
    seen_titles: set = set()
    deduped = []
    for p in products:
        t = (p.get("title") or "").strip()
        if t and t not in seen_titles:
            seen_titles.add(t)
            p["rank"] = len(deduped) + 1
            deduped.append(p)
    products = deduped

    if not products:
        return {"ok": False, "error": "no_products", "keyword": keyword}

    # DB 저장
    _init_db()
    now = datetime.now().isoformat(timespec="seconds")
    conn = sqlite3.connect(str(DB_PATH))
    for p in products:
        conn.execute(
            """INSERT INTO shopping_items
               (collected_at, keyword, rank, title, price, mall, brand,
                review_count, buy_count, wish_count, rating, delivery, link)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                now,
                keyword,
                p.get("rank"),
                p.get("title"),
                p.get("price"),
                p.get("mall"),
                p.get("brand"),
                p.get("review_count"),
                p.get("buy_count"),
                p.get("wish_count"),
                p.get("rating"),
                p.get("delivery"),
                p.get("link"),
            ),
        )
    conn.commit()
    conn.close()

    # 통계 계산
    prices = [p["price"] for p in products if p.get("price")]
    reviews = [p["review_count"] for p in products if p.get("review_count")]
    ratings = [p["rating"] for p in products if p.get("rating")]

    return {
        "ok": True,
        "keyword": keyword,
        "count": len(products),
        "products": products,
        "stats": {
            "price": {
                "min": min(prices) if prices else None,
                "avg": sum(prices) // len(prices) if prices else None,
                "max": max(prices) if prices else None,
            },
            "review": {
                "min": min(reviews) if reviews else None,
                "avg": sum(reviews) // len(reviews) if reviews else None,
                "max": max(reviews) if reviews else None,
                "total": sum(reviews) if reviews else 0,
            },
            "rating": {
                "avg": round(sum(ratings) / len(ratings), 2) if ratings else None,
                "max": max(ratings) if ratings else None,
            },
        },
    }


def query_items(keyword: str, days: int = 30, limit: int = 100) -> list[dict]:
    """수집된 데이터 조회 — 최근 N일."""
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT * FROM shopping_items
           WHERE keyword = ?
             AND collected_at >= datetime('now', ?, 'localtime')
           ORDER BY collected_at DESC, rank ASC
           LIMIT ?""",
        (keyword, f"-{days} days", limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def full_summary(keyword: str) -> dict:
    """전체 통계 요약."""
    items = query_items(keyword)
    if not items:
        return {"keyword": keyword, "count": 0}

    prices = [i["price"] for i in items if i.get("price")]
    reviews = [i["review_count"] for i in items if i.get("review_count")]
    ratings = [i["rating"] for i in items if i.get("rating")]

    return {
        "keyword": keyword,
        "count": len(items),
        "price": {"min": min(prices), "avg": sum(prices) // len(prices), "max": max(prices)} if prices else {},
        "review": {"min": min(reviews), "avg": sum(reviews) // len(reviews), "max": max(reviews), "total": sum(reviews)}
        if reviews
        else {},
        "rating": {"avg": round(sum(ratings) / len(ratings), 2), "max": max(ratings)} if ratings else {},
        "top10": items[:10],
    }

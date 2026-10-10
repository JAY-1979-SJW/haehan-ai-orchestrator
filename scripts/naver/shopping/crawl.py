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

from ai_orchestrator.paths.runtime import data_dir

ROOT = Path(__file__).resolve().parents[3]  # repo root (2026-08-14: [4]는 저장소 밖 C:\work 를 가리켰음)
DB_PATH = data_dir() / "shopping_competitor_v2.db"

# ── JS: 네이버쇼핑 상품 카드 추출 ────────────────────────────────────
# 실측(2026-08-14): 검색결과 페이지는 **가상 스크롤(windowing)** 이라 화면에 보이는
# 카드만 DOM 에 존재하고 스크롤하면 이전 카드가 제거된다. 따라서 "끝까지 스크롤 후
# 한 번에 추출" 하면 마지막 화면의 5건 정도만 남는다(전체 2,972건인데도).
# → crawl_shopping() 이 스크롤 도중 매 스텝마다 이 함수를 호출해 증분 수집한다.
#
# 카드 컨테이너 실측 클래스:
#   광고 상품 : adProduct_item__*
#   일반 상품 : product_item__*
_EXTRACT_JS = r"""
(() => {
    const cards = document.querySelectorAll(
        '[class*="adProduct_item"],[class*="product_item"]'
    );
    const items = [];

    cards.forEach((card) => {
        const cls = (typeof card.className === 'string') ? card.className : '';
        const isAd = /adProduct/.test(cls);
        const txt = card.innerText || '';

        const q = (sel) => {
            const e = card.querySelector(sel);
            return e ? (e.innerText || '').trim() : '';
        };

        // ── 상품명: title 영역 우선, 없으면 a 태그 중 본문성 텍스트
        let title = q('[class*="_title"] a') || q('[class*="_title"]');
        if (!title) {
            for (const a of card.querySelectorAll('a')) {
                const t = (a.innerText || '').trim().replace(/\s+/g, ' ');
                if (t.length >= 8 &&
                    !/^(광고|찜하기|구매|정상가|할인율|배송비|리뷰)/.test(t)) {
                    title = t;
                    break;
                }
            }
        }
        title = title.replace(/\s+/g, ' ').trim();
        if (!title) return;

        // 필터 UI/카테고리 링크가 상품으로 오탐되던 문제 방지
        if (/^조명종류\s*:/.test(title)) return;

        // ── 가격: price 영역 안에서만 파싱 (배송비 오인 방지)
        const priceScope = q('[class*="price_area"]') || txt;
        const pm = priceScope.match(/([\d,]{3,})\s*원/);
        const price = pm ? parseInt(pm[1].replace(/,/g, '')) : null;

        // ── 판매처
        const mall = q('[class*="mall"]').replace(/\s+/g, ' ').slice(0, 40);

        // ── 지표 (키워드 뒤 숫자만 — 임의 소수 오인 방지)
        const rv = txt.match(/리뷰\s*[(\[]?([\d,]+)/);
        const rt = txt.match(/별점\s*([\d.]+)/);
        const by = txt.match(/구매\s*([\d,]+)/);
        const wi = txt.match(/찜하기\s*([\d,]+)/);
        const dl = txt.match(/(무료배송|내일배송|오늘출발|당일배송)/);

        const a = card.querySelector('a[href]');

        items.push({
            title,
            price,
            mall,
            is_ad: isAd,
            rating: rt ? parseFloat(rt[1]) : null,
            review_count: rv ? parseInt(rv[1].replace(/,/g, '')) : null,
            buy_count: by ? parseInt(by[1].replace(/,/g, '')) : null,
            wish_count: wi ? parseInt(wi[1].replace(/,/g, '')) : null,
            delivery: dl ? dl[1] : '',
            link: (a ? a.href : '').slice(0, 300),
        });
    });
    return items;
})()
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
    # 광고/일반 구분 — 가격 통계에서 광고가 섞이면 왜곡되므로 분리 저장(2026-08-14 추가).
    cols = {row[1] for row in conn.execute("PRAGMA table_info(shopping_items)")}
    if "is_ad" not in cols:
        conn.execute("ALTER TABLE shopping_items ADD COLUMN is_ad INTEGER DEFAULT 0")
    conn.commit()
    conn.close()


def _save_products(keyword: str, products: list[dict]) -> None:
    """수집 결과를 DB 에 저장."""
    _init_db()
    now = datetime.now().isoformat(timespec="seconds")
    conn = sqlite3.connect(str(DB_PATH))
    for p in products:
        conn.execute(
            """INSERT INTO shopping_items
               (collected_at, keyword, rank, title, price, mall, brand,
                review_count, buy_count, wish_count, rating, delivery, link, is_ad)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                1 if p.get("is_ad") else 0,
            ),
        )
    conn.commit()
    conn.close()


def _build_result(keyword: str, products: list[dict]) -> dict:
    """통계 계산 + 결과 dict 생성."""
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


def _scroll_collect(send, extract_visible, collected: dict[str, dict], limit: int) -> None:
    """스크롤하며 증분 수집 — 새 항목이 안 나오면 조기 종료."""
    stagnant = 0
    for _ in range(60):
        for item in extract_visible():
            key = (item.get("link") or "").strip() or (item.get("title") or "").strip()
            if key and key not in collected:
                collected[key] = item
                stagnant = -1  # 아래에서 +1 되어 0
        stagnant += 1
        if len(collected) >= limit:
            break
        if stagnant >= 6:  # 6스텝 연속 신규 0건 → 페이지 끝
            break
        send("Runtime.evaluate", {"expression": "window.scrollBy(0, 700)"})
        time.sleep(0.9)


def _cdp_send(ws, counter: dict, method, params=None, timeout=20.0):
    """CDP 명령 전송 후 같은 id 의 응답을 기다린다(실패/타임아웃은 빈 dict)."""
    counter["mid"] += 1
    mid = counter["mid"]
    ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
    deadline = time.time() + timeout
    while time.time() < deadline:
        ws.settimeout(max(0.5, deadline - time.time()))
        try:
            m = json.loads(ws.recv())
            if m.get("id") == mid:
                return m
        except Exception:  # noqa: BLE001 - DOM에서 추출한 JSON 파싱 실패시 빈 dict/list로 안전 폴백 — 읽기전용 공개 검색결과 스크래핑
            return {}
    return {}


def crawl_shopping(
    keyword: str,
    limit: int = 40,
    cdp_port: int = 9222,
    max_pages: int = 1,
) -> dict:
    """CDP 브라우저로 네이버쇼핑 크롤링 — 리뷰/별점 포함.

    가상 스크롤 대응(2026-08-14): 검색결과는 보이는 카드만 DOM 에 유지하므로
    "스크롤 완료 후 일괄 추출" 이 아니라 **스크롤 스텝마다 추출해 누적**한다.
    max_pages > 1 이면 pagingIndex 로 다음 페이지까지 이어서 수집한다.
    """
    import urllib.parse
    import urllib.request

    import websocket

    # CDP 탭 획득
    with urllib.request.urlopen(f"http://127.0.0.1:{cdp_port}/json/list", timeout=3) as r:
        pages = [t for t in json.loads(r.read()) if t.get("type") == "page"]
    if not pages:
        return {"ok": False, "error": "no_cdp_page"}

    tab = pages[0]
    ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=20, suppress_origin=True)

    counter = {"mid": 0}

    def send(method, params=None, timeout=20.0):
        return _cdp_send(ws, counter, method, params, timeout)

    def extract_visible() -> list[dict]:
        r = send(
            "Runtime.evaluate",
            {"expression": f"JSON.stringify({_EXTRACT_JS})", "returnByValue": True},
            timeout=20,
        )
        raw = r.get("result", {}).get("result", {}).get("value", "[]")
        try:
            return json.loads(raw) or []
        except Exception:  # noqa: BLE001 - DOM에서 추출한 JSON 파싱 실패시 빈 dict/list로 안전 폴백 — 읽기전용 공개 검색결과 스크래핑
            return []

    collected: dict[str, dict] = {}  # key(link|title) → item
    pages_done = 0

    try:
        for page_idx in range(1, max(1, int(max_pages)) + 1):
            q = urllib.parse.quote(keyword)
            url = (
                f"https://search.shopping.naver.com/search/all?query={q}&sort=rel&pagingIndex={page_idx}&pagingSize=80"
            )
            send("Page.navigate", {"url": url}, timeout=20)
            time.sleep(4.0)
            pages_done += 1

            # 스크롤하며 증분 수집 — 새 항목이 안 나오면 조기 종료
            _scroll_collect(send, extract_visible, collected, limit)

            if len(collected) >= limit:
                break
    finally:
        ws.close()

    products = list(collected.values())[:limit]
    for i, p in enumerate(products, start=1):
        p["rank"] = i

    if not products:
        return {"ok": False, "error": "no_products", "keyword": keyword}

    # DB 저장
    _save_products(keyword, products)

    # 통계 계산
    return _build_result(keyword, products)


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

"""네이버 쇼핑 검색결과에서 **직접 상품 URL** 추출 (adcr 우회).

배경(2026-08-15 실측):
    검색결과 카드의 링크는 전부 `cr.shopping.naver.com/adcr?x=...` 광고 클릭 추적이다.
    이를 자동으로 대량 호출하면 광고주에게 클릭당 과금이 발생하는 부정클릭이 되고,
    실제로 재사용 시 `Bad Request` 로 만료되기도 한다.

    반면 페이지 HTML 에는 `smartstore.naver.com/{store}/products/{id}` 형태의
    **직접 URL 이 그대로 남아 있다**(1회 검색에서 39건 확인).
    → 광고 클릭 없이, 만료 없이 상세페이지에 접근할 수 있다.

    ⚠ 2026-08-15 실측: 검색결과 상품 배열은 `__NEXT_DATA__` 에 **없다**.
      클라이언트에서 별도 API 로 받아오므로 SSR 상태에는 프로모션 배열
      (superSavingProducts 등)만 들어 있다. 그래서 구조화 데이터에 의존하지 않고
      **HTML 의 직접 URL 만** 신뢰 소스로 쓴다. 가격·옵션은 상세페이지에서 얻는다.

주의: 반환된 URL 만 사용하고, adcr 링크는 절대 열지 않는다.
"""

from __future__ import annotations

import re
import time
import urllib.parse
from typing import Any

DIRECT_URL_RE = re.compile(r"smartstore\.naver\.com/[a-zA-Z0-9_-]+/products/\d+")

SEARCH_URL = "https://search.shopping.naver.com/search/all?query={q}&sort=rel&pagingIndex={p}"

# 이 접두어가 붙은 링크는 광고 클릭 추적이므로 사용 금지
FORBIDDEN_PREFIX = "cr.shopping.naver.com"


def is_safe_product_url(url: str) -> bool:
    """직접 상품 URL 인지 검증 — adcr 링크를 실수로 받지 않도록 방어."""
    if not url:
        return False
    if FORBIDDEN_PREFIX in url:
        return False
    return bool(DIRECT_URL_RE.search(url))


_EXTRACT_JS = r"""
() => {
  const out = {urls: [], items: []};
  const html = document.documentElement.innerHTML;
  const m = html.match(/smartstore\.naver\.com\/[a-zA-Z0-9_-]+\/products\/\d+/g);
  out.urls = m ? [...new Set(m)] : [];

  const el = document.querySelector('#__NEXT_DATA__');
  if (el) {
    try {
      const data = JSON.parse(el.textContent);
      const found = [];
      const walk = (o, d) => {
        if (d > 9 || !o || typeof o !== 'object') return;
        if (Array.isArray(o)) {
          if (o.length && o[0] && typeof o[0] === 'object' &&
              ('productTitle' in o[0] || 'productName' in o[0])) {
            o.forEach(p => found.push(p));
            return;
          }
          o.slice(0, 30).forEach(v => walk(v, d + 1));
        } else {
          Object.values(o).slice(0, 60).forEach(v => walk(v, d + 1));
        }
      };
      walk(data, 0);
      out.items = found.slice(0, 200).map(p => ({
        id: p.id ?? null,
        name: p.productName ?? p.productTitle ?? null,
        price: p.price ?? null,
        lowPrice: p.lowPrice ?? null,
        deliveryFee: p.dlvryLowPrice ?? null,
        optionCount: p.stdPrchOptCount ?? null,
        maker: p.maker ?? null,
        cat1: p.category1Name ?? null,
        cat2: p.category2Name ?? null,
        cat3: p.category3Name ?? null,
        cat4: p.category4Name ?? null,
        mallUrl: p.mallProductUrl ?? null,
      }));
    } catch (e) { out.parse_error = String(e).slice(0, 80); }
  }
  return out;
}
"""


def find_direct_urls(page: Any, keyword: str, *, max_pages: int = 3, settle_s: float = 6.0, log=None) -> dict:
    """키워드 검색 → **직접 상품 URL** 수집 (주 목적).

    items(구조화 정보)는 SSR 상태에 있을 때만 부수적으로 담기며, 비어 있는 것이
    정상이다. 가격·옵션은 반드시 상세페이지에서 확인해야 한다
    — 목록가는 최저 옵션가라 실구매가와 다르다(실측: 25,000 → 실제 33,000).
    """

    def _say(m: str) -> None:
        if log:
            log(m)

    urls: list[str] = []
    items: list[dict] = []

    for p in range(1, max(1, int(max_pages)) + 1):
        url = SEARCH_URL.format(q=urllib.parse.quote(keyword), p=p)
        page.goto(url, wait_until="domcontentloaded", timeout=40000)
        page.wait_for_timeout(int(settle_s * 1000))
        try:
            got = page.evaluate(_EXTRACT_JS)
        except Exception as e:  # noqa: BLE001 - 네이버 쇼핑 경쟁사 상품 URL 목록 읽기전용 스크래핑 — 페이지별 추출(page.evaluate) 실패를 로그로 남기고 continue로 다음 페이지 진행, 쓰기 없음.
            _say(f"  [{keyword} p{p}] 추출 실패: {type(e).__name__}")
            continue

        page_urls = [u for u in got.get("urls", []) if is_safe_product_url(u)]
        for u in page_urls:
            full = "https://" + u if not u.startswith("http") else u
            if full not in urls:
                urls.append(full)
        for it in got.get("items", []):
            items.append(it)
        _say(f"  [{keyword} p{p}] URL {len(page_urls)}건 / 상품정보 {len(got.get('items', []))}건")
        time.sleep(1.0)

    # id 기준 중복 제거
    seen_ids = set()
    uniq_items = []
    for it in items:
        k = it.get("id") or it.get("name")
        if k and k not in seen_ids:
            seen_ids.add(k)
            uniq_items.append(it)

    return {"keyword": keyword, "urls": urls, "items": uniq_items}

"""네이버 쇼핑 검색 collector — 비로그인 공개 API 전용.

수집은 검색 결과 메타데이터만 다룬다. 구매/장바구니/찜 같은 쓰기 동작 없음.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .naver_search_client import SOURCE_SHOP, NaverSearchClient, SearchResult
from .naver_search_utils import strip_html, to_int_price


@dataclass
class ShopItem:
    title: str = ""
    link: str = ""
    image: str = ""
    lprice: int | None = None
    hprice: int | None = None
    mall_name: str = ""
    product_id: str = ""
    product_type: str = ""
    brand: str = ""
    maker: str = ""
    category1: str = ""
    category2: str = ""
    category3: str = ""
    category4: str = ""
    source: str = SOURCE_SHOP

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "link": self.link,
            "image": self.image,
            "lprice": self.lprice,
            "hprice": self.hprice,
            "mall_name": self.mall_name,
            "product_id": self.product_id,
            "product_type": self.product_type,
            "brand": self.brand,
            "maker": self.maker,
            "category1": self.category1,
            "category2": self.category2,
            "category3": self.category3,
            "category4": self.category4,
            "source": self.source,
        }


@dataclass
class ShopSearchResult:
    status: str
    query: str
    items: list = field(default_factory=list)
    item_count: int = 0
    raw: dict | None = None
    error_code: str | None = None
    error_message: str | None = None
    source: str = SOURCE_SHOP

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "status": self.status,
            "query": self.query,
            "items": [i if isinstance(i, dict) else i.to_dict() for i in self.items],
            "item_count": self.item_count,
            "raw": self.raw,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


def _normalize_shop_item(raw: dict) -> dict:
    return ShopItem(
        title=strip_html(raw.get("title")),
        link=str(raw.get("link") or "").strip(),
        image=str(raw.get("image") or "").strip(),
        lprice=to_int_price(raw.get("lprice")),
        hprice=to_int_price(raw.get("hprice")),
        mall_name=strip_html(raw.get("mallName")),
        product_id=str(raw.get("productId") or "").strip(),
        product_type=str(raw.get("productType") or "").strip(),
        brand=strip_html(raw.get("brand")),
        maker=strip_html(raw.get("maker")),
        category1=strip_html(raw.get("category1")),
        category2=strip_html(raw.get("category2")),
        category3=strip_html(raw.get("category3")),
        category4=strip_html(raw.get("category4")),
    ).to_dict()


def _from_search_result(query: str, sr: SearchResult) -> ShopSearchResult:
    if sr.status in {"dry_run", "ok"}:
        items = [_normalize_shop_item(it) if isinstance(it, dict) else {} for it in sr.items]
        return ShopSearchResult(
            status=sr.status,
            query=query,
            items=items,
            item_count=len(items),
            raw=sr.raw,
        )
    return ShopSearchResult(
        status=sr.status,
        query=query,
        error_code=sr.error_code,
        error_message=sr.error_message,
        raw=sr.raw,
    )


def collect_shopping_search(
    query: str,
    *,
    display: int = 10,
    start: int = 1,
    sort: str = "sim",
    client: NaverSearchClient | None = None,
) -> ShopSearchResult:
    c = client if client is not None else NaverSearchClient()
    sr = c.search_shop(query, display=display, start=start, sort=sort)
    return _from_search_result(query, sr)


__all__ = [
    "ShopItem",
    "ShopSearchResult",
    "collect_shopping_search",
]

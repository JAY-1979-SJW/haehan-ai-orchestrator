"""네이버 블로그 검색 collector — 비로그인 공개 API 전용."""

from __future__ import annotations

from dataclasses import dataclass, field

from scripts.naver.shopping.naver_search_client import SOURCE_BLOG, NaverSearchClient, SearchResult
from scripts.naver.shopping.naver_search_utils import normalize_post_date, strip_html


@dataclass
class BlogItem:
    title: str = ""
    link: str = ""
    blogger_name: str = ""
    blogger_link: str = ""
    description: str = ""
    post_date: str = ""
    source: str = SOURCE_BLOG

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "link": self.link,
            "blogger_name": self.blogger_name,
            "blogger_link": self.blogger_link,
            "description": self.description,
            "post_date": self.post_date,
            "source": self.source,
        }


@dataclass
class BlogSearchResult:
    status: str
    query: str
    items: list = field(default_factory=list)
    item_count: int = 0
    raw: dict | None = None
    error_code: str | None = None
    error_message: str | None = None
    source: str = SOURCE_BLOG

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


def _normalize_blog_item(raw: dict) -> dict:
    return BlogItem(
        title=strip_html(raw.get("title")),
        link=str(raw.get("link") or "").strip(),
        blogger_name=strip_html(raw.get("bloggername")),
        blogger_link=str(raw.get("bloggerlink") or "").strip(),
        description=strip_html(raw.get("description")),
        post_date=normalize_post_date(raw.get("postdate")),
    ).to_dict()


def _from_search_result(query: str, sr: SearchResult) -> BlogSearchResult:
    if sr.status in {"dry_run", "ok"}:
        items = [_normalize_blog_item(it) if isinstance(it, dict) else {} for it in sr.items]
        return BlogSearchResult(
            status=sr.status,
            query=query,
            items=items,
            item_count=len(items),
            raw=sr.raw,
        )
    return BlogSearchResult(
        status=sr.status,
        query=query,
        error_code=sr.error_code,
        error_message=sr.error_message,
        raw=sr.raw,
    )


def collect_blog_search(
    query: str,
    *,
    display: int = 10,
    start: int = 1,
    sort: str = "sim",
    client: NaverSearchClient | None = None,
) -> BlogSearchResult:
    c = client if client is not None else NaverSearchClient()
    sr = c.search_blog(query, display=display, start=start, sort=sort)
    return _from_search_result(query, sr)


__all__ = [
    "BlogItem",
    "BlogSearchResult",
    "collect_blog_search",
]

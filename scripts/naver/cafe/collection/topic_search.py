"""Read-only Naver Cafe topic search helpers.

The collector navigates an existing CDP target to Naver search result pages and
extracts visible Cafe links from the DOM. It never launches, closes, joins,
writes, deletes, moves, or submits anything.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlencode

from scripts.common.gate import check as gate_check
from scripts.naver.mail.read import cdp
from scripts.naver.cafe import list_collector

SEARCH_ROOT = "https://search.naver.com/search.naver"
DEFAULT_TOPIC_KEYWORDS = [
    "인테리어",
    "셀프 인테리어",
    "조명 인테리어",
    "챗GPT",
    "AI 자동화",
    "업무 자동화",
    "부업",
    "창업",
]


@dataclass(frozen=True)
class CafeTopicSearchItem:
    keyword: str
    rank: int
    title: str
    url: str
    cafe_name: str = ""
    snippet: str = ""
    source: str = "naver_search_article"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CafeTopicSearchReport:
    ok: bool
    code: str = "ok"
    keywords: list[str] = field(default_factory=list)
    total_items: int = 0
    items: list[CafeTopicSearchItem] = field(default_factory=list)
    keyword_counts: dict[str, int] = field(default_factory=dict)
    top_cafes: list[dict[str, Any]] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "code": self.code,
            "keywords": list(self.keywords),
            "total_items": self.total_items,
            "items": [item.to_dict() for item in self.items],
            "keyword_counts": dict(self.keyword_counts),
            "top_cafes": list(self.top_cafes),
            "messages": list(self.messages),
        }


def split_keywords(raw: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if raw is None:
        return list(DEFAULT_TOPIC_KEYWORDS)
    if isinstance(raw, (list, tuple)):
        parts = [str(item) for item in raw]
    else:
        normalized = str(raw).replace("\n", ",").replace(";", ",")
        parts = normalized.split(",")
    keywords: list[str] = []
    seen: set[str] = set()
    for part in parts:
        keyword = part.strip()
        if not keyword or keyword in seen:
            continue
        seen.add(keyword)
        keywords.append(keyword)
    return keywords or list(DEFAULT_TOPIC_KEYWORDS)


def build_search_url(keyword: str) -> str:
    params = urlencode(
        {
            "where": "article",
            "query": keyword,
            "sm": "tab_opt",
            "nso": "so:r,p:all,a:all",
        },
        encoding="utf-8",
    )
    return f"{SEARCH_ROOT}?{params}"


def build_dom_extract_expression(keyword: str, *, limit: int = 10) -> str:
    keyword_json = __import__("json").dumps(keyword, ensure_ascii=False)
    limit = max(1, min(int(limit), 50))
    return f"""
(() => {{
  const keyword = {keyword_json};
  const limit = {limit};
  const seen = new Set();
  const items = [];
  const anchors = Array.from(document.querySelectorAll('a[href*="cafe.naver.com"], a[href*="section.cafe.naver.com"]'));
  function clean(text) {{
    return String(text || '').replace(/\\s+/g, ' ').trim();
  }}
  function cafeNameFrom(block, anchorText) {{
    const selectors = ['.name', '.sub_txt', '.source_box', '.user_info', '.total_sub'];
    for (const selector of selectors) {{
      const value = clean(block.querySelector(selector)?.innerText || '');
      if (value && value.length <= 80) return value;
    }}
    const lines = clean(block.innerText || '').split(' ').filter(Boolean);
    return lines.length > 1 ? lines.slice(0, 4).join(' ') : anchorText.slice(0, 80);
  }}
  for (const a of anchors) {{
    const url = a.href || '';
    const title = clean(a.innerText || a.title || '');
    if (!url || !title || title.length < 2) continue;
    if (seen.has(url)) continue;
    seen.add(url);
    const block = a.closest('li, .view_wrap, .total_wrap, .api_subject_bx, section, div') || a.parentElement || a;
    const snippet = clean(block.innerText || '').slice(0, 700);
    items.push({{
      keyword,
      rank: items.length + 1,
      title: title.slice(0, 180),
      url,
      cafe_name: cafeNameFrom(block, title),
      snippet,
      source: 'naver_search_article'
    }});
    if (items.length >= limit) break;
  }}
  return {{
    keyword,
    href: location.href,
    title: document.title,
    items
  }};
}})()
""".strip()


def build_report(rows: list[dict[str, Any]], *, keywords: list[str]) -> CafeTopicSearchReport:
    items: list[CafeTopicSearchItem] = []
    seen_urls: set[str] = set()
    for row in rows:
        for raw_item in row.get("items", []) if isinstance(row, dict) else []:
            if not isinstance(raw_item, dict):
                continue
            url = str(raw_item.get("url") or "").strip()
            title = str(raw_item.get("title") or "").strip()
            if not url or not title or url in seen_urls:
                continue
            seen_urls.add(url)
            items.append(
                CafeTopicSearchItem(
                    keyword=str(raw_item.get("keyword") or row.get("keyword") or ""),
                    rank=int(raw_item.get("rank") or 0),
                    title=title,
                    url=url,
                    cafe_name=str(raw_item.get("cafe_name") or "").strip(),
                    snippet=str(raw_item.get("snippet") or "").strip(),
                    source=str(raw_item.get("source") or "naver_search_article"),
                )
            )

    keyword_counts = {keyword: sum(1 for item in items if item.keyword == keyword) for keyword in keywords}
    cafe_counts: dict[str, int] = {}
    for item in items:
        key = item.cafe_name or item.url.split("/")[2]
        cafe_counts[key] = cafe_counts.get(key, 0) + 1
    top_cafes = [
        {"cafe_name": cafe, "count": count}
        for cafe, count in sorted(cafe_counts.items(), key=lambda pair: (-pair[1], pair[0]))[:20]
    ]
    return CafeTopicSearchReport(
        ok=True,
        keywords=keywords,
        total_items=len(items),
        items=items,
        keyword_counts=keyword_counts,
        top_cafes=top_cafes,
        messages=[
            "Collected Naver Cafe topic search results through existing CDP target only.",
            "UTF-8 query encoding is handled in Python before browser navigation.",
            "Read-only DOM extraction; no join, write, delete, move, submit, launch, or close action.",
        ],
    )


def collect_topic_search_from_target(
    target_id: str,
    *,
    port: int,
    keywords: str | list[str] | tuple[str, ...] | None = None,
    limit_per_keyword: int = 10,
    wait_s: float = 2.0,
) -> CafeTopicSearchReport:
    gate_check("scan_page", context="naver_cafe_topic_search")
    parsed_keywords = split_keywords(keywords)
    rows: list[dict[str, Any]] = []
    for keyword in parsed_keywords:
        cdp.navigate(target_id, build_search_url(keyword), port=port)
        time.sleep(max(0.0, wait_s))
        raw = list_collector.evaluate_async(
            target_id,
            build_dom_extract_expression(keyword, limit=limit_per_keyword),
            port=port,
            timeout=20.0,
        )
        if isinstance(raw, dict):
            rows.append(raw)
        else:
            rows.append({"keyword": keyword, "items": [], "error": "invalid_dom_extract_result"})
    return build_report(rows, keywords=parsed_keywords)

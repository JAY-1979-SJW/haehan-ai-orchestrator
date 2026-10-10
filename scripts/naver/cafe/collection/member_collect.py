"""Read-only collection for joined Naver Cafe pages.

This module is for cafes the user can already access. It collects the cafe home
surface, board links, and article candidates through an existing CDP target. It
does not join, write, comment, delete, move, submit, launch, or close browsers.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import quote

from scripts.common.gate import check as gate_check
from scripts.naver.cafe import list_collector
from scripts.naver.mail.read import cdp

DEFAULT_TERMS = [
    "AI",
    "자동화",
    "스마트",
    "스토어",
    "쿠팡",
    "CS",
    "고객",
    "상세페이지",
    "송장",
    "업로드",
    "상품",
    "등록",
    "마케팅",
    "광고",
    "택배",
    "물류",
    "구매대행",
    "도매",
    "위탁",
    "창업",
    "운영",
    "매출",
    "플랫폼",
]

DEFAULT_BOARD_HINTS = {
    "soho": [
        ("startup_ops", "QnA 창업ㆍ운영", "10094408", "75", "L"),
        ("smartstore", "QnA 스마트 스토어", "10094408", "633", "L"),
        ("coupang_ads", "QnA 쿠팡 셀러 광고", "10094408", "701", "L"),
        ("marketing_ads", "QnA 마케팅ㆍ광고", "10094408", "566", "L"),
        ("logistics", "QnA 물류ㆍ택배ㆍ박스", "10094408", "680", "L"),
        ("purchase_agent", "QnA 해외ㆍ구매대행등", "10094408", "525", "L"),
    ],
    "royaltyserver": [
        ("ai_jobs", "AI 작업자구해요", "22417348", "74", "L"),
        ("ai_tool_errors", "AI툴 오류 공유", "22417348", "62", "I"),
        ("ai_work_share", "AI 작업공유방", "22417348", "63", "I"),
        ("ai_news", "AI정보/뉴스", "22417348", "64", "L"),
        ("sns_marketing_ai", "SNS/마케팅 AI활용법", "22417348", "65", "L"),
        ("ai_image_video", "AI이미지/영상 제작법", "22417348", "66", "L"),
        ("ai_business", "AI업무활용법", "22417348", "67", "L"),
        ("ai_education", "AI 협력교육원", "22417348", "76", "L"),
    ],
}


@dataclass(frozen=True)
class CafeBoardHint:
    key: str
    label: str
    club_id: str
    menu_id: str
    board_type: str = "L"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class JoinedCafeCollectReport:
    ok: bool
    code: str = "ok"
    cafe_url: str = ""
    href: str = ""
    title: str = ""
    frame_href: str = ""
    frame_title: str = ""
    top_body_sample: str = ""
    frame_body_sample: str = ""
    boards: list[dict[str, Any]] = field(default_factory=list)
    articles: list[dict[str, Any]] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class JoinedCafeBoardsReport:
    ok: bool
    code: str = "ok"
    cafe_url: str = ""
    boards: list[dict[str, Any]] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_cafe_url(cafe_url: str) -> str:
    cafe_url = str(cafe_url or "").strip().strip("/")
    if cafe_url.startswith("https://cafe.naver.com/"):
        cafe_url = cafe_url.split("https://cafe.naver.com/", 1)[1].split("/", 1)[0]
    if not cafe_url:
        raise ValueError("cafe_url_required")
    return cafe_url


def board_hints_for(cafe_url: str) -> list[CafeBoardHint]:
    rows = DEFAULT_BOARD_HINTS.get(normalize_cafe_url(cafe_url), [])
    hints: list[CafeBoardHint] = []
    for row in rows:
        if len(row) == 3:
            key, label, menu_id = row
            hints.append(CafeBoardHint(key=key, label=label, club_id="", menu_id=menu_id))
        else:
            key, label, club_id, menu_id, board_type = row
            hints.append(CafeBoardHint(key=key, label=label, club_id=club_id, menu_id=menu_id, board_type=board_type))
    return hints


def _home_extract_expression() -> str:
    return r"""
JSON.stringify((function(){
  function clean(s){return String(s||'').replace(/\s+/g,' ').trim();}
  var frame = document.getElementById('cafe_main');
  var d = frame && frame.contentDocument ? frame.contentDocument : document;
  function collectLinks(doc, source){
    return Array.prototype.slice.call(doc.querySelectorAll('a')).map(function(a){
      return {source: source, text: clean(a.innerText || a.title || ''), href: String(a.href || a.getAttribute('href') || ''), title: String(a.title || '')};
    }).filter(function(x){return x.text || x.href;});
  }
  return {
    href: location.href,
    title: document.title,
    frameHref: d.location.href,
    frameTitle: d.title,
    topBody: clean(document.body && document.body.innerText || '').slice(0, 2500),
    frameBody: clean(d.body && d.body.innerText || '').slice(0, 7000),
    links: collectLinks(document, 'top').concat(collectLinks(d, 'frame')).slice(0, 1200)
  };
})())
""".strip()


def _board_extract_expression() -> str:
    return r"""
JSON.stringify((function(){
  function clean(s){return String(s||'').replace(/\s+/g,' ').trim();}
  var frame = document.getElementById('cafe_main');
  var d = frame && frame.contentDocument ? frame.contentDocument : document;
  var links = Array.prototype.slice.call(d.querySelectorAll('a')).map(function(a){
    var row = a.closest('tr,li,div');
    return {text: clean(a.innerText || a.title || ''), href: String(a.href || a.getAttribute('href') || ''), title: String(a.title || ''), rowText: clean(row && row.innerText || '').slice(0, 600)};
  }).filter(function(x){return x.text || x.href;});
  return {frameHref: d.location.href, frameTitle: d.title, body: clean(d.body && d.body.innerText || '').slice(0, 4000), links: links.slice(0, 700)};
})())
""".strip()


def _filtered_links(links: list[dict[str, Any]], *, terms: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    boards: list[dict[str, Any]] = []
    articles: list[dict[str, Any]] = []
    seen_boards: set[tuple[str, str]] = set()
    seen_articles: set[tuple[str, str]] = set()
    for link in links:
        blob = " ".join(str(link.get(k, "")) for k in ("text", "href", "title", "rowText"))
        if any(term in blob for term in terms):
            key = (str(link.get("text", "")), str(link.get("href", "")))
            if key not in seen_boards:
                seen_boards.add(key)
                boards.append({**link, "matched_terms": [term for term in terms if term in blob]})
        if "ArticleRead" in blob or "/soho/" in blob:
            key = (str(link.get("text", "")), str(link.get("href", "")))
            if key not in seen_articles:
                seen_articles.add(key)
                articles.append({**link, "matched_terms": [term for term in terms if term in blob]})
    return boards, articles


def collect_home_from_target(
    target_id: str,
    *,
    port: int,
    cafe_url: str,
    terms: list[str] | None = None,
    wait_s: float = 2.5,
) -> JoinedCafeCollectReport:
    gate_check("scan_page", context="naver_cafe_member_collect")
    cafe_url = normalize_cafe_url(cafe_url)
    cdp.navigate(target_id, f"https://cafe.naver.com/{cafe_url}", port=port)
    time.sleep(max(0.0, wait_s))
    raw = list_collector.evaluate_async(target_id, _home_extract_expression(), port=port, timeout=20.0)
    if isinstance(raw, str):
        raw = __import__("json").loads(raw)
    if not isinstance(raw, dict):
        return JoinedCafeCollectReport(ok=False, code="invalid_home_extract_result", cafe_url=cafe_url)
    boards, articles = _filtered_links(raw.get("links", []), terms=terms or DEFAULT_TERMS)
    return JoinedCafeCollectReport(
        ok=True,
        cafe_url=cafe_url,
        href=str(raw.get("href") or ""),
        title=str(raw.get("title") or ""),
        frame_href=str(raw.get("frameHref") or ""),
        frame_title=str(raw.get("frameTitle") or ""),
        top_body_sample=str(raw.get("topBody") or ""),
        frame_body_sample=str(raw.get("frameBody") or ""),
        boards=boards[:200],
        articles=articles[:200],
        messages=["Collected joined Naver Cafe home read-only through existing CDP target."],
    )


def collect_boards_from_target(
    target_id: str,
    *,
    port: int,
    cafe_url: str,
    hints: list[CafeBoardHint] | None = None,
    terms: list[str] | None = None,
    wait_s: float = 2.5,
) -> JoinedCafeBoardsReport:
    gate_check("scan_page", context="naver_cafe_member_boards_collect")
    cafe_url = normalize_cafe_url(cafe_url)
    selected = hints if hints is not None else board_hints_for(cafe_url)
    reports: list[dict[str, Any]] = []
    for hint in selected:
        if not hint.club_id:
            raise ValueError(f"club_id_required_for_board_hint:{hint.key}")
        iframe_url = quote(
            f"/ArticleList.nhn?search.clubid={hint.club_id}&search.menuid={hint.menu_id}&search.boardtype={hint.board_type}",
            safe="",
        )
        cdp.navigate(target_id, f"https://cafe.naver.com/{cafe_url}?iframe_url={iframe_url}", port=port)
        time.sleep(max(0.0, wait_s))
        raw = list_collector.evaluate_async(target_id, _board_extract_expression(), port=port, timeout=20.0)
        if isinstance(raw, str):
            raw = __import__("json").loads(raw)
        raw = raw if isinstance(raw, dict) else {}
        _, articles = _filtered_links(raw.get("links", []), terms=terms or DEFAULT_TERMS)
        reports.append(
            {
                "key": hint.key,
                "label": hint.label,
                "club_id": hint.club_id,
                "menu_id": hint.menu_id,
                "board_type": hint.board_type,
                "frame_href": raw.get("frameHref", ""),
                "body_sample": raw.get("body", ""),
                "articles": articles[:80],
                "article_count": len(articles),
            }
        )
    return JoinedCafeBoardsReport(
        ok=True,
        cafe_url=cafe_url,
        boards=reports,
        messages=["Collected joined Naver Cafe board article lists read-only through existing CDP target."],
    )

"""아이보스(i-boss.co.kr) 게시글 수집 — 온라인마케팅 실무자 커뮤니티.

목적: 건설 물량산출/공무서류 프로그램을 니치 전문가 커뮤니티(건설공무 카페 등)에
영업하는 데 참고할 마케팅 실무 노하우(DB 마케팅, 카페 마케팅, 콘텐츠 마케팅 전략)
수집. 아이보스 자체는 영업 대상이 아니라 "마케팅 방법을 배우는" 참고 자료 소스.

로그인 불필요(본문까지 비회원 열람 가능, 2026-08-16 확인). 단, 일반 urllib 요청은
403(봇 차단)이라 반드시 CDP 브라우저(Playwright connect_over_cdp)로 접근해야 한다.
scripts/community/universal_extractor.py 의 휴리스틱은 이 사이트의 GNB/인기글
위젯을 게시글 목록으로 오인해 신규 작성했다(a.mb_subject 셀렉터가 안정적).
"""

from __future__ import annotations

import re
import time
from typing import Any

BASE_URL = "https://www.i-boss.co.kr"

BOARDS = {
    "정보공유": "/ab-6166",
    "질문답변": "/ab-2109",
}

_LIST_JS = r"""
() => {
  // 두 스킨을 모두 지원한다: 정보공유(tr 테이블) / 질문답변(div.article 카드).
  const rows = [];
  const anchors = Array.from(document.querySelectorAll('a[title][href]'))
    .filter(a => /^\/?ab-\d+-\d+/.test(a.getAttribute('href') || ''));
  const seen = new Set();
  for (const a of anchors) {
    const href = a.getAttribute('href') || '';
    if (seen.has(href)) continue;
    seen.add(href);
    const container = a.closest('tr') || a.closest('div.article') || a.closest('li');
    const title = a.getAttribute('title') || '';
    if (!container) { rows.push({ href, title, category: '', author: '', date: '', views: '', votes: '' }); continue; }
    const category = (container.querySelector('.tblabel, .category')?.textContent || '').trim();
    const author = (container.querySelector('.mb_writer span, .user span[id^="ABP-btn"]')?.textContent || '').trim();
    const dateEl = container.querySelector('.DateTime, .user label.bstip');
    const date = (dateEl?.getAttribute('data-tip') || dateEl?.textContent || '').trim();
    const views = (container.querySelector('.ViewCount')?.textContent || '').trim();
    const votes = (container.querySelector('.voteCount, .cmt i')?.textContent || '').trim();
    rows.push({ href, title, category, author, date, views, votes });
  }
  return rows;
}
"""


def list_board(page: Any, board_url: str, *, wait_seconds: float = 4.0) -> list[dict[str, Any]]:
    """게시판 URL(BOARDS 값 또는 절대 URL) → 게시글 목록(제목/작성자/날짜/조회수/추천수)."""
    url = board_url if board_url.startswith("http") else BASE_URL + board_url
    page.goto(url, timeout=25000, wait_until="domcontentloaded")
    time.sleep(wait_seconds)
    rows = page.evaluate(_LIST_JS)
    out = []
    for r in rows:
        href = r.get("href", "")
        full_url = href if href.startswith("http") else f"{BASE_URL}/{href.lstrip('/')}"
        out.append({**r, "url": full_url})
    return out


# 두 스킨 모두 대응: 정보공유는 "작성자→날짜" 순서 + "좋아요/댓글" 라벨,
# 질문답변은 "날짜→작성자" 순서 + "답변"(+채택률) 라벨을 쓴다.
_META_RE_INFO = re.compile(
    r"(?P<author>\S+)\n\n(?P<date>\d{4}[.\-]\d{2}[.\-]\d{2})[^\n]*\n\n조회수\s*(?P<views>[\d,]+)\n\n"
    r"좋아요\s*(?P<likes>[\d,]+)\n\n댓글\s*(?P<comments>[\d,]+)"
    r"\n(?P<body>[\s\S]+)"
)
_META_RE_QNA = re.compile(
    r"(?P<date>\d{4}[.\-]\d{2}[.\-]\d{2})[^\n]*\n\n(?P<author>\S+)\n\n조회수\s*(?P<views>[\d,]+)\n\n"
    r"답변\s*(?P<comments>[\d,]+)(?:\n\n채택률[\s\S]{0,20}%)?"
    r"\n(?P<body>[\s\S]+)"
)
_BODY_STOP_MARKERS = ["아 맞다! 좋아요", "좋아요\n좋아요", "댓글 새로고침", "AI가 비슷한 글을 추천해요"]


def _trim_body(body: str) -> str:
    cut = len(body)
    for marker in _BODY_STOP_MARKERS:
        idx = body.find(marker)
        if idx != -1:
            cut = min(cut, idx)
    return body[:cut].strip()[:3000]


_COMMENT_ITEM_JS = r"""
() => {
  const items = Array.from(document.querySelectorAll('#ajax-cmt-list [class*="comment-item"], #ajax-cmt-list li'));
  return items.map(el => (el.innerText || '').trim()).filter(Boolean).slice(0, 100);
}
"""


def fetch_post_detail(page: Any, url: str, *, wait_seconds: float = 3.0) -> dict[str, Any]:
    """게시글 상세 방문 → 작성자/날짜/조회수/좋아요/댓글수/본문/댓글원문(최선) 추출."""
    page.goto(url, timeout=25000, wait_until="domcontentloaded")
    time.sleep(wait_seconds)

    # 가장 텍스트 밀도가 높은 컨테이너(메타데이터+본문 포함)를 휴리스틱으로 탐색.
    # 이 사이트는 안정적인 본문 클래스명이 없어(그누보드 계열 커스텀 스킨), 구조
    # 대신 "텍스트 양이 가장 많은 자식 수 적은 블록"으로 콘텐츠 영역을 찾는다.
    block_text = page.evaluate(
        r"""
        () => {
            const all = Array.from(document.querySelectorAll('div,section,article'));
            let best = '', bestLen = 0;
            for (const el of all) {
                const len = (el.innerText || '').length;
                if (len > bestLen && len < 20000 && el.children.length < 40) {
                    bestLen = len; best = el.innerText || '';
                }
            }
            return best;
        }
        """
    )

    result: dict[str, Any] = {
        "url": url,
        "author": "",
        "date": "",
        "view_count": "",
        "like_count": "",
        "comment_count": "0",
        "body": "",
        "comments_raw": [],
    }
    match = _META_RE_INFO.search(block_text or "") or _META_RE_QNA.search(block_text or "")
    if match:
        groups = match.groupdict()
        result.update(
            {
                "author": groups.get("author", "").strip(),
                "date": groups.get("date", "").strip(),
                "view_count": groups.get("views", "").replace(",", ""),
                "like_count": (groups.get("likes") or "").replace(",", ""),
                "comment_count": (groups.get("comments") or "0").replace(",", ""),
                "body": _trim_body(groups.get("body", "")),
            }
        )

    try:
        result["comments_raw"] = page.evaluate(_COMMENT_ITEM_JS)
    except Exception:  # noqa: BLE001 - 페이지 댓글 수집(page.evaluate) 실패 시 빈 목록으로 폴백 - 읽기전용 스크래핑, 실패 시 해당 항목만 누락될 뿐 쓰기·위험 조작 없음
        result["comments_raw"] = []

    return result

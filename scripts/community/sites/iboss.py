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
  const rows = [];
  const anchors = Array.from(document.querySelectorAll('a.mb_subject[title]'));
  for (const a of anchors) {
    const tr = a.closest('tr');
    if (!tr) continue;
    const href = a.getAttribute('href') || '';
    const title = a.getAttribute('title') || '';
    const category = (tr.querySelector('.tblabel')?.textContent || '').trim();
    const author = (tr.querySelector('.mb_writer span')?.textContent || '').trim();
    const dateEl = tr.querySelector('.DateTime');
    const date = (dateEl?.getAttribute('data-tip') || dateEl?.textContent || '').trim();
    const views = (tr.querySelector('.ViewCount')?.textContent || '').trim();
    const votes = (tr.querySelector('.voteCount')?.textContent || '').trim();
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


_META_RE = re.compile(
    r"(?P<author>\S+)\n\n(?P<date>\d{4}-\d{2}-\d{2})\n\n조회수\s*(?P<views>[\d,]+)\n\n좋아요\s*(?P<likes>[\d,]+)\n\n댓글\s*(?P<comments>[\d,]+)\n\n(?P<body>[\s\S]+)"
)

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
    match = _META_RE.search(block_text or "")
    if match:
        result.update(
            {
                "author": match.group("author").strip(),
                "date": match.group("date").strip(),
                "view_count": match.group("views").replace(",", ""),
                "like_count": match.group("likes").replace(",", ""),
                "comment_count": match.group("comments").replace(",", ""),
                "body": match.group("body").strip()[:3000],
            }
        )

    try:
        result["comments_raw"] = page.evaluate(_COMMENT_ITEM_JS)
    except Exception:
        result["comments_raw"] = []

    return result

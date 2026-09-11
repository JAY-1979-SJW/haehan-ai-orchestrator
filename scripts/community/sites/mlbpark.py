"""MLB파크(mlbpark.donga.com) 게시판 게시글 수집.

2026-09-12 두 번 헤맨 끝에 확정된 사실들 (재발 방지 기록):

1. 실제 게시판은 3개뿐이다: mlbtown(해외야구), kbotown(국내야구), bullpen(불펜 —
   야구 외 잡담/사회이슈 전반). "mbs2/mbs4/mbs5" 같은 코드는 존재하지 않는
   추측이었다 — 홈페이지 네비게이션에서 실제 `m=list` 링크로 직접 확인할 것.
2. 페이지네이션 파라미터는 `page=`가 아니라 `p=`(게시글 30건 단위 offset,
   즉 2페이지=p=31, 3페이지=p=61 ...)다. `page=`는 조용히 무시되고 항상
   1페이지만 반환된다.
3. 어느 게시판에 들어가든 화면 상단에 "버닝(인기글)" 위젯이 mlbtown/kbotown/
   bullpen 글을 섞어서 따로 얹힌다(getBurningWidget.php로 별도 로드). 그래서
   `a[href*="m=view"]`만으로 앵커를 모으면 지금 보고 있는 게시판이 아니라
   이 위젯 내용을 주워버린다 — 반드시 `href`에 `b={그 게시판 코드}`가 포함된
   것만 걸러야 한다.
4. 실제 게시글 행 텍스트 형식(예: 불펜): "{글번호}\\n{카테고리}\\n{제목}
   [{댓글수}]|{작성자}|{시간}|{조회수}" — 카테고리 태그(일상/과학/유머/야구 등)가
   같이 붙어 있어 이것도 분류에 바로 쓸 수 있다.

로그인 불필요, GPT 없이 이 전용 셀렉터만으로 충분.
"""

from __future__ import annotations

import re
from typing import Any

BASE_URL = "https://mlbpark.donga.com"

BOARDS = {
    "불펜": "bullpen",
    "해외야구": "mlbtown",
    "국내야구": "kbotown",
}


def board_url(board: str, offset: int = 1) -> str:
    code = BOARDS.get(board, board)
    return f"{BASE_URL}/mp/b.php?p={offset}&m=list&b={code}&query=&select=&user="


_ROW_JS = r"""
(boardCode) => {
  const anchors = Array.from(document.querySelectorAll(`a[href*="m=view"][href*="b=${boardCode}"]`))
    .filter(a => !a.href.includes('pos=reply'));
  const seen = new Set();
  const out = [];
  for (const a of anchors) {
    if (seen.has(a.href)) continue;
    seen.add(a.href);
    const row = a.closest('tr') || a.closest('li');
    const rowText = (row ? row.innerText : '').replace(/\t/g, '|').trim();
    out.push({ title: a.innerText.trim(), url: a.href, rowText });
  }
  return out;
}
"""

_ROW_RE = re.compile(
    r"^\d+\|?\s*\n?(?P<category>\S+)\n(?P<title>.+?)(?:\s*\[\d+\])?\|(?P<author>[^|]+)\|(?P<time>[^|]+)\|(?P<views>\d+)",
    re.S,
)


def _parse_row(rowText: str) -> dict[str, str]:
    m = _ROW_RE.match(rowText)
    if not m:
        return {"category": "", "author": "", "time": "", "views": ""}
    return {
        "category": m.group("category").strip(),
        "author": m.group("author").strip(),
        "time": m.group("time").strip(),
        "views": m.group("views").strip(),
    }


def list_board(page: Any, board: str, *, offset: int = 1) -> list[dict[str, Any]]:
    """게시판(별칭 또는 코드) → 게시글 목록(제목/링크/카테고리/작성자/시간/조회수)."""
    code = BOARDS.get(board, board)
    url = board_url(board, offset)
    if not url.startswith(BASE_URL):
        raise ValueError(f"mlbpark.donga.com URL만 허용됩니다: {url!r}")

    page.goto(url, timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    rows = page.evaluate(_ROW_JS, code)
    if not isinstance(rows, list):
        return []

    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        title = (r.get("title") or "").strip()
        if not title:
            continue
        meta = _parse_row(r.get("rowText", ""))
        out.append({"title": title, "url": r.get("url", ""), **meta})
    return out


def list_board_range(page: Any, board: str, *, days: int = 7, max_pages: int = 300) -> dict[str, Any]:
    """게시판을 p= 오프셋으로 순회해 최근 N일치 게시글을 모은다.

    '시간' 필드가 절대시각(HH:MM:SS, 오늘)이거나 상대(N일전)일 수 있어
    엄밀한 날짜 계산은 하지 않는다 — 매 페이지가 이전 페이지와 겹치는
    글이 없는 동안은 계속 수집하고, 새 글이 전혀 없는 페이지(=한 바퀴
    돈 것)를 만나면 멈춘다. 결과의 pages_scanned/count를 같이 반환하니
    호출부가 "이게 대략 며칠치인지"는 게시글의 time 필드로 직접 판단한다.
    """
    code = BOARDS.get(board, board)
    all_posts: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    stopped_reason = "max_pages_reached"
    p = 0

    for p in range(1, max_pages + 1):
        offset = (p - 1) * 30 + 1
        posts = list_board(page, board, offset=offset)
        if not posts:
            stopped_reason = "no_more_posts"
            break
        new_posts = [pt for pt in posts if pt.get("url") not in seen_urls]
        if not new_posts:
            stopped_reason = "no_new_posts"
            break
        for pt in new_posts:
            seen_urls.add(pt.get("url"))
        all_posts.extend(new_posts)

    return {
        "ok": True,
        "board": board,
        "board_code": code,
        "days": days,
        "pages_scanned": p,
        "stopped_reason": stopped_reason,
        "count": len(all_posts),
        "posts": all_posts,
    }

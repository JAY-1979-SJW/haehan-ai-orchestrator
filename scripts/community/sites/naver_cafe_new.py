"""네이버 카페 신규 UI(cafe.naver.com/f-e/cafes/{clubid}/menus/{menuid}) 게시글 수집.

2026-09-12 확인: 새 카페 UI는 React SPA라 게시글 링크가 `a[href*="/articles/"]`로
존재하긴 하지만, universal_extractor.py의 범용 휴리스틱(DOM 구조 시그니처로
최대 그룹 선택)이 사이드 메뉴 링크를 게시글 목록으로 오인해서 실패한다.
그래서 이 사이트 전용 추출기를 따로 둔다(아이보스와 같은 패턴).

렌더링이 느려서(React 하이드레이션) domcontentloaded 직후 3초 대기로는
부족하다 — 6초 이상 대기 필요(2026-09-12 실측, "아프니까 사장이다" 카페).
"""

from __future__ import annotations

from typing import Any

_LIST_JS = r"""
() => {
  const anchors = Array.from(document.querySelectorAll('a[href*="/articles/"]'))
    .filter(a => !a.href.includes('commentFocus'));
  const seen = new Set();
  const rows = [];
  for (const a of anchors) {
    const href = a.getAttribute('href') || '';
    if (seen.has(href)) continue;
    seen.add(href);
    const row = a.closest('li') || a.closest('tr') || (a.parentElement && a.parentElement.parentElement);
    const rowText = (row ? row.innerText : '').replace(/\s+/g, ' ').trim();
    const dateM = rowText.match(/\d{4}\.\d{1,2}\.\d{1,2}\.|\d{1,2}:\d{2}/);
    const viewM = rowText.match(/(\d[\d,]*(?:\.\d+)?만?)\s*$/);
    const cmtM = rowText.match(/댓글수\s*\[(\d[\d,]*)\]/);
    rows.push({
      title: (a.innerText || '').trim(),
      url: a.href,
      date: dateM ? dateM[0] : '',
      views: viewM ? viewM[1] : '',
      comments: cmtM ? cmtM[1] : '',
    });
  }
  return rows;
}
"""


def list_board(page: Any, url: str, *, wait_seconds: float = 6.0) -> list[dict[str, Any]]:
    """게시판 URL(cafe.naver.com/f-e/cafes/{clubid}/menus/{menuid}?viewType=L) → 게시글 목록.

    이 어댑터는 네이버 카페 전용이라 다른 도메인으로 임의 이동시키지 않는다
    (SSRF 방지 — url이 cafe.naver.com이 아니면 거부).
    """
    if not url.startswith("https://cafe.naver.com/"):
        raise ValueError(f"cafe.naver.com URL만 허용됩니다: {url!r}")

    page.goto(url, timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(int(wait_seconds * 1000))
    rows = page.evaluate(_LIST_JS)
    if not isinstance(rows, list):
        return []
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        title = (r.get("title") or "").strip()
        if not title or title in {"댓글수"}:
            continue
        out.append(r)
    return out


def board_url(clubid: int, menuid: int = 0) -> str:
    return f"https://cafe.naver.com/f-e/cafes/{clubid}/menus/{menuid}?viewType=L"

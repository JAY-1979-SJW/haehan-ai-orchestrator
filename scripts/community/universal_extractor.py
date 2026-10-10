"""범용 게시글 추출기 — URL → 게시글 목록(제목·링크·날짜·조회수).

전략:
  휴리스틱: 같은 구조 위치에 반복되는 링크 묶음 = 게시글 목록으로 감지(무료·빠름).
  휴리스틱이 안 통하는 사이트는 scripts/community/sites/ 에 전용 어댑터를
  추가한다(GPT 폴백은 2026-09-12 유료 API 사용 중단으로 제거됨).

사용:
    from scripts.browser.cdp.connection import get_page
    from scripts.community.universal_extractor import extract_posts
    result = extract_posts(get_page(), "https://example.com/board")
"""

from __future__ import annotations

import time
from typing import Any

# 휴리스틱: 구조 시그니처가 같은 앵커 묶음 중 최대 그룹을 게시글 목록으로 본다.
_HEURISTIC_JS = r"""() => {
  const anchors = Array.from(document.querySelectorAll('a[href]'))
    .map(a => ({ el: a, href: a.href || '', text: (a.innerText || '').trim() }))
    .filter(x => x.href && x.text.length >= 4 && x.text.length <= 180
                 && !/^(javascript:|#|mailto:)/.test(x.href));
  function sig(a) {
    let p = a.el, parts = [];
    for (let i = 0; i < 3 && p; i++) {
      const cls = (typeof p.className === 'string' ? p.className.split(/\s+/)[0] : '') || '';
      parts.push(p.tagName + (cls ? '.' + cls : ''));
      p = p.parentElement;
    }
    return parts.join('>');
  }
  const groups = {};
  anchors.forEach(a => { const s = sig(a); (groups[s] = groups[s] || []).push(a); });

  const DATE_RE = /(\d{4}[.\-\/]\d{1,2}[.\-\/]\d{1,2}|\d{1,2}[.\-\/]\d{1,2}|\d{1,2}:\d{2}|\d+\s*(분|시간|일|개월)\s*전)/;
  const VIEW_RE = /조회\s*[:\s]*([\d,]+)|\bview[s]?\s*[:\s]*([\d,]+)/i;
  const CMT_RE = /(댓글|코멘트|comment[s]?)\s*[:\s]*([\d,]+)|\[(\d{1,4})\]/i;

  function rowsOf(group) {
    return group.slice(0, 120).map(a => {
      const cont = a.el.closest('li,tr,article,[class*="item"],[class*="list"]') || a.el.parentElement;
      const ctext = (cont ? cont.innerText : '').replace(/\s+/g, ' ').trim();
      const dateM = ctext.match(DATE_RE), viewM = ctext.match(VIEW_RE), cmtM = ctext.match(CMT_RE);
      return {
        title: a.text, url: a.href,
        date: dateM ? dateM[0] : '',
        views: viewM ? (viewM[1] || viewM[2] || '') : '',
        comments: cmtM ? (cmtM[2] || cmtM[3] || '') : '',
      };
    });
  }

  // 게시글다움 점수: 크기 + 날짜/조회 신호 비중. (사이드바 메뉴처럼 신호 없는 큰 묶음 배제)
  let best = null, bestScore = -1, bestSignal = 0;
  for (const k in groups) {
    const g = groups[k];
    if (g.length < 5) continue;
    const rows = rowsOf(g);
    const withDate = rows.filter(r => r.date).length / rows.length;
    const withView = rows.filter(r => r.views).length / rows.length;
    const signal = withDate * 2 + withView;
    const score = g.length * (1 + signal * 3);  // 신호 있는 묶음을 강하게 우대
    if (score > bestScore) { bestScore = score; best = rows; bestSignal = signal; }
  }
  if (!best) return { posts: [], signal: 0 };
  return { posts: best, signal: bestSignal };
}"""


def _dedup(posts: list[dict]) -> list[dict]:
    seen, out = set(), []
    for p in posts:
        key = (p.get("title", "").strip(), p.get("url", "").strip())
        if not key[0] or key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def extract_posts(page, url: str, max_posts: int = 50, use_gpt: bool = False) -> dict[str, Any]:
    """URL의 게시글 목록을 추출.

    2026-09-12: GPT 폴백을 제거했다(유료 API 사용 중단 지시). 휴리스틱이
    빈약한 사이트는 `scripts/community/sites/`에 전용 어댑터를 만들어
    대응한다(예: iboss.py). `use_gpt` 인자는 하위호환용으로 남겨뒀지만
    더 이상 아무 효과가 없다.

    Returns:
        {ok, url, method('heuristic'|'none'), count, posts:[{title,url,date,views,comments}]}
    """
    if not url or not url.startswith("http"):
        return {"ok": False, "error": "유효한 URL이 아닙니다", "posts": [], "count": 0}

    page.goto(url, timeout=30000, wait_until="domcontentloaded")
    time.sleep(3)  # 동적 렌더 대기

    method = "heuristic"
    try:
        h = page.evaluate(_HEURISTIC_JS)
    except Exception:  # noqa: BLE001 - 휴리스틱 페이지 추출(page.evaluate) 실패 시 빈 결과 구조로 폴백 - 읽기전용 스크래핑, 실패해도 빈 게시물 목록만 나올 뿐 쓰기·위험 조작 없음
        h = {"posts": [], "signal": 0}
    posts = _dedup(h.get("posts", []) or [])

    if not posts:
        return {
            "ok": False,
            "url": url,
            "method": "none",
            "count": 0,
            "posts": [],
            "error": "게시글을 추출하지 못했습니다(로그인벽·동적로딩·캡차·전용 어댑터 필요일 수 있음)",
        }

    posts = posts[:max_posts]
    return {"ok": True, "url": url, "method": method, "count": len(posts), "posts": posts}

"""범용 게시글 추출기 — URL → 게시글 목록(제목·링크·날짜·조회수).

전략:
  1) 휴리스틱: 같은 구조 위치에 반복되는 링크 묶음 = 게시글 목록으로 감지(무료·빠름).
  2) GPT 폴백: 휴리스틱 결과가 빈약하면 렌더된 페이지 텍스트를 GPT에 주고 구조화 추출.
     → 사이트별 셀렉터 불필요. URL만 주면 어떤 사이트든 시도.

사용:
    from scripts.web_connector import get_page
    from scripts.community.universal_extractor import extract_posts
    result = extract_posts(get_page(), "https://example.com/board")
"""

from __future__ import annotations

import json
import re
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

_GPT_MAX_CHARS = 11000  # 페이지 텍스트 트림 상한(토큰 비용 제어)
_MIN_HEURISTIC_POSTS = 8  # 이 미만이면 GPT 폴백


def _dedup(posts: list[dict]) -> list[dict]:
    seen, out = set(), []
    for p in posts:
        key = (p.get("title", "").strip(), p.get("url", "").strip())
        if not key[0] or key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _gpt_extract(page_text: str, source_url: str) -> list[dict]:
    """렌더된 페이지 텍스트 → GPT 구조화 추출."""
    from ai_orchestrator.openai_proxy_caller import call_openai_chat

    text = page_text[:_GPT_MAX_CHARS]
    prompt = (
        "다음은 커뮤니티/포럼 게시판 페이지의 텍스트입니다. 게시글 목록만 추출하세요.\n"
        "메뉴·광고·네비게이션·로그인·푸터는 제외. 실제 게시글 행만.\n"
        "JSON 배열로만 출력(설명 금지). 각 항목 키: title, date, views, comments.\n"
        "값이 없으면 빈 문자열. 최대 60개.\n\n"
        f"[출처: {source_url}]\n{text}"
    )
    res = call_openai_chat(message=prompt, max_tokens=3000)
    if not res.ok:
        return []
    raw = res.text.strip()
    m = re.search(r"\[.*\]", raw, re.S)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
    except Exception:
        return []
    out = []
    for it in arr if isinstance(arr, list) else []:
        if isinstance(it, dict) and (it.get("title") or "").strip():
            out.append(
                {
                    "title": str(it.get("title", "")).strip(),
                    "url": str(it.get("url", "")).strip(),
                    "date": str(it.get("date", "")).strip(),
                    "views": str(it.get("views", "")).strip(),
                    "comments": str(it.get("comments", "")).strip(),
                }
            )
    return out


def extract_posts(page, url: str, max_posts: int = 50, use_gpt: bool = True) -> dict[str, Any]:
    """URL의 게시글 목록을 추출.

    Returns:
        {ok, url, method('heuristic'|'gpt'|'none'), count, posts:[{title,url,date,views,comments}]}
    """
    if not url or not url.startswith("http"):
        return {"ok": False, "error": "유효한 URL이 아닙니다", "posts": [], "count": 0}

    page.goto(url, timeout=30000, wait_until="domcontentloaded")
    time.sleep(3)  # 동적 렌더 대기

    method = "heuristic"
    try:
        h = page.evaluate(_HEURISTIC_JS)
    except Exception:
        h = {"posts": [], "signal": 0}
    posts = _dedup(h.get("posts", []) or [])
    signal = h.get("signal", 0) or 0

    # 휴리스틱이 빈약하거나(개수 부족) 게시글 신호(날짜/조회)가 약하면 GPT 폴백.
    # signal<0.3 = 날짜/조회가 거의 없음 → 사이드바 메뉴 등 오인 가능성.
    if use_gpt and (len(posts) < _MIN_HEURISTIC_POSTS or signal < 0.3):
        try:
            page_text = page.evaluate("() => document.body.innerText || ''")
        except Exception:
            page_text = ""
        gpt_posts = _dedup(_gpt_extract(page_text, url)) if page_text else []
        # GPT 결과가 날짜를 더 많이 담고 있거나(품질↑) 더 많으면 채택
        gpt_dated = sum(1 for p in gpt_posts if p.get("date"))
        heur_dated = sum(1 for p in posts if p.get("date"))
        if gpt_posts and (gpt_dated > heur_dated or len(gpt_posts) > len(posts)):
            posts, method = gpt_posts, "gpt"

    if not posts:
        return {
            "ok": False,
            "url": url,
            "method": "none",
            "count": 0,
            "posts": [],
            "error": "게시글을 추출하지 못했습니다(로그인벽·동적로딩·캡차일 수 있음)",
        }

    posts = posts[:max_posts]
    return {"ok": True, "url": url, "method": method, "count": len(posts), "posts": posts}

"""경쟁 글 자동 조사 — 같은 주제로 이미 상위 노출된 네이버 블로그 글 분석 (L5, raw CDP).

## 왜 필요한가
웹 검색으로 "블로그 잘 쓰는 법"을 조사하는 것보다, **우리가 쓰려는 것과
정확히 같은 주제로 실제 1위를 하고 있는 글을 열어보는 게 훨씬 정확하다**
(2026-08-23 실측). 그날 수동으로 해보니 우리 기준이 통째로 틀렸다는 게
드러났다 — 우리 초안 1,805자/태그 8개 vs 1위 글 5,409자/태그 30개.

이 모듈은 그 수동 조사를 자동화한다. 결과는 `gpt_writer.py`의 프롬프트에
주입돼 "경쟁 글은 이 정도로 쓴다"를 GPT에게 알려준다.

## 검증된 셀렉터 (2026-08-23)
- 블로그 검색: `search.naver.com/search.naver?ssc=tab.blog.all&query=...`
- 결과 링크: `a[href*="blog.naver.com/"]` 중 `/{blogId}/{logNo}` 패턴
  ⚠️ 검색결과 상단에 블로그 홈 링크(`/{blogId}` 만 있는 것)가 먼저 나오므로
  **logNo까지 있는 것만** 걸러야 한다.
- 본문: iframe 안 `.se-main-container`(신 에디터) 또는 `#postViewArea`(구 에디터)
"""

from __future__ import annotations

import json
import time
from urllib.parse import quote

from scripts.browser.cdp.cdp_helper import CDP
from scripts.common.logger import get_logger

_log = get_logger(__name__)

SEARCH_URL = "https://search.naver.com/search.naver?ssc=tab.blog.all&query={q}"

_SEARCH_RESULT_JS = """(function(){
  var seen = {}, out = [];
  Array.from(document.querySelectorAll('a')).forEach(function(a){
    var h = a.href || '';
    var m = h.match(/blog\\.naver\\.com\\/([A-Za-z0-9_-]+)\\/(\\d{6,})/);
    if (!m) return;
    var key = m[1] + '/' + m[2];
    if (seen[key]) return;
    seen[key] = 1;
    out.push({blogId: m[1], logNo: m[2], url: 'https://blog.naver.com/' + key});
  });
  return JSON.stringify(out);
})()"""

# 경쟁 글 1편 분석 — 본문 길이·태그 수·소제목 구조를 뽑는다.
_ANALYZE_JS = """(function(){
  function pick(doc){
    if (!doc) return null;
    var main = doc.querySelector('.se-main-container') || doc.querySelector('#postViewArea');
    if (!main) return null;
    var titleEl = doc.querySelector('.se-title-text, .htitle, .pcol1 .title');
    var body = (main.innerText || '').trim();
    var tags = Array.from(doc.querySelectorAll('a'))
      .map(function(a){ return (a.innerText || '').trim(); })
      .filter(function(t){ return t.indexOf('#') === 0 && t.length > 1; });
    var uniqTags = [];
    tags.forEach(function(t){ if (uniqTags.indexOf(t) === -1) uniqTags.push(t); });
    // 소제목 후보: 짧고 굵은 줄(30자 이하)을 구조 힌트로 수집
    var heads = body.split('\\n')
      .map(function(s){ return s.trim(); })
      .filter(function(s){ return s.length > 1 && s.length <= 30; })
      .slice(0, 40);
    return JSON.stringify({
      title: titleEl ? titleEl.innerText.trim() : '',
      char_count: body.length,
      tag_count: uniqTags.length,
      tags: uniqTags.slice(0, 30),
      line_hints: heads
    });
  }
  var r = pick(document);
  if (r) return r;
  var frames = document.querySelectorAll('iframe');
  for (var i = 0; i < frames.length; i++) {
    try {
      var d = frames[i].contentDocument || frames[i].contentWindow.document;
      var rr = pick(d);
      if (rr) return rr;
    } catch (e) {}
  }
  return '';
})()"""


def search_top_posts(cdp: CDP, query: str, top_n: int = 3) -> list[dict]:
    """네이버 블로그 검색 상위 N개 글의 URL을 반환."""
    cdp.navigate(SEARCH_URL.format(q=quote(query)), wait=3)
    time.sleep(1.5)
    raw = cdp.js(_SEARCH_RESULT_JS)
    try:
        items = json.loads(raw) if raw else []
    except Exception:  # noqa: BLE001 - JSON 캐시 파싱 실패시 빈 목록/None으로 안전 폴백 — 읽기전용 캐시 조회
        items = []
    return items[:top_n]


def analyze_post(cdp: CDP, url: str) -> dict | None:
    """경쟁 글 1편을 열어 분량·태그·구조를 추출."""
    cdp.navigate(url, wait=3)
    time.sleep(1.5)
    raw = cdp.js(_ANALYZE_JS)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:  # noqa: BLE001 - JSON 캐시 파싱 실패시 빈 목록/None으로 안전 폴백 — 읽기전용 캐시 조회
        return None
    data["url"] = url
    return data


def research_competitors(cdp: CDP, query: str, top_n: int = 3) -> dict:
    """같은 주제 상위 글 N편을 분석해 요약 통계를 낸다.

    반환: {"query", "posts": [...], "avg_chars", "avg_tags", "max_chars", "max_tags"}
    """
    found = search_top_posts(cdp, query, top_n=top_n)
    posts = []
    for it in found:
        a = analyze_post(cdp, it["url"])
        if a and a.get("char_count", 0) > 300:
            posts.append(a)
            _log.info(
                "[competitor] %s — %d자, 태그 %d개",
                a.get("title", "")[:28],
                a["char_count"],
                a["tag_count"],
            )
    if not posts:
        return {"query": query, "posts": [], "avg_chars": 0, "avg_tags": 0, "max_chars": 0, "max_tags": 0}
    n = len(posts)
    return {
        "query": query,
        "posts": posts,
        "avg_chars": sum(p["char_count"] for p in posts) // n,
        "avg_tags": sum(p["tag_count"] for p in posts) // n,
        "max_chars": max(p["char_count"] for p in posts),
        "max_tags": max(p["tag_count"] for p in posts),
    }


def summarize_for_prompt(research: dict) -> str:
    """경쟁 글 분석 결과를 GPT 프롬프트에 넣을 문단으로 정리."""
    posts = research.get("posts") or []
    if not posts:
        return ""
    lines = [
        "## 같은 주제로 이미 상위 노출된 경쟁 글 (실측)",
        f"- 평균 {research['avg_chars']:,}자 / 태그 평균 {research['avg_tags']}개"
        f" (최대 {research['max_chars']:,}자 / 태그 {research['max_tags']}개)",
        "- 경쟁 글 제목:",
    ]
    for p in posts:
        lines.append(f"  · {p.get('title', '')[:60]} ({p['char_count']:,}자, 태그 {p['tag_count']}개)")
    lines.append(
        "→ **이 글들보다 더 구체적이고 더 충실해야 상위 노출을 노릴 수 있습니다.** "
        "위 분량 이상으로, 검색자가 이 글 하나로 문제를 끝낼 수 있게 쓰세요."
    )
    return "\n".join(lines)

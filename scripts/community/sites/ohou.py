"""오늘의집(ohou.se) 커뮤니티 검색 — 실제 사용자 질문/게시글 수집.

## 왜 CDP인가 (requests/curl 불가, 2026-08-24 실측)
`ohou.se`는 서버 단에서 봇 차단이 걸려 있어 plain HTTP 요청은 UA를 정상적으로
넣어도 **403**이 난다. 반면 CDP로 띄운 실제 브라우저로 직접 URL 이동하면
정상 로딩된다(로그인 불필요) — 클릭 시뮬레이션도 필요 없고, 검색 URL을
직접 열면 된다.

## 검색 URL (2026-08-24 실측 확정)
    https://ohou.se/search/community?query={URL인코딩 검색어}&search_affect_type=Typing

같은 페이지에 "연관검색어" 칩도 함께 뜬다(예: "조명" 검색 시 탁상조명·
천장조명·스탠드조명·거실조명 등) — 이것도 함께 긁으면 카페 없이 연관
키워드 확장 신호를 얻을 수 있다.

## 게시글 카드 구조 (2026-08-24 실측, css-xxxx 해시 클래스는 배포마다
바뀔 수 있어 태그/구조 기반 셀렉터만 쓴다)
    article > a[href*="/community/posts/"]
      h3                        ← 제목
      span (h3 다음 형제)         ← 본문 스니펫(검색어가 <mark>로 감싸져 있음)
      .css-60smz5 (첫 번째)      ← 게시판 이름
      .css-60smz5 (두 번째)      ← 작성 시각(상대시간)
"""

from __future__ import annotations

import json
import time
import urllib.parse

from scripts.browser.cdp.cdp_helper import CDP
from scripts.common.logger import get_logger

_log = get_logger(__name__)

SEARCH_URL = "https://ohou.se/search/community?query={q}&search_affect_type=Typing"

_EXTRACT_JS = """(function(){
  var out = [];
  var seen = {};
  document.querySelectorAll('article a[href*="/community/posts/"]').forEach(function(a){
    var href = a.getAttribute('href') || '';
    if (seen[href]) return;
    seen[href] = true;
    var h3 = a.querySelector('h3');
    if (!h3) return;
    var snippet = h3.nextElementSibling ? h3.nextElementSibling.textContent.trim() : '';
    var metaSpans = Array.from(a.querySelectorAll('.css-60smz5')).map(function(s){ return s.textContent.trim(); });
    out.push({
      title: h3.textContent.trim(),
      snippet: snippet,
      url: href,
      board: metaSpans[0] || '',
      posted_at: metaSpans[1] || ''
    });
  });
  return JSON.stringify(out);
})()"""


def search_community(query: str, port: int = 9222, wait: float = 3.0) -> dict:
    """오늘의집 커뮤니티에서 query를 검색해 실제 게시글(제목·본문 일부·게시판·
    작성시각) 목록을 반환한다.

    연관검색어 칩은 이 페이지(/search/community)가 아니라 통합검색 탭
    (/search/index)에 따로 있다 — 2026-08-24 1차 구현에서는 뺐다. 셀렉터가
    상단 네비게이션 탭까지 잘못 잡는 문제가 있어, 정확한 요소를 못 찾은
    채로 데이터를 내보내느니 빼는 게 낫다고 판단했다. 필요해지면
    /search/index 페이지를 대상으로 별도 함수로 추가한다.

    반환: {"query": str, "posts": [...]}
    """
    url = SEARCH_URL.format(q=urllib.parse.quote(query))
    cdp = CDP(port=port)
    try:
        cdp.navigate(url, wait=wait)
        time.sleep(1.5)
        raw_posts = cdp.js(_EXTRACT_JS)
    finally:
        cdp.close()

    posts = json.loads(raw_posts) if raw_posts else []
    _log.info("[ohou] '%s' 검색 — 게시글 %d건", query, len(posts))
    return {"query": query, "posts": posts}


if __name__ == "__main__":
    import sys

    q = sys.argv[1] if len(sys.argv) > 1 else "조명"
    result = search_community(q)
    print(json.dumps(result, ensure_ascii=False, indent=2))

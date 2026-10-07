"""네이버 뉴스 스크래핑 — cdp_console API 기반.

cdp_console로 DOM 구조 탐색 후 작성.

구조 확인 결과:
  - .main_brick_item : 언론사별 카드 블록
  - 각 블록 내 a[href*=media.naver] : 언론사명
  - 각 블록 내 a[href*=article] + innerText > 10자 : 기사 제목/URL

사용:
    from scripts.naver.scrape_news import fetch_news, fetch_article

    # 메인 뉴스 (언론사별)
    news = fetch_news()
    for block in news:
        print(block['press'], len(block['articles']))

    # 기사 본문
    body = fetch_article("https://n.news.naver.com/article/...")
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def fetch_news(url: str = "https://news.naver.com") -> list[dict]:
    """네이버 뉴스 메인 — 언론사별 기사 블록 추출.

    Returns:
        [
          {
            "press": "언론사명",
            "updated": "업데이트 시각",
            "articles": [{"title": str, "url": str}, ...]
          }, ...
        ]
    """
    import importlib

    connect = importlib.import_module("scripts.browser.cdp.cdp_console").connect

    with connect() as s:
        if "news.naver.com" not in s.url:
            s.goto(url)
            s.wait(1.5)

        data, err = s.js_json("""(function(){
            return Array.from(document.querySelectorAll('.main_brick_item')).map(function(item){
                // 언론사명 (미디어 링크 텍스트)
                var pressEl = item.querySelector('a[href*="media.naver"]');
                var pressText = pressEl ? pressEl.innerText.trim() : '';
                var parts = pressText.split('\\n');
                var press   = parts[0].trim();
                var updated = parts[1] ? parts[1].trim() : '';

                // 기사 목록
                var articles = Array.from(
                    item.querySelectorAll('a[href*="article"]')
                ).filter(function(a){
                    return a.innerText.trim().length > 10;
                }).map(function(a){
                    return {
                        title: a.innerText.trim().replace(/\\s+/g, ' '),
                        url:   a.href
                    };
                });

                return { press: press, updated: updated, articles: articles };
            }).filter(function(x){ return x.articles.length > 0; });
        })()""")

        return [] if err else data


def fetch_article(article_url: str) -> dict:
    """네이버 뉴스 기사 본문 추출.

    Returns:
        {
          "title": str,
          "press": str,
          "datetime": str,
          "body": str,
          "url": str
        }
    """
    import importlib

    connect = importlib.import_module("scripts.browser.cdp.cdp_console").connect

    with connect() as s:
        s.goto(article_url)
        s.wait(1.5)

        data, err = s.js_json("""(function(){
            // 제목
            var title = (
                document.querySelector('#title_area span, .media_end_head_headline') ||
                document.querySelector('h2#title_area, h2.end_tit')
            );
            // 언론사
            var press = document.querySelector(
                '.media_end_head_top a img, .press_logo img'
            );
            var pressName = press ? (press.alt || press.title || '') : (
                (document.querySelector('.media_end_linked_more_point') || {}).innerText || ''
            );
            // 작성시각
            var dt = document.querySelector(
                '.media_end_head_info_datestamp_time, ._ARTICLE_DATE_TIME'
            );
            // 본문
            var body = document.querySelector(
                '#dic_area, .go_trans._article_content, article#dic_area'
            );
            var bodyText = body ? body.innerText.trim() : '';
            // 첫 3문장 추출 (마침표/느낌표/물음표 기준, 최소 20자)
            var summary = '';
            if(bodyText){
                var sents = bodyText.split(/(?<=[.!?…])\\s+/).filter(function(s){ return s.trim().length >= 20; });
                summary = sents.slice(0,3).join(' ').slice(0,300);
            }
            return {
                title:    title ? title.innerText.trim() : '',
                press:    pressName.trim(),
                datetime: dt ? (dt.getAttribute('data-date-time') || dt.innerText.trim()) : '',
                body:     bodyText.replace(/\\s+/g, ' '),
                summary:  summary,
                url:      location.href
            };
        })()""")

        return {} if err else data


def fetch_search(query: str, page: int = 1) -> list[dict]:
    """네이버 뉴스 검색 결과 추출.

    Returns:
        [{"title": str, "url": str, "press": str, "datetime": str, "summary": str}, ...]
    """
    import importlib

    connect = importlib.import_module("scripts.browser.cdp.cdp_console").connect

    search_url = f"https://search.naver.com/search.naver?where=news&query={query}&start={(page - 1) * 10 + 1}"

    with connect() as s:
        s.goto(search_url)
        s.wait(1.5)

        data, err = s.js_json("""(function(){
            // fds-news-item-list-tab 내 기사 카드 단위 정밀 추출
            var tab = document.querySelector('[class*="fds-news-item-list-tab"]');
            if(!tab) return [];

            var SKIP_DOMAINS = ['media.naver.com', 'search.naver.com', 'keep.naver.com', 'n.news.naver.com'];
            var SKIP_TEXTS   = ['Keep에 저장', 'Keep에 바로가기', '네이버뉴스'];

            function isSkip(a){
                var t = a.innerText.trim();
                for(var k=0; k<SKIP_TEXTS.length; k++) if(t === SKIP_TEXTS[k]) return true;
                if(t.indexOf('관련뉴스') > -1) return true;
                for(var d=0; d<SKIP_DOMAINS.length; d++) if(a.href.indexOf(SKIP_DOMAINS[d]) > -1) return true;
                return false;
            }

            var results = [];
            Array.from(tab.children).forEach(function(card){
                if(card.className.indexOf('sds-comps-divider') > -1) return;

                // 언론사: media.naver.com/press 링크 중 텍스트 있는 첫 것
                var press = '';
                Array.from(card.querySelectorAll('a[href*="media.naver.com/press"]')).forEach(function(a){
                    if(!press && a.innerText.trim().length > 0) press = a.innerText.trim();
                });

                // 날짜: '시간 전'/'분 전'/'일 전' 또는 날짜형 패턴 span
                var datetime = '';
                Array.from(card.querySelectorAll('span')).forEach(function(sp){
                    if(datetime) return;
                    var t = sp.innerText.trim();
                    if(/\\d+시간\\s*전|\\d+분\\s*전|\\d+일\\s*전|어제|\\d{4}-\\d{2}-\\d{2}|\\d{1,2}월\\s*\\d{1,2}일/.test(t)) datetime = t;
                });

                // 기사 링크 후보: 내부/Keep 제외, 10~150자
                var extLinks = Array.from(card.querySelectorAll('a')).filter(function(a){
                    var t = a.innerText.trim();
                    return !isSkip(a) && t.length >= 10 && t.length <= 150;
                });
                if(extLinks.length === 0) return;

                // 첫 번째 = 제목, 두 번째 = 요약 (다른 URL인 경우)
                var title   = extLinks[0].innerText.trim().replace(/\\s+/g,' ');
                var url     = extLinks[0].href;
                var summary = '';
                if(extLinks[1] && extLinks[1].href !== url){
                    summary = extLinks[1].innerText.trim().replace(/\\s+/g,' ').slice(0,150);
                }

                results.push({title:title, url:url, press:press, datetime:datetime, summary:summary});
            });
            return results;
        })()""")

        return [] if err else data


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "main"

    if cmd == "main":
        print("네이버 뉴스 메인 스크래핑\n" + "=" * 60)
        blocks = fetch_news()
        print(f"언론사 블록: {len(blocks)}개\n")
        for b in blocks[:5]:
            print(f"[{b['press']}] {b['updated']}")
            for a in b["articles"][:3]:
                print(f"  · {a['title'][:60]}")
            print()

    elif cmd == "article" and len(sys.argv) > 2:
        print("기사 본문 스크래핑\n" + "=" * 60)
        art = fetch_article(sys.argv[2])
        print(f"제목: {art.get('title', '')}")
        print(f"언론사: {art.get('press', '')}")
        print(f"일시: {art.get('datetime', '')}")
        print(f"요약: {art.get('summary', '')}")
        print(f"본문({len(art.get('body', ''))}자): {art.get('body', '')[:200]}...")

    elif cmd == "search" and len(sys.argv) > 2:
        q = " ".join(sys.argv[2:])
        print(f"뉴스 검색: {q!r}\n" + "=" * 60)
        results = fetch_search(q)
        print(f"결과: {len(results)}건\n")
        for r in results[:5]:
            print(f"[{r['press']}] {r['datetime']}")
            print(f"  {r['title']}")
            print(f"  {r['summary'][:80]}")
            print()

    else:
        print("사용법:")
        print("  python scrape_news.py main                      # 메인 뉴스")
        print("  python scrape_news.py article <url>             # 기사 본문")
        print("  python scrape_news.py search <검색어>           # 뉴스 검색")

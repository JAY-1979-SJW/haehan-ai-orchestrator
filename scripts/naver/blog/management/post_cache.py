"""발행글 콘텐츠 캐시 — skyjwsin 블로그 전체 글을 긁어 로컬 JSON에 저장 (L5, raw CDP).

`analytics.py`(방문자/유입 통계)와 역할이 다르다 — 이건 **콘텐츠**(제목·본문·
태그) 캐시다.

## 왜 필요한가
`data/blog_topic_cache.json`은 AI가 자동 발행한 글만 기록한다
(`publish.py::record_success()` 경유). 사용자가 직접 쓴 글은 안 잡혀서
중복 발행 방지가 반쪽이고, 전체 글이 기준서를 지키는지도 알 수 없다.

## 검증된 셀렉터 (2026-08-23 실측 — 이거 아니면 오답이 나온다)
- 본문: **iframe 안의 `.se-main-container`**
  `document.body.innerText`를 통째로 쓰면 좌측 카테고리 메뉴·태그 목록·
  공지글이 본문 앞에 섞여 들어온다(하위 모델 위임 시 실제 발생).
- 날짜: **`.se_publishDate`**
  `.date`를 쓰면 **공지글 날짜**나 하단 "이 블로그의 다른 글" 목록 날짜를
  잡는다. 실제로 8.20 글을 8.15로 잘못 기록한 사고가 있었다.
- 태그: `a` 중 텍스트가 `#`로 시작하는 것만.
  필터 없이 `.post_tag a` 등을 쓰면 "태그수정·취소·확인" 버튼이 섞인다.
- 목록: **화면을 긁지 말고 `PostTitleListAsync.naver` JSON API를 쓴다.**
  `PostList.naver` 화면은 `currentPage`가 먹지 않아 11건에서 멈췄다
  (전체 103편). API는 페이지네이션이 정상이고 조회수·카테고리·공개여부
  까지 준다. 단 응답의 `pagingHtml`에 JSON 비표준 이스케이프(`\\'`)가
  섞여 있어 `raw.replace("\\\\'", "'")` 후 파싱해야 한다.

## 사용
    python -m scripts.naver.blog.management.post_cache --limit 3   # 드라이런
    python -m scripts.naver.blog.management.post_cache             # 전체(증분)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import unquote_plus

_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.cdp_helper import CDP  # noqa: E402
from scripts.logger import get_logger  # noqa: E402

_log = get_logger(__name__)

BLOG_ID = "skyjwsin"
CACHE_PATH = _ROOT / "data" / "blog_posts_cache.json"

# 목록은 네이버 내부 JSON API를 쓴다(2026-08-23 확정).
# 처음엔 PostList.naver 화면을 긁었는데 `currentPage`가 먹지 않아 11건에서
# 멈췄다(전체 103편). 이 API는 페이지네이션이 정상 동작하고 조회수·카테고리·
# 공개여부(openType)까지 한 번에 준다.
LIST_API = (
    "https://blog.naver.com/PostTitleListAsync.naver"
    f"?blogId={BLOG_ID}&viewdate=&currentPage={{page}}"
    "&categoryNo=0&parentCategoryNo=&countPerPage={per_page}"
)

# 글 본문 추출 — 위 docstring의 "검증된 셀렉터" 참고
_POST_JS = """(function(){
  function pick(doc){
    if (!doc) return null;
    // 스마트에디터 ONE(신) → 구 에디터 순으로 폴백.
    // 2026-08-23 실측: logNo 100xxx대 옛 글은 .se-main-container가 없고
    // #postViewArea를 쓴다. 이걸 빼먹어 103편 중 29편이 통째로 누락됐었다.
    var main = doc.querySelector('.se-main-container') || doc.querySelector('#postViewArea');
    if (!main) return null;
    var titleEl = doc.querySelector('.se-title-text, .htitle, .pcol1 .title');
    var dateEl = doc.querySelector('.se_publishDate, .date');
    var tags = Array.from(doc.querySelectorAll('a'))
      .map(function(a){ return (a.innerText || '').trim(); })
      .filter(function(t){ return t.indexOf('#') === 0 && t.length > 1; });
    var uniq = [];
    tags.forEach(function(t){ if (uniq.indexOf(t) === -1) uniq.push(t); });
    return JSON.stringify({
      title: titleEl ? titleEl.innerText.trim() : '',
      posted_at: dateEl ? dateEl.innerText.trim() : '',
      tags: uniq,
      body: main.innerText.trim()
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


def load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            _log.warning("[post-cache] 캐시 로드 실패, 새로 시작: %s", e)
    return {"posts": []}


def save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def collect_log_nos(cdp: CDP, max_pages: int = 30, per_page: int = 30) -> list[dict]:
    """목록 API를 순회해 글 메타(logNo/제목/카테고리/조회수/공개여부)를 모은다."""
    found: dict[str, dict] = {}
    for page in range(1, max_pages + 1):
        cdp.navigate(LIST_API.format(page=page, per_page=per_page), wait=2.5)
        time.sleep(1.0)
        raw = cdp.js("document.body ? document.body.innerText : ''")
        if not raw:
            break
        # 네이버 응답의 `pagingHtml` 안에 `\'`가 들어있는데 JSON 표준에선
        # 허용되지 않는 이스케이프라 그대로 파싱하면 깨진다(2026-08-23 실측).
        try:
            data = json.loads(raw.replace("\\'", "'"))
        except Exception as e:
            _log.warning("[post-cache] 목록 %d페이지 파싱 실패: %s", page, e)
            break
        items = data.get("postList", [])
        new = 0
        for it in items:
            no = str(it.get("logNo", ""))
            if not no or no in found:
                continue
            found[no] = {
                "logNo": no,
                "title": unquote_plus(it.get("title", "")),
                "categoryNo": str(it.get("categoryNo", "")),
                "read_count": it.get("readCount", ""),
                "open_type": str(it.get("openType", "")),
                "list_date": it.get("addDate", ""),
            }
            new += 1
        _log.info("[post-cache] 목록 %d페이지: 신규 %d건 (누적 %d)", page, new, len(found))
        if new == 0 or not items:
            break
    return list(found.values())


def extract_post(cdp: CDP, log_no: str) -> dict | None:
    """글 1편을 열어 제목·본문·태그·작성일을 추출."""
    cdp.navigate(f"https://blog.naver.com/{BLOG_ID}/{log_no}", wait=3)
    time.sleep(1.5)
    raw = cdp.js(_POST_JS)
    if not raw:
        _log.warning("[post-cache] %s 추출 실패(.se-main-container 없음)", log_no)
        return None
    try:
        data = json.loads(raw)
    except Exception as e:
        _log.warning("[post-cache] %s JSON 파싱 실패: %s", log_no, e)
        return None
    data["logNo"] = log_no
    data["char_count"] = len(data.get("body", ""))
    return data


def build_cache(limit: int | None = None, port: int = 9222) -> dict:
    """증분 수집: 이미 캐시에 있는 logNo는 건너뛴다."""
    cache = load_cache()
    cached = {p["logNo"] for p in cache.get("posts", [])}

    cdp = CDP(port=port)
    try:
        listing = collect_log_nos(cdp)
        todo = [x for x in listing if x["logNo"] not in cached]
        if limit:
            todo = todo[:limit]
        _log.info("[post-cache] 전체 %d건 / 신규 %d건 수집 시작", len(listing), len(todo))

        for i, item in enumerate(todo, 1):
            post = extract_post(cdp, item["logNo"])
            if post:
                # 목록 API가 준 메타(조회수/카테고리/공개여부)를 함께 보존
                for k in ("categoryNo", "read_count", "open_type", "list_date"):
                    post[k] = item.get(k, "")
                cache.setdefault("posts", []).append(post)
                save_cache(cache)  # 중간에 끊겨도 진행분 보존
                _log.info(
                    "[post-cache] (%d/%d) %s — %d자, 태그 %d개",
                    i,
                    len(todo),
                    post["title"][:30],
                    post["char_count"],
                    len(post["tags"]),
                )
    finally:
        cdp.close()
    return cache


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="이번 실행에서 수집할 최대 글 수")
    ap.add_argument("--port", type=int, default=9222)
    args = ap.parse_args()

    cache = build_cache(limit=args.limit, port=args.port)
    posts = cache.get("posts", [])
    print(f"\n캐시 총 {len(posts)}건 → {CACHE_PATH}")
    for p in posts[-5:]:
        print(f"  · [{p['posted_at']}] {p['title'][:40]} ({p['char_count']}자, 태그{len(p['tags'])})")


if __name__ == "__main__":
    main()

"""네이버 카페 게시글 수집기 — 3개월치 전수 수집.

사용:
    from scripts.browser.cdp.connection import get_page
    from scripts.naver.cafe.collector import collect_articles

    articles = collect_articles(
        page,
        cafe_url="https://cafe.naver.com/0moo",
        days=90,           # 최근 N일 (기본 90일)
        max_detail=200,    # 상세 방문 최대 글 수 (0 = 목록만)
        save_path="data/cafe/raw_articles.json",
    )
"""

from __future__ import annotations

import json
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from playwright.sync_api import Page

from scripts.common.app_paths import repo_root
from scripts.common.logger import get_logger
from scripts.naver.common.auth import ensure_naver_login

_log = get_logger(__name__)

ROOT = repo_root()


def _cafe_out_dir() -> Path:
    from scripts.common.data_paths import get_app_dir

    return get_app_dir("cafe")


_OUT_DIR = _cafe_out_dir()

# ── URL 패턴 ──────────────────────────────────────────────────────────
# ArticleList.nhn → 리다이렉트 후 실제 menus/0 페이지 (클래식 DOM 유지)
_LIST_URL = (
    "https://cafe.naver.com/ArticleList.nhn?search.clubid={clubid}&search.boardtype=L&search.page={page}&userDisplay=50"
)
# 전체글보기(boardtype=L)는 네이버 카페 쪽 조회 페이지 상한(약 150p)에 걸려 오래된 글에
# 못 닿는 경우가 있다(2026-08-16 확인). 게시판별(boardtype=M&menuid=)로 나눠 돌리면
# 게시판마다 별도 상한이 적용돼 더 오래된 글까지 닿을 수 있다.
_BOARD_LIST_URL = (
    "https://cafe.naver.com/ArticleList.nhn?search.clubid={clubid}&search.boardtype=L"
    "&search.menuid={menu_id}&search.page={page}&userDisplay=50"
)
_SEARCH_URL = "https://cafe.naver.com/ArticleSearchList.nhn?search.clubid={clubid}&search.searchBy=0&search.query={query}&search.page={page}&userDisplay=50"
# 상세글은 PC용 신규 SPA(/f-e/cafes/.../articles/...)가 CDP 자동화에서 하이드레이션이
# 안 되는 문제가 있어(2026-08-15 확인, 본문 이 늘 빈 값) 모바일 뷰로 방문한다.
# 모바일 뷰는 서버에서 완성된 DOM을 내려줘 CDP 환경에서도 안정적으로 읽힌다.
_ARTICLE_URL = "https://m.cafe.naver.com/ca-fe/web/cafes/{clubid}/articles/{article_id}"


def _get_clubid(page: Page, cafe_url: str) -> str:
    """카페 URL → clubid 추출."""
    # URL에서 직접 추출 시도
    m = re.search(r"/cafes/(\d+)", cafe_url)
    if m:
        return m.group(1)
    # 카페 홈 방문 후 추출
    page.goto(cafe_url, timeout=20000, wait_until="domcontentloaded")
    time.sleep(3)
    for f in page.frames:
        m = re.search(r"clubid=(\d+)", f.url)
        if m:
            return m.group(1)
    html = page.content()
    for pattern in [r'"clubid"\s*:\s*"?(\d+)"?', r"clubid=(\d+)", r"/cafes/(\d+)"]:
        m = re.search(pattern, html)
        if m:
            return m.group(1)
    raise ValueError(f"clubid 추출 실패: {cafe_url}")


def _parse_date(date_str: str) -> date | None:
    """카페 날짜 문자열 → date 객체. '2026.05.06.' / '05.06.' / '2026-05-06' 형식 처리."""
    s = date_str.strip().rstrip(".")
    today = date.today()
    for fmt in ("%Y.%m.%d", "%Y-%m-%d", "%Y. %m. %d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    # 'MM.DD' — 연도 없음 → 올해 추정
    m = re.match(r"^(\d{2})\.(\d{2})$", s)
    if m:
        return date(today.year, int(m.group(1)), int(m.group(2)))
    # 'HH:MM' 형식 (오늘 글)
    if re.match(r"^\d{2}:\d{2}$", s):
        return today
    return None


def _extract_search_page(page: Page, clubid: str, query: str, page_no: int) -> list[dict]:
    """카페 검색 결과 1페이지 추출 (키워드 필터)."""
    from urllib.parse import quote

    url = _SEARCH_URL.format(clubid=clubid, query=quote(query), page=page_no)
    page.goto(url, timeout=25000, wait_until="domcontentloaded")
    time.sleep(3)

    try:
        items = page.evaluate("""
        () => {
            const out = [];
            const rows = document.querySelectorAll('.article-board tbody tr');
            rows.forEach(row => {
                const titleEl = row.querySelector('a.article');
                if (!titleEl) return;
                const title = titleEl.innerText.trim();
                if (!title) return;
                const href = titleEl.href || '';
                let author = '', date_str = '', views = '', comments = '';
                row.querySelectorAll('td').forEach(td => {
                    const cls = td.className || '';
                    if (cls.includes('type_date')) {
                        date_str = td.innerText.trim();
                    } else if (cls.includes('type_readCount')) {
                        views = td.innerText.trim().replace(/[^0-9]/g, '');
                    } else if (cls.includes('type_replyCount')) {
                        comments = td.innerText.trim().replace(/[^0-9]/g, '');
                    } else {
                        const nick = td.querySelector('.p-nick, .nick');
                        if (nick && !author) author = nick.innerText.trim();
                    }
                });
                const m = /articles\\/(\\d+)/.exec(href);
                const article_id = m ? m[1] : '';
                const is_notice = row.className.includes('board-notice');
                if (article_id) out.push({ title, href, author, date_str, views, comments, article_id, board: '', is_notice });
            });
            return out;
        }
        """)
        if items:
            _log.debug("[cafe-search] 검색 p%d: %d건", page_no, len(items))
            return items
    except Exception as e:  # noqa: BLE001 - 네이버 카페 목록/상세 읽기전용 수집 — JS 추출 실패 시 빈 리스트 반환, 상세 추출은 재시도 후 실패해도 빈 dict 반환, 쓰기 없음
        _log.warning("[cafe-search] JS 추출 실패 p%d: %s", page_no, e)
    return []


def _extract_list_page(page: Page, clubid: str, page_no: int, menu_id: str = "") -> list[dict]:
    """카페 목록 1페이지 추출. menu_id 지정 시 해당 게시판만, 아니면 전체글보기."""
    url = (
        _BOARD_LIST_URL.format(clubid=clubid, menu_id=menu_id, page=page_no)
        if menu_id
        else _LIST_URL.format(clubid=clubid, page=page_no)
    )
    page.goto(url, timeout=25000, wait_until="domcontentloaded")
    time.sleep(3)

    # 클래식 ArticleList DOM 파싱 (td 클래스 기반)
    try:
        items = page.evaluate("""
        () => {
            const out = [];
            const rows = document.querySelectorAll('.article-board tbody tr');
            rows.forEach(row => {
                const titleEl = row.querySelector('a.article');
                if (!titleEl) return;
                const title = titleEl.innerText.trim();
                if (!title) return;
                const href = titleEl.href || '';
                let author = '', date_str = '', views = '', comments = '';
                row.querySelectorAll('td').forEach(td => {
                    const cls = td.className || '';
                    if (cls.includes('type_date')) {
                        date_str = td.innerText.trim();
                    } else if (cls.includes('type_readCount')) {
                        views = td.innerText.trim().replace(/[^0-9]/g, '');
                    } else if (cls.includes('type_replyCount')) {
                        comments = td.innerText.trim().replace(/[^0-9]/g, '');
                    } else {
                        const nick = td.querySelector('.p-nick, .nick');
                        if (nick && !author) author = nick.innerText.trim();
                    }
                });
                const m = /articles\\/(\\d+)/.exec(href);
                const article_id = m ? m[1] : '';
                const is_notice = row.className.includes('board-notice');
                if (article_id) out.push({ title, href, author, date_str, views, comments, article_id, board: '', is_notice });
            });
            return out;
        }
        """)
        if items:
            _log.debug("[cafe-collect] 목록 p%d: %d건", page_no, len(items))
            return items
    except Exception as e:  # noqa: BLE001 - 네이버 카페 목록/상세 읽기전용 수집 — JS 추출 실패 시 빈 리스트 반환, 상세 추출은 재시도 후 실패해도 빈 dict 반환, 쓰기 없음
        _log.warning("[cafe-collect] JS 추출 실패 p%d: %s", page_no, e)
    return []


def _fetch_article_detail(page: Page, clubid: str, article_id: str) -> dict:
    """글 상세 방문 → view_count, like_count, comment_count, board, tags, body, comments 추출.

    모바일 카페 뷰(m.cafe.naver.com) DOM 기준. 좋아요 수는 위젯이 비동기로 채워
    넣어 클래스 셀렉터가 불안정하므로, 값이 확정적으로 붙는 인접 문구("좋아요한
    사람 목록으로 이동")를 앵커로 정규식 추출한다. 댓글은 최초 로드된 페이지
    분량만 수집한다(더보기 클릭 등 추가 조작 없음 — read-only 원칙).
    """
    url = _ARTICLE_URL.format(clubid=clubid, article_id=article_id)
    for attempt in range(2):
        try:
            return _fetch_article_detail_once(page, url)
        except Exception as e:  # noqa: BLE001 - 네이버 카페 목록/상세 읽기전용 수집 — JS 추출 실패 시 빈 리스트 반환, 상세 추출은 재시도 후 실패해도 빈 dict 반환, 쓰기 없음
            _log.warning("[cafe-collect] 상세 추출 실패(시도 %d) %s: %s", attempt + 1, article_id, e)
            time.sleep(2.0)
    return {}


def _fetch_article_detail_once(page: Page, url: str) -> dict:
    page.goto(url, timeout=25000, wait_until="domcontentloaded")
    time.sleep(3.0)
    detail = page.evaluate("""
        () => {
            const board = (
                document.querySelector('.tit_menu')?.innerText || ''
            ).split('\\n')[0].trim();
            const author = (
                document.querySelector('.end_user_nick, .writer_area .nick')?.innerText || ''
            ).trim();
            const view_count = (
                document.querySelector('.no.font_l')?.innerText || ''
            ).replace(/[^0-9]/g, '');
            const bodyText = document.body.innerText || '';
            const likeMatch = bodyText.match(/좋아요\\s*([\\d,]+)\\s*좋아요한 사람/);
            const like_count = likeMatch ? likeMatch[1].replace(/,/g, '') : '';
            const commentCountText = document.querySelector('.CafeCommentSort')?.innerText || '';
            const commentMatch = commentCountText.match(/댓글\\s*([\\d,]+)/);
            const comment_count = commentMatch ? commentMatch[1].replace(/,/g, '') : '0';
            const tags = (document.querySelector('.tag_area')?.innerText || '')
                .split('#').map(s => s.trim()).filter(Boolean);
            const body = (
                document.querySelector('.se-viewer, .ContentRenderer')?.innerText || ''
            ).trim().substring(0, 3000);
            const written_at = (
                document.querySelector('.date.font_l')?.innerText || ''
            ).replace('작성일', '').trim();
            const comments = Array.from(document.querySelectorAll('.comment_item')).map(el => {
                const footer = el.querySelector('.comment_footer')?.innerText || '';
                const dateMatch = footer.match(/\\d{4}\\.\\d{2}\\.\\d{2}\\.\\s*\\d{2}:\\d{2}/);
                return {
                    author: (el.querySelector('.nick_name')?.innerText || '').trim(),
                    date: dateMatch ? dateMatch[0] : '',
                    text: (el.querySelector('.comment_content')?.innerText || '').trim().substring(0, 500),
                };
            }).filter(c => c.text);
            return {
                board, author, view_count, like_count, tags, body, comment_count, written_at,
                comments, comments_loaded_count: comments.length,
            };
        }
        """)
    return detail or {}


def _new_article(aid: str, item: dict, d) -> dict:
    """목록 항목 1건 -> 게시글 dict(상세 필드는 기본값)."""
    return (
    {
        "article_id": aid,
        "title": item.get("title", ""),
        "href": item.get("href", ""),
        "author": item.get("author", ""),
        "date_str": item.get("date_str", ""),
        "date": d.isoformat() if d else "",
        "board": item.get("board", ""),
        "view_count": item.get("views", "0") or "0",
        "like_count": "0",
        "comment_count": item.get("comments", "0") or "0",
        "tags": [],
        "body": "",
    }
    )


def _visit_details(page: Page, clubid: str, articles: list[dict], max_detail: int) -> None:
    """상세 방문(max_detail > 0 일 때) — articles 를 제자리 갱신."""
    if max_detail > 0:
        detail_targets = articles[:max_detail]
        _log.info("[cafe-collect] 상세 방문 시작: %d건", len(detail_targets))
        for i, art in enumerate(detail_targets, 1):
            detail = _fetch_article_detail(page, clubid, art["article_id"])
            if detail:
                art.update(
                    {
                        "board": detail.get("board") or art.get("board", ""),
                        "author": detail.get("author") or art.get("author", ""),
                        "view_count": detail.get("view_count") or art.get("view_count", "0"),
                        "like_count": detail.get("like_count", "0"),
                        "comment_count": str(detail.get("comment_count") or art.get("comment_count", "0")),
                        "tags": detail.get("tags", []),
                        "body": detail.get("body", ""),
                        "written_at": detail.get("written_at", ""),
                        "comments": detail.get("comments", []),
                        "comments_loaded_count": detail.get("comments_loaded_count", 0),
                    }
                )
            if i % 10 == 0:
                _log.info("[cafe-collect] 상세 %d/%d 완료", i, len(detail_targets))


def _save_articles(articles: list[dict], save_path: str | None, kw: str) -> None:
    """수집 결과를 JSON 으로 저장."""
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    if save_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        if kw:
            slug = re.sub(r"[^\w가-힣]", "_", kw)[:30]
            save_path = str(_OUT_DIR / f"keyword_{slug}_raw_articles_{ts}.json")
        else:
            save_path = str(_OUT_DIR / f"raw_articles_{ts}.json")
    Path(save_path).write_text(json.dumps(articles, ensure_ascii=False, indent=2), encoding="utf-8")
    _log.info("[cafe-collect] 저장 완료: %s (%d건)", save_path, len(articles))


def collect_articles(  # noqa: PLR0913 - 공개 시그니처 유지(동작 변경 금지 리팩터링)
    page: Page,
    cafe_url: str,
    days: int = 90,
    max_pages: int = 200,
    max_detail: int = 300,
    save_path: str | None = None,
    keyword: str = "",
    menu_id: str = "",
) -> list[dict]:
    """카페 게시글 수집.

    Args:
        page: Playwright 페이지
        cafe_url: 카페 홈 URL (예: https://cafe.naver.com/0moo)
        days: 수집 기간(일). 기본 90일(3개월).
        max_pages: 목록 최대 페이지 수 (안전 상한)
        max_detail: 상세 방문 최대 글 수. 0이면 목록 메타만 수집.
        save_path: JSON 저장 경로. None이면 data/cafe/ 자동 경로.
        keyword: 검색어. 지정 시 해당 키워드 검색 결과만 수집. 빈 문자열이면 전수 수집.
        menu_id: 게시판 ID. 지정 시 해당 게시판만 수집(전체글보기 조회 상한 우회용).

    Returns:
        수집된 게시글 dict 목록.
    """
    if not ensure_naver_login(page).get("ok"):
        raise RuntimeError("네이버 로그인 필요")

    cutoff = date.today() - timedelta(days=days)
    kw = keyword.strip()
    _log.info("[cafe-collect] 수집 시작 — cutoff=%s, cafe=%s, keyword=%r", cutoff, cafe_url, kw or "(전수)")

    clubid = _get_clubid(page, cafe_url)
    _log.info("[cafe-collect] clubid=%s", clubid)

    articles: list[dict] = []
    seen_ids: set[str] = set()
    stop = False

    for page_no in range(1, max_pages + 1):
        if stop:
            break
        items = (
            _extract_search_page(page, clubid, kw, page_no)
            if kw
            else _extract_list_page(page, clubid, page_no, menu_id)
        )
        if not items:
            _log.info("[cafe-collect] p%d: 결과 없음 — 수집 종료", page_no)
            break

        new_in_page = 0
        for item in items:
            aid = item.get("article_id", "")
            if not aid or aid in seen_ids:
                continue

            # 공지글은 날짜 무관 수집 (오래된 공지도 항상 상단에 표시됨)
            is_notice = item.get("is_notice", False)

            # 날짜 파싱
            d = _parse_date(item.get("date_str", ""))
            if not is_notice and d is not None and d < cutoff:
                _log.info("[cafe-collect] p%d: cutoff 도달 (%s) — 종료", page_no, d)
                stop = True
                break

            seen_ids.add(aid)
            articles.append(_new_article(aid, item, d))
            new_in_page += 1

        _log.info("[cafe-collect] p%d: +%d건 (누계 %d건)", page_no, new_in_page, len(articles))

        if new_in_page == 0 and page_no > 1:
            _log.info("[cafe-collect] 신규 없음 — 수집 종료")
            break

    _log.info("[cafe-collect] 목록 수집 완료: %d건", len(articles))

    # 상세 방문
    _visit_details(page, clubid, articles, max_detail)

    # 저장
    _save_articles(articles, save_path, kw)
    return articles

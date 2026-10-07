"""네이버 카페 자동화 패키지.

## 기능 목록 (새 작업 전 여기를 먼저 확인)

### 수집 (collection/)
- collect_articles(page, cafe_url, days, max_detail, keyword)
    → 카페 게시글 전수 수집 또는 키워드 검색 수집
    → 저장: data/cafe/raw_articles_*.json  (keyword 있으면 keyword_{slug}_*.json)
- get_my_cafes(page)          → 내 가입 카페 목록
- save_my_cafes(cafes)        → data/cafe/my_cafes.json 저장

### 분류/분석 (analysis/)
- run_pipeline(input_path)    → 3단계 분류 (규칙→형태소→TF-IDF) → classified_*.json
- organize(input_path)        → 군집화·중복제거·KB 구조화 → organized_kb_*.json
- prepare_posts_for_review(posts, context) → 게시글 정리(무료) — Claude Code가 직접 분석

### 글쓰기 (write/)
- write_post(page, cafe_url, board_name, title, body, ...)
- confirm_publish(page)

### API 엔드포인트 (ai_orchestrator/connectors/naver_cafe/naver_cafe_router.py)
- POST /naver-cafe/collect            (cafe_url, days, max_detail, keyword)
- POST /naver-cafe/collect-my-cafes
- POST /naver-cafe/ai-analyze         (category, days, max_posts)
- GET  /naver-cafe/articles           (limit, offset, category)
- GET  /naver-cafe/summary
- GET  /naver-cafe/kb
- GET  /naver-cafe/report

### 클래스 (하위 호환)
- NaverCafe: open_my_cafes / list_posts / read_post / write_post

### 게시판 관리 (management/)
- list_boards(page, cafe_url)                  → 현재 게시판(메뉴) 목록 조회
- add_board(page, cafe_url, name, board_type)  → 신규 게시판 추가 (BOARD_TYPES 참고)
"""

from __future__ import annotations

import contextlib
import time

from playwright.sync_api import Page

from scripts.community.analyzer import prepare_posts_for_review
from scripts.common.logger import get_logger
from scripts.naver.common.auth import ensure_naver_login
from scripts.browser.popup.popup_detector import handle_page_popups

from .analysis.organizer import organize
from .analysis.pipeline import run_pipeline
from .collection.collector import collect_articles
from .collection.explorer import get_my_cafes, save_my_cafes
from .management.board import BOARD_TYPES, add_board, list_boards
from .writer import confirm_publish, write_post

_log = get_logger(__name__)

MY_CAFES_URL = "https://section.cafe.naver.com/ca-fe/home/recent-articles"


class NaverCafe:
    """네이버 카페 자동화 — 글/댓글/조회 (기존 API 호환)."""

    def __init__(self, page: Page):
        self.page = page

    def _ensure_login(self) -> bool:
        result = ensure_naver_login(self.page)
        return bool(result.get("ok"))

    def open_my_cafes(self) -> list[dict]:
        if not self._ensure_login():
            return []
        self.page.goto(MY_CAFES_URL, timeout=20000, wait_until="domcontentloaded")
        time.sleep(2.5)
        # 네이버 카페 읽기전용 조회 - 팝업 닫기 실패는 목록 조회에 영향 없어 무시하고 계속
        with contextlib.suppress(Exception):
            handle_page_popups(self.page, timeout_s=1.5)
        try:
            return self.page.evaluate("""
            () => {
                const out = [];
                const seen = new Set();
                document.querySelectorAll('a[href*="cafe.naver.com"]').forEach(a => {
                    const href = a.href || '';
                    const m = /cafe\\.naver\\.com\\/([a-zA-Z0-9_-]+)/.exec(href);
                    if (!m) return;
                    const cafe_id = m[1];
                    if (seen.has(cafe_id)) return;
                    if (['ManageCafe', 'CafeList', 'CafeSearch'].includes(cafe_id)) return;
                    seen.add(cafe_id);
                    const name = (a.innerText || a.title || '').trim().substring(0, 40);
                    if (name && name.length >= 2)
                        out.push({cafe_id, name, url: 'https://cafe.naver.com/' + cafe_id});
                });
                return out;
            }
            """)
        except Exception as e:  # noqa: BLE001 - 네이버 카페 읽기전용 조회(NaverCafe: open_my_cafes/list_posts/read_post) — 각 except는 빈 리스트 또는 오류 dict를 반환하며, 실제 글쓰기(write_post)는 별도 writer 모듈에 위임되어 이 파일에 포함되지 않음.
            _log.error("[naver-cafe] open_my_cafes 실패: %s", e)
            return []

    def list_posts(self, cafe_url: str, board_no: int | str = "", limit: int = 30) -> list[dict]:
        if not self._ensure_login():
            return []
        url = (
            cafe_url
            if not board_no
            else f"{cafe_url}?iframe_url=/ArticleList.nhn?search.clubid=&search.menuid={board_no}"
        )
        self.page.goto(url, timeout=20000, wait_until="domcontentloaded")
        time.sleep(2.5)
        for f in self.page.frames:
            if "ArticleList" in f.url or "cafe.naver.com" in f.url:
                try:
                    posts = f.evaluate(
                        """
                    (limit) => {
                        const out = [];
                        document.querySelectorAll('.article-board tbody tr, .board-list li').forEach((row, i) => {
                            if (i >= limit) return;
                            const title = row.querySelector('.article, .tit, .subject a')?.innerText?.trim() || '';
                            const author = row.querySelector('.p-nick, .name, .writer')?.innerText?.trim() || '';
                            const date = row.querySelector('.date, .time')?.innerText?.trim() || '';
                            const link = row.querySelector('a')?.href || '';
                            if (title) out.push({title, author, date, link});
                        });
                        return out;
                    }
                    """,
                        limit,
                    )
                    if posts:
                        return posts
                except Exception:  # noqa: BLE001 - 네이버 카페 읽기전용 조회(NaverCafe: open_my_cafes/list_posts/read_post) — 각 except는 빈 리스트 또는 오류 dict를 반환하며, 실제 글쓰기(write_post)는 별도 writer 모듈에 위임되어 이 파일에 포함되지 않음.
                    continue
        return []

    def read_post(self, post_url: str) -> dict:
        if not self._ensure_login():
            return {"error": "login_failed"}
        self.page.goto(post_url, timeout=20000, wait_until="domcontentloaded")
        time.sleep(2.5)
        for f in self.page.frames:
            if "ArticleRead" in f.url or "PostView" in f.url:
                try:
                    return f.evaluate("""
                    () => ({
                        title: document.querySelector('.title_area, .tit_area, h3')?.innerText?.trim() || '',
                        author: document.querySelector('.nick, .nick_box')?.innerText?.trim() || '',
                        date: document.querySelector('.date, .article_info .time')?.innerText?.trim() || '',
                        body: (document.querySelector('.se-main-container, .ContentRenderer, .post_ct, .article_viewer')?.innerText || '').substring(0, 5000),
                        comment_count: document.querySelectorAll('.comment_box, .CommentItem').length,
                    })
                    """)
                except Exception:  # noqa: BLE001 - 네이버 카페 읽기전용 조회(NaverCafe: open_my_cafes/list_posts/read_post) — 각 except는 빈 리스트 또는 오류 dict를 반환하며, 실제 글쓰기(write_post)는 별도 writer 모듈에 위임되어 이 파일에 포함되지 않음.
                    continue
        return {"error": "iframe_not_found"}

    def write_post(  # noqa: PLR0913 - 공개 시그니처 유지(동작 변경 금지 리팩터링)
        self,
        cafe_url: str,
        board_name: str,
        title: str,
        body: str,
        tags: list[str] | None = None,
        members_only: bool = False,
        require_approval: bool = True,
    ) -> dict:
        """카페 글쓰기 (새 writer 위임)."""
        return write_post(
            self.page,
            cafe_url=cafe_url,
            board_name=board_name,
            title=title,
            body=body,
            tags=tags,
            members_only=members_only,
            require_approval=require_approval,
        )


__all__ = [  # noqa: RUF022
    # 수집
    "collect_articles",
    "get_my_cafes",
    "save_my_cafes",
    # 분석
    "run_pipeline",
    "organize",
    "prepare_posts_for_review",
    # 글쓰기
    "write_post",
    "confirm_publish",
    # 게시판 관리
    "list_boards",
    "add_board",
    "BOARD_TYPES",
    # 클래스 (하위 호환)
    "NaverCafe",
]

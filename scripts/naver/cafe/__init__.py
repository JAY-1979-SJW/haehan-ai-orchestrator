"""네이버 카페 자동화 패키지.

NaverCafe 클래스: 기존 scripts/naver/cafe.py와 동일한 인터페이스 (패키지 전환 호환).
write_post / confirm_publish: 새 글쓰기 자동화 (승인 게이트 포함).
"""
from __future__ import annotations

import time
from typing import Any

from playwright.sync_api import Page

from scripts.logger import get_logger
from scripts.critical_logger import log_critical
from scripts.popup_detector import handle_page_popups
from scripts.naver.auth import ensure_naver_login

from .writer import write_post, confirm_publish

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
        try:
            handle_page_popups(self.page, timeout_s=1.5)
        except Exception:
            pass
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
        except Exception as e:
            _log.error("[naver-cafe] open_my_cafes 실패: %s", e)
            return []

    def list_posts(self, cafe_url: str, board_no: int | str = "", limit: int = 30) -> list[dict]:
        if not self._ensure_login():
            return []
        url = cafe_url if not board_no else f"{cafe_url}?iframe_url=/ArticleList.nhn?search.clubid=&search.menuid={board_no}"
        self.page.goto(url, timeout=20000, wait_until="domcontentloaded")
        time.sleep(2.5)
        for f in self.page.frames:
            if "ArticleList" in f.url or "cafe.naver.com" in f.url:
                try:
                    posts = f.evaluate("""
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
                    """, limit)
                    if posts:
                        return posts
                except Exception:
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
                except Exception:
                    continue
        return {"error": "iframe_not_found"}

    def write_post(self, cafe_url: str, board_name: str, title: str, body: str,
                   tags: list[str] | None = None, members_only: bool = False,
                   require_approval: bool = True) -> dict:
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


__all__ = ["NaverCafe", "write_post", "confirm_publish"]

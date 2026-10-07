"""네이버 카페 자동화 — 글/댓글/조회.

사용:
  from scripts.naver.cafe import NaverCafe
  from scripts.browser.cdp.connection import get_page

  c = NaverCafe(get_page())
  c.open_my_cafes()                # 내 카페 목록
  c.list_posts(cafe_url=, board_no=)  # 게시판 글 목록
  c.read_post(post_url=)
  c.write_post(cafe_url=, title=, body=, send=False)  # 임시저장 기본
"""

from __future__ import annotations

import contextlib
import time

from playwright.sync_api import Page

from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger
from scripts.naver.common.auth import ensure_naver_login
from scripts.browser.popup.popup_detector import handle_page_popups

_log = get_logger(__name__)

MY_CAFES_URL = "https://section.cafe.naver.com/ca-fe/home/recent-articles"


class NaverCafe:
    def __init__(self, page: Page):
        self.page = page

    def _ensure_login(self) -> bool:
        result = ensure_naver_login(self.page)
        return bool(result.get("ok"))

    def open_my_cafes(self) -> list[dict]:
        """내가 가입한 카페 목록."""
        if not self._ensure_login():
            return []
        self.page.goto(MY_CAFES_URL, timeout=20000, wait_until="domcontentloaded")
        time.sleep(2.5)
        with contextlib.suppress(Exception):
            handle_page_popups(self.page, timeout_s=1.5)
        try:
            cafes = self.page.evaluate("""
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
                    if (name && name.length >= 2) {
                        out.push({cafe_id, name, url: 'https://cafe.naver.com/' + cafe_id});
                    }
                });
                return out;
            }
            """)
            _log.info("[naver-cafe] 내 카페 %d개", len(cafes))
            return cafes
        except Exception as e:  # noqa: BLE001 - 네이버 카페 CDP 자동화(목록/읽기/쓰기) - 실패 시 빈 목록 또는 ok:False 반환, 성공으로 위장하지 않음
            _log.error("[naver-cafe] open_my_cafes 실패: %s", e)
            return []

    def list_posts(self, cafe_url: str, board_no: int | str = "", limit: int = 30) -> list[dict]:
        """카페 게시판 글 목록."""
        if not self._ensure_login():
            return []
        url = (
            cafe_url
            if not board_no
            else f"{cafe_url}?iframe_url=/ArticleList.nhn?search.clubid=&search.menuid={board_no}"
        )
        self.page.goto(url, timeout=20000, wait_until="domcontentloaded")
        time.sleep(2.5)

        # 카페 iframe 진입
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
                except Exception:  # noqa: BLE001 - 네이버 카페 CDP 자동화(목록/읽기/쓰기) - 실패 시 빈 목록 또는 ok:False 반환, 성공으로 위장하지 않음
                    continue
        return []

    def read_post(self, post_url: str) -> dict:
        """카페 글 본문."""
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
                except Exception:  # noqa: BLE001 - 네이버 카페 CDP 자동화(목록/읽기/쓰기) - 실패 시 빈 목록 또는 ok:False 반환, 성공으로 위장하지 않음
                    continue
        return {"error": "iframe_not_found"}

    def write_post(self, cafe_url: str, board_no: int | str, title: str, body: str, send: bool = False) -> dict:
        """카페 글쓰기. send=False (기본): 임시저장만. send=True: 사용자 명시 시 발행."""
        if not self._ensure_login():
            return {"ok": False, "error": "login_failed"}

        # 글쓰기 페이지 진입
        write_url = f"{cafe_url}?iframe_url=/ArticleWrite.nhn?m=write&clubid=&menuid={board_no}"
        self.page.goto(write_url, timeout=20000, wait_until="domcontentloaded")
        time.sleep(3)

        # 카페 글쓰기 에디터 frame
        for f in self.page.frames:
            if "ArticleWrite" in f.url:
                try:
                    # 제목
                    f.locator('input[name="subject"], .input_text').first.fill(title, timeout=3000)
                    time.sleep(0.5)
                    # 본문 에디터 (SmartEditor)
                    body_el = f.locator('.se-text-paragraph, [contenteditable="true"]').first
                    body_el.click(timeout=3000)
                    time.sleep(0.3)
                    self.page.keyboard.type(body, delay=15)
                    time.sleep(0.5)

                    if send:
                        f.locator('button:has-text("등록"), .btn_register, .btn_publish').first.click(timeout=3000)
                        time.sleep(3)
                        log_critical("OTHER", f"카페 글 발행: {title[:30]}", cafe=cafe_url, mode="cafe_publish")
                        return {"ok": True, "mode": "published"}
                    else:
                        # 임시저장
                        with contextlib.suppress(Exception):
                            f.locator('button:has-text("임시저장"), .btn_temp').first.click(timeout=3000)
                        time.sleep(2)
                        return {"ok": True, "mode": "draft"}
                except Exception as e:  # noqa: BLE001 - 네이버 카페 CDP 자동화(목록/읽기/쓰기) - 실패 시 빈 목록 또는 ok:False 반환, 성공으로 위장하지 않음
                    return {"ok": False, "error": str(e)}
        return {"ok": False, "error": "write_iframe_not_found"}

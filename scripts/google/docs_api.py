"""Google Docs OOP 인터페이스.

사용:
    docs = DocsAPI(page)
    docs.new(title="회의록", content="...")
    docs.recent(limit=20)
    docs.append_text(doc_url, "추가 내용")
    docs.get_text(doc_url)
"""

from __future__ import annotations

import time

from playwright.sync_api import Page

from scripts.critical_logger import log_critical
from scripts.logger import get_logger

_log = get_logger(__name__)


class DocsAPI:
    """Google Docs 자동화."""

    DOCS_HOME = "https://docs.google.com/document/u/0/"

    def __init__(self, page: Page):
        self.page = page

    def recent(self, limit: int = 20) -> list[dict]:
        """최근 문서."""
        self.page.goto(self.DOCS_HOME, timeout=20000)
        time.sleep(3)
        try:
            return (
                self.page.evaluate(
                    """(limit) => {
                    const out = [];
                    document.querySelectorAll('[data-id]').forEach(el => {
                        if (out.length >= limit) return;
                        const name = el.querySelector('[data-tooltip], .docs-homescreen-list-item-title')?.innerText
                                    || (el.innerText || '').split('\\n')[0];
                        const id = el.getAttribute('data-id') || '';
                        if (name) out.push({name: name.substring(0, 80), id,
                                            url: `https://docs.google.com/document/d/${id}/edit`});
                    });
                    return out;
                }""",
                    limit,
                )
                or []
            )
        except Exception:
            return []

    def new(self, title: str = "", content: str = "") -> dict:
        """새 문서 생성 + 내용 입력."""
        self.page.goto("https://docs.google.com/document/create", timeout=20000)
        time.sleep(4)  # 에디터 로드
        url_after = self.page.url
        try:
            if title:
                # 제목 영역 클릭
                title_el = self.page.locator('input.docs-title-input, [aria-label*="제목"]').first
                title_el.click(timeout=3000)
                self.page.keyboard.press("Control+a")
                self.page.keyboard.type(title, delay=20)
                self.page.keyboard.press("Tab")
                time.sleep(1)

            if content:
                # 본문 영역 클릭
                self.page.locator('.kix-appview-editor, [contenteditable="true"]').first.click(timeout=3000)
                time.sleep(0.5)
                self.page.keyboard.type(content, delay=10)
                time.sleep(2)

            log_critical("OTHER", f"Docs 새 문서: {title[:30]}", url=url_after, mode="docs_new")
            return {"ok": True, "title": title, "url": url_after, "content_len": len(content)}
        except Exception as e:
            return {"ok": False, "error": str(e)[:100], "url": url_after}

    def open_doc(self, url: str) -> dict:
        """문서 열기."""
        self.page.goto(url, timeout=20000)
        time.sleep(3)
        return {"ok": True, "url": url}

    def append_text(self, url: str, text: str) -> dict:
        """문서 끝에 텍스트 추가."""
        self.open_doc(url)
        try:
            self.page.locator('.kix-appview-editor, [contenteditable="true"]').first.click(timeout=3000)
            time.sleep(0.5)
            self.page.keyboard.press("Control+End")
            time.sleep(0.3)
            self.page.keyboard.press("Enter")
            self.page.keyboard.type(text, delay=10)
            time.sleep(1.5)
            log_critical("OTHER", f"Docs 텍스트 추가: {len(text)}자", mode="docs_append")
            return {"ok": True, "appended": len(text)}
        except Exception as e:
            return {"ok": False, "error": str(e)[:100]}

    def get_text(self, url: str) -> dict:
        """문서 본문 추출."""
        self.open_doc(url)
        try:
            text = self.page.evaluate(
                """() => (document.querySelector('.kix-appview-editor')?.innerText
                          || document.body?.innerText || '').substring(0, 50000)"""
            )
            return {"ok": True, "text": text, "len": len(text)}
        except Exception as e:
            return {"ok": False, "error": str(e)[:100]}

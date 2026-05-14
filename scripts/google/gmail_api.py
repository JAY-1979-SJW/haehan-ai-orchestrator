"""Gmail OOP 인터페이스 (기존 gmail.py task 함수 보존).

기존 `gmail.run("compose", [...])` CLI 스타일에 추가로,
Python 코드에서 직접 호출할 수 있는 클래스 제공.

사용:
    from scripts.google.gmail_api import GmailAPI
    from scripts.web_connector import get_page
    g = GmailAPI(get_page())
    g.send(to="x@y.com", subject="안녕", body="내용")
    g.list_inbox(limit=20)
    g.read(0)
    g.reply(0, "답장 내용")
    g.mark_read(0)
    g.label(0, "중요")
    g.search("from:naver.com")
"""
from __future__ import annotations

import time
from typing import Any

from playwright.sync_api import Page

from scripts.logger import get_logger
from scripts.critical_logger import log_critical
from scripts.config import GOOGLE_URLS

_log = get_logger(__name__)


class GmailAPI:
    """Gmail 웹 UI 자동화 (CDP 기반)."""

    def __init__(self, page: Page):
        self.page = page

    # ── 목록/탐색 ────────────────────────────────────────────────────

    def list_inbox(self, limit: int = 20, folder: str = "inbox") -> list[dict]:
        """받은편지함 목록."""
        url_map = {
            "inbox": GOOGLE_URLS["gmail_inbox"],
            "sent": GOOGLE_URLS["gmail_sent"],
            "drafts": GOOGLE_URLS["gmail_drafts"],
            "archive": GOOGLE_URLS["gmail_archive"],
            "trash": GOOGLE_URLS["gmail_trash"],
        }
        self.page.goto(url_map.get(folder, url_map["inbox"]), timeout=20000)
        time.sleep(2.5)
        rows = self.page.evaluate(
            r"""(limit) => {
                const out = [];
                for (const el of document.querySelectorAll('[role="listitem"]')) {
                    if (out.length >= limit) break;
                    const from = el.querySelector('[data-senders]')?.getAttribute('data-senders') || '';
                    const subject = el.querySelector('[data-subject]')?.getAttribute('data-subject') || '';
                    const date = el.querySelector('[data-date-time]')?.getAttribute('data-date-time') || '';
                    const unread = el.classList.contains('zE') || !!el.querySelector('.zE');
                    if (from || subject) out.push({from, subject, date, unread});
                }
                return out;
            }""",
            limit,
        )
        _log.info("[gmail] %s 목록 %d개", folder, len(rows))
        return rows

    def search(self, query: str, limit: int = 20) -> list[dict]:
        """검색 + 결과 목록 반환."""
        self.page.goto(GOOGLE_URLS["gmail_home"], timeout=20000)
        time.sleep(2)
        try:
            box = self.page.locator('input[placeholder*="Search"], input[aria-label*="검색"]').first
            box.click(timeout=3000)
            box.fill(query, timeout=3000)
            self.page.keyboard.press("Enter")
            time.sleep(3)
        except Exception as e:
            _log.error("[gmail] 검색 실패: %s", e)
            return []
        return self.list_inbox(limit=limit, folder="inbox")  # 같은 셀렉터로 결과 파싱

    # ── 발송/답장 ────────────────────────────────────────────────────

    def send(self, *, to: str, subject: str, body: str,
             cc: str | None = None, bcc: str | None = None) -> dict:
        """새 메일 발송."""
        self.page.goto(GOOGLE_URLS["gmail_home"], timeout=20000)
        time.sleep(2.5)
        try:
            # JS로 "편지쓰기" 버튼 찾기 (has-text selector 대체)
            compose_clicked = self.page.evaluate("""
            () => {
                for (const btn of document.querySelectorAll('div[role="button"], button')) {
                    const txt = (btn.innerText || '').trim();
                    if (txt === '편지쓰기' || txt === 'Compose') {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }
            """)
            if not compose_clicked:
                raise RuntimeError("'편지쓰기' 버튼 못 찾음")
            time.sleep(2)

            to_input = self.page.locator(
                'input[aria-label*="To"], input[aria-label*="받는사람"], textarea[name="to"]'
            ).first
            to_input.click(timeout=3000)
            self.page.keyboard.type(to, delay=20)
            self.page.keyboard.press("Tab")
            time.sleep(0.5)

            if cc:
                # Cc 열기
                try:
                    self.page.locator('span:has-text("Cc"), span:has-text("참조")').first.click(timeout=1500)
                    self.page.locator('input[aria-label*="Cc"], input[aria-label*="참조"]').first.fill(cc, timeout=2000)
                except Exception:
                    pass

            if bcc:
                try:
                    self.page.locator('span:has-text("Bcc"), span:has-text("숨은참조")').first.click(timeout=1500)
                    self.page.locator('input[aria-label*="Bcc"], input[aria-label*="숨은참조"]').first.fill(bcc, timeout=2000)
                except Exception:
                    pass

            subj = self.page.locator('input[aria-label*="Subject"], input[name="subjectbox"]').first
            subj.fill(subject, timeout=3000)
            time.sleep(0.3)

            self.page.evaluate(
                """(text) => {
                    const ed = document.querySelector('div[contenteditable="true"][aria-label*="Message"], div[contenteditable="true"]');
                    if (ed) {
                        ed.focus();
                        ed.innerHTML = text.replace(/\\n/g, '<br>');
                        ed.dispatchEvent(new Event('input', {bubbles: true}));
                    }
                }""",
                body,
            )
            time.sleep(0.5)

            send_btn = self.page.locator(
                'div[role="button"][aria-label*="Send"], div[role="button"][aria-label*="보내기"]'
            ).first
            send_btn.click(timeout=5000)
            time.sleep(2.5)
            log_critical("MAIL_SEND", f"Gmail 발송: {to}", subject=subject[:50], mode="gmail_send")
            return {"ok": True, "to": to, "subject": subject}
        except Exception as e:
            _log.error("[gmail] 발송 실패: %s", e)
            return {"ok": False, "error": str(e)[:100]}

    def reply(self, mail_index: int, body: str, reply_all: bool = False) -> dict:
        """N번째 메일에 답장."""
        self.list_inbox(limit=max(mail_index + 1, 10))
        try:
            items = self.page.locator('[role="listitem"]')
            items.nth(mail_index).click(timeout=5000)
            time.sleep(2)
            btn_label = "전체답장" if reply_all else "답장"
            self.page.locator(
                f'div[role="button"]:has-text("{btn_label}"), div[role="button"][aria-label*="Reply"]'
            ).first.click(timeout=4000)
            time.sleep(1.5)
            self.page.evaluate(
                """(text) => {
                    const ed = document.querySelector('div[contenteditable="true"]');
                    if (ed) { ed.focus(); ed.innerHTML = text.replace(/\\n/g, '<br>');
                              ed.dispatchEvent(new Event('input', {bubbles: true})); }
                }""",
                body,
            )
            time.sleep(0.5)
            self.page.locator(
                'div[role="button"][aria-label*="Send"], div[role="button"][aria-label*="보내기"]'
            ).first.click(timeout=4000)
            time.sleep(2)
            log_critical("MAIL_SEND", f"Gmail 답장: idx={mail_index}", mode="gmail_reply")
            return {"ok": True, "mail_index": mail_index}
        except Exception as e:
            return {"ok": False, "error": str(e)[:100]}

    # ── 읽기/상태 변경 ───────────────────────────────────────────────

    def read(self, mail_index: int) -> dict:
        """N번째 메일 열어서 본문 추출."""
        self.list_inbox(limit=max(mail_index + 1, 10))
        try:
            items = self.page.locator('[role="listitem"]')
            items.nth(mail_index).click(timeout=5000)
            time.sleep(2.5)
            data = self.page.evaluate(
                """() => {
                    const subj = document.querySelector('h2[data-thread-perm-id], h2.hP')?.innerText || '';
                    const from_el = document.querySelector('[email], .gD');
                    const sender = from_el?.getAttribute('email') || from_el?.innerText || '';
                    const body = document.querySelector('[role="article"] [dir="ltr"], .a3s')?.innerText || '';
                    return {subject: subj, sender, body: body.substring(0, 4000)};
                }"""
            )
            return {"ok": True, **data}
        except Exception as e:
            return {"ok": False, "error": str(e)[:100]}

    def mark_read(self, mail_index: int) -> dict:
        """읽음 표시."""
        try:
            self.list_inbox(limit=max(mail_index + 1, 10))
            items = self.page.locator('[role="listitem"]')
            items.nth(mail_index).click(timeout=5000)
            time.sleep(1.5)
            # 메일 열면 자동으로 읽음
            self.page.goto(GOOGLE_URLS["gmail_inbox"], timeout=10000)
            return {"ok": True, "mail_index": mail_index}
        except Exception as e:
            return {"ok": False, "error": str(e)[:100]}

    def star(self, mail_index: int) -> dict:
        """별표."""
        try:
            self.list_inbox(limit=max(mail_index + 1, 10))
            items = self.page.locator('[role="listitem"]')
            it = items.nth(mail_index)
            it.locator('span[role="checkbox"][aria-label*="Star"], .T-KT').first.click(timeout=3000)
            return {"ok": True, "mail_index": mail_index}
        except Exception as e:
            return {"ok": False, "error": str(e)[:100]}

    def delete(self, mail_index: int) -> dict:
        """N번째 메일 삭제."""
        try:
            self.list_inbox(limit=max(mail_index + 1, 10))
            items = self.page.locator('[role="listitem"]')
            items.nth(mail_index).click(timeout=5000)
            time.sleep(1.5)
            self.page.locator(
                'div[role="button"][aria-label*="Delete"], div[role="button"][aria-label*="삭제"]'
            ).first.click(timeout=4000)
            time.sleep(1.5)
            log_critical("OTHER", f"Gmail 삭제: idx={mail_index}", mode="gmail_delete")
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)[:100]}

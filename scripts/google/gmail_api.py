"""Safe Gmail browser adapter.

This adapter keeps the legacy public methods but does not click final Send or
Delete controls. Gmail writes must flow through the Google work approval path
and remain no-final-submit until a separate approved final action exists.
"""
from __future__ import annotations

import time
from typing import Any

from playwright.sync_api import Page

from scripts.config import GOOGLE_URLS
from scripts.logger import get_logger

_log = get_logger(__name__)


class GmailAPI:
    """Gmail UI helper for user-present CDP sessions."""

    def __init__(self, page: Page):
        self.page = page

    def list_inbox(self, limit: int = 20, folder: str = "inbox") -> list[dict[str, Any]]:
        """Return a redacted list of visible messages from a Gmail folder."""
        url_map = {
            "inbox": GOOGLE_URLS["gmail_inbox"],
            "sent": GOOGLE_URLS["gmail_sent"],
            "drafts": GOOGLE_URLS["gmail_drafts"],
            "archive": GOOGLE_URLS["gmail_archive"],
            "trash": GOOGLE_URLS["gmail_trash"],
        }
        self.page.goto(url_map.get(folder, url_map["inbox"]), timeout=20000)
        time.sleep(3.0)
        rows = self.page.evaluate(
            r"""(limit) => {
                const out = [];
                for (const row of document.querySelectorAll('tr.zA, [role="listitem"]')) {
                    if (out.length >= limit) break;
                    const fromEl = row.querySelector('.yW span[email], .yW span[name], .zF, [data-senders]');
                    const subjectEl = row.querySelector('.y6 span:not(.T3), [data-subject]');
                    const dateEl = row.querySelector('.xW span, td.xW, [data-date-time]');
                    const from = fromEl?.getAttribute('name') || fromEl?.getAttribute('data-senders') || fromEl?.innerText || '';
                    const subject = subjectEl?.getAttribute('data-subject') || subjectEl?.innerText || '';
                    const date = dateEl?.getAttribute('title') || dateEl?.getAttribute('data-date-time') || dateEl?.innerText || '';
                    const unread = row.classList.contains('zE');
                    if (from || subject) {
                        out.push({
                            from_preview: from.trim().slice(0, 80),
                            subject_preview: subject.trim().slice(0, 120),
                            date: date.trim().slice(0, 80),
                            unread,
                            index: out.length
                        });
                    }
                }
                return out;
            }""",
            limit,
        )
        _log.info("[gmail] listed folder=%s count=%d", folder, len(rows))
        return rows

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search Gmail and return visible result previews."""
        self.page.goto(GOOGLE_URLS["gmail_home"], timeout=20000)
        time.sleep(2.0)
        try:
            box = self.page.locator(
                'input[name="q"], input[placeholder*="Search"], input[placeholder*="검색"], '
                'input[aria-label*="Search"], input[aria-label*="search"], input[aria-label*="검색"], '
                'input[type="search"], input[type="text"][role="combobox"]'
            ).first
            box.click(timeout=3000)
            box.fill(query, timeout=3000)
            self.page.keyboard.press("Enter")
            time.sleep(3.0)
        except Exception as exc:
            _log.error("[gmail] search failed: %s", exc)
            return []
        return self.list_inbox(limit=limit, folder="inbox")

    def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        cc: str | None = None,
        bcc: str | None = None,
    ) -> dict[str, Any]:
        """Fill a Gmail compose draft only. Final Send is never clicked."""
        self.page.goto(GOOGLE_URLS["gmail_home"], timeout=20000)
        time.sleep(2.5)
        try:
            self._open_compose()
            self._fill_recipient("to", to)
            if cc:
                self._fill_optional_recipient("Cc", cc)
            if bcc:
                self._fill_optional_recipient("Bcc", bcc)
            self._fill_subject(subject)
            self._fill_body(body)
            return {
                "ok": True,
                "mode": "draft_only_no_final_submit",
                "final_send_clicked": False,
                "fields_filled": ["to", "subject", "body"],
            }
        except Exception as exc:
            _log.error("[gmail] draft fill failed: %s", exc)
            return {"ok": False, "error": str(exc)[:100]}

    def reply(self, mail_index: int, body: str, reply_all: bool = False) -> dict[str, Any]:
        """Fill a reply draft only. Final Send is never clicked."""
        self.list_inbox(limit=max(mail_index + 1, 10))
        try:
            self.page.locator('tr.zA, [role="listitem"]').nth(mail_index).click(timeout=5000)
            time.sleep(2.0)
            labels = ["Reply all", "Reply"] if reply_all else ["Reply"]
            self._click_by_text(labels)
            time.sleep(1.0)
            self._fill_body(body)
            return {
                "ok": True,
                "mode": "reply_draft_only_no_final_submit",
                "final_send_clicked": False,
                "mail_index": mail_index,
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:100]}

    def read(self, mail_index: int) -> dict[str, Any]:
        """Open a visible message and return a redacted body preview."""
        self.list_inbox(limit=max(mail_index + 1, 10))
        try:
            self.page.locator('tr.zA, [role="listitem"]').nth(mail_index).click(timeout=5000)
            time.sleep(2.5)
            data = self.page.evaluate(
                """() => {
                    const subj = document.querySelector('h2[data-thread-perm-id], h2.hP')?.innerText || '';
                    const sender = document.querySelector('[email], .gD')?.innerText || '';
                    const body = document.querySelector('[role="article"] [dir="ltr"], .a3s')?.innerText || '';
                    return {
                        subject_preview: subj.slice(0, 120),
                        sender_preview: sender.slice(0, 80),
                        body_preview: body.slice(0, 1000)
                    };
                }"""
            )
            return {"ok": True, **data}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:100]}

    def mark_read(self, mail_index: int) -> dict[str, Any]:
        """Open a message, which may mark it read in Gmail."""
        self.list_inbox(limit=max(mail_index + 1, 10))
        try:
            self.page.locator('tr.zA, [role="listitem"]').nth(mail_index).click(timeout=5000)
            time.sleep(1.5)
            self.page.goto(GOOGLE_URLS["gmail_inbox"], timeout=10000)
            return {"ok": True, "mail_index": mail_index, "state_change": "gmail_may_mark_read"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:100]}

    def star(self, mail_index: int) -> dict[str, Any]:
        """Block starring until a dedicated approval-gated action is added."""
        return {
            "ok": False,
            "mode": "blocked",
            "reason": "gmail_star_requires_user_final_approval",
            "mail_index": mail_index,
        }

    def delete(self, mail_index: int) -> dict[str, Any]:
        """Block deletion until a dedicated approval-gated action is added."""
        return {
            "ok": False,
            "mode": "blocked",
            "reason": "gmail_delete_requires_user_final_approval",
            "mail_index": mail_index,
        }

    def _open_compose(self) -> None:
        if self._compose_visible():
            return
        self._click_by_text(["Compose"])
        time.sleep(1.5)
        if not self._compose_visible():
            self.page.locator('div[role="button"][gh="cm"], div[aria-label*="Compose"]').first.click(timeout=4000)
            time.sleep(1.5)

    def _compose_visible(self) -> bool:
        selectors = ['input[name="subjectbox"]', 'textarea[name="to"]', 'div[contenteditable="true"]']
        for selector in selectors:
            try:
                if self.page.locator(selector).first.bounding_box(timeout=500) is not None:
                    return True
            except Exception:
                continue
        return False

    def _fill_recipient(self, field: str, value: str) -> None:
        if not value:
            return
        selector = (
            'textarea[name="to"], div[name="to"] input[type="text"], '
            'input[aria-label*="To"], input[aria-label*="Recipient"]'
        )
        target = self.page.locator(selector).first
        target.click(timeout=4000)
        self.page.keyboard.type(value, delay=10)
        self.page.keyboard.press("Enter")

    def _fill_optional_recipient(self, label: str, value: str) -> None:
        try:
            self._click_by_text([label])
            self._fill_recipient(label.lower(), value)
        except Exception:
            _log.warning("[gmail] optional recipient field skipped: %s", label)

    def _fill_subject(self, value: str) -> None:
        self.page.locator('input[name="subjectbox"], input[aria-label*="Subject"]').first.fill(value, timeout=4000)

    def _fill_body(self, value: str) -> None:
        target = self.page.locator('div[contenteditable="true"][role="textbox"], div[contenteditable="true"]').last
        target.click(timeout=4000)
        self.page.keyboard.type(value, delay=5)

    def _click_by_text(self, labels: list[str]) -> None:
        last_error: Exception | None = None
        for label in labels:
            try:
                self.page.get_by_text(label, exact=False).first.click(timeout=3000)
                return
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"Gmail control not found: {'/'.join(labels)}") from last_error

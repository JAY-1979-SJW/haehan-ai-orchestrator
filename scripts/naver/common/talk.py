"""네이버 톡톡 자동화 — 메시지 조회 / 답장.

URL: https://talk.naver.com/
"""

from __future__ import annotations

import time

from playwright.sync_api import Page

from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger
from scripts.naver.common.auth import open_logged_in_page

_log = get_logger(__name__)
TALK_URL = "https://talk.naver.com/"
TALK_SEND_CONFIRM_TEXT = "NAVER_APPROVED_SEND"


class NaverTalk:
    def __init__(self, page: Page):
        self.page = page

    def open(self) -> bool:
        return open_logged_in_page(self.page, TALK_URL)

    def list_chats(self, limit: int = 30) -> list[dict]:
        """대화 목록."""
        if not self.open():
            return []
        try:
            chats = self.page.evaluate(
                """
            (limit) => {
                const out = [];
                document.querySelectorAll('[class*="ChatList"] li, .chat_list li, .talk-item').forEach((el, i) => {
                    if (i >= limit) return;
                    const partner = el.querySelector('.name, .partner, [class*="name"]')?.innerText?.trim() || '';
                    const last_msg = el.querySelector('.message, .preview, [class*="preview"]')?.innerText?.trim() || '';
                    const time_el = el.querySelector('.time, .date')?.innerText?.trim() || '';
                    const unread = el.querySelector('.badge, .unread, [class*="unread"]') !== null;
                    if (partner) out.push({partner, last_message: last_msg, time: time_el, unread});
                });
                return out;
            }
            """,
                limit,
            )
            return chats
        except Exception as e:  # noqa: BLE001 - 네이버 톡톡 채팅 목록조회/메시지전송 자동화 — 팝업처리 실패 무시, 목록조회/전송 실패는 ok=False 에러 결과 반환할 뿐 세션 파기나 삭제 없음
            _log.error("[naver-talk] list_chats 실패: %s", e)
            return []

    def send_message(
        self,
        partner_name: str,
        message: str,
        confirm: bool = False,
        approval_confirm: str = "",
    ) -> dict:
        """메시지 발송. confirm=False 시 입력만, True 시 승인 확인 후 발송."""
        if not self.open():
            return {"ok": False, "error": "open_failed"}
        try:
            self.page.get_by_text(partner_name, exact=False).first.click(timeout=5000)
            time.sleep(2)
            self.page.locator('[contenteditable="true"], textarea').first.fill(message, timeout=3000)
            time.sleep(0.5)
            if confirm:
                if approval_confirm != TALK_SEND_CONFIRM_TEXT:
                    return {
                        "ok": False,
                        "mode": "filled_not_sent",
                        "error": "approval_required",
                        "requires": ["--approved", f"--confirm={TALK_SEND_CONFIRM_TEXT}"],
                    }
                self.page.locator('button:has-text("전송"), .btn_send').first.click(timeout=3000)
                time.sleep(2)
                log_critical("OTHER", f"네이버 톡톡 발송: {partner_name}", partner=partner_name, mode="talk_send")
                return {"ok": True, "mode": "sent"}
            return {"ok": True, "mode": "filled_not_sent"}
        except Exception as e:  # noqa: BLE001 - 네이버 톡톡 채팅 목록조회/메시지전송 자동화 — 팝업처리 실패 무시, 목록조회/전송 실패는 ok=False 에러 결과 반환할 뿐 세션 파기나 삭제 없음
            return {"ok": False, "error": str(e)}

"""메일 고급 자동화 — 자동 답장 / 첨부 다운로드 / 일괄 정리.

기본 NaverMail 위에 구축.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from playwright.sync_api import Page

from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger

_log = get_logger(__name__)


class MailAutomation:
    """메일 자동 처리 — 규칙 기반 답장, 첨부 자동 다운로드, 일괄 분류."""

    def __init__(self, page: Page):
        self.page = page
        from scripts.naver.mail import (  # type: ignore[attr-defined]  # 실제 없음(2026-09-29 defect_index #39 확인, #37/#38 과 동일 계열) — 이 클래스 자체가 코드맵상 완전 UNREACHED(어디서도 인스턴스화 안 됨), 저우선순위로 보류
            NaverMail,
        )

        self.mail = NaverMail(page)

    # ── 자동 답장 ──────────────────────────────────────────────────────

    def auto_reply(self, rules: list[dict], dry_run: bool = True) -> dict:
        """규칙 기반 자동 답장.

        rules: [
            {"sender_pattern": "vendor@", "subject_pattern": "주문 확인",
             "template": "안녕하세요, 주문 확인되었습니다."},
        ]
        dry_run=True: 답장 발송 안 함, 매칭 건수만 보고
        """
        inbox = self.mail.list_inbox(limit=50)
        matched = []
        for mail in inbox:
            for rule in rules:
                sender_ok = not rule.get("sender_pattern") or re.search(
                    rule["sender_pattern"], mail.get("sender", ""), re.I
                )
                subject_ok = not rule.get("subject_pattern") or re.search(
                    rule["subject_pattern"], mail.get("subject", ""), re.I
                )
                if sender_ok and subject_ok:
                    matched.append({"mail": mail, "rule": rule})
                    break

        _log.info("[mail-auto] %d개 매칭", len(matched))
        if dry_run:
            return {"ok": True, "dry_run": True, "matched": len(matched), "items": matched}

        sent = 0
        for m in matched:
            r = self.mail.compose(
                to=m["mail"]["sender"],
                subject=f"RE: {m['mail']['subject']}",
                body=m["rule"]["template"],
                send=True,
            )
            if r.get("ok"):
                sent += 1
                log_critical(
                    "MAIL_SEND",
                    f"자동 답장: {m['mail']['subject'][:30]}",
                    to=m["mail"]["sender"],
                    rule=m["rule"].get("template", "")[:50],
                )
            time.sleep(2)
        return {"ok": True, "matched": len(matched), "sent": sent}

    # ── 첨부파일 자동 다운로드 ────────────────────────────────────────

    def download_attachments(self, save_dir: str, sender_filter: str | None = None, days: int = 30) -> dict:
        """받은편지함의 첨부파일 자동 다운로드.

        save_dir: 저장 폴더
        sender_filter: 발신자 필터 (정규식)
        days: 최근 N일 메일만
        """
        save_path = Path(save_dir)
        save_path.mkdir(parents=True, exist_ok=True)

        if not self.mail.open():
            return {"ok": False, "error": "open_failed"}

        # 첨부 있는 메일 추출
        attachment_mails = self.page.evaluate("""
        () => {
            const rows = document.querySelectorAll('[role="listitem"], .mail_list li, tbody tr');
            const out = [];
            rows.forEach(row => {
                const hasAttach = row.querySelector('[class*="attach"], .icon_attach');
                if (!hasAttach) return;
                const sender = row.querySelector('.from, .sender')?.innerText?.trim() || '';
                const subject = row.querySelector('.subject, [class*="subject"]')?.innerText?.trim() || '';
                const date = row.querySelector('.date, .time')?.innerText?.trim() || '';
                out.push({sender, subject, date});
            });
            return out;
        }
        """)

        if sender_filter:
            attachment_mails = [m for m in attachment_mails if re.search(sender_filter, m.get("sender", ""), re.I)]

        _log.info("[mail-auto] 첨부 메일 %d개", len(attachment_mails))
        return {
            "ok": True,
            "candidates": len(attachment_mails),
            "items": attachment_mails,
            "note": "실제 다운로드는 메일별 진입 + 다운로드 버튼 클릭 필요 (개별 구현)",
        }

    # ── 일괄 분류 / 라벨 ──────────────────────────────────────────────

    def bulk_label(self, sender_filter: str, label: str) -> dict:
        """발신자 필터 기준 메일 일괄 라벨링 (UI 분석 후 보강 필요)."""
        return {"ok": False, "note": "네이버 메일 라벨 UI 상세 구현 필요"}

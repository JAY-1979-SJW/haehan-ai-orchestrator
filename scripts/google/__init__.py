"""Google 서비스 통합 진입점 (Blog 패키지와 동일 패턴).

OOP 클래스는 별도 *_api.py 모듈에. 기존 task 함수형 모듈은 보존.

사용:
    from scripts.google import Google
    from scripts.web_connector import get_page

    g = Google(get_page())
    g.login()                      # ID/PW 자동 로그인
    g.gmail.send(to="x@y.com", subject="...", body="...")
    g.gmail.list_inbox(limit=10)
    g.calendar.create_event(title="...", when="2026-05-13 14:00")
    g.calendar.quick_add("내일 오후 3시 미용실")
    g.drive.upload("data/report.pdf")
    g.docs.new(title="회의록", content="...")
    g.sheets.new(title="매출")
"""
from __future__ import annotations

from playwright.sync_api import Page


class Google:
    """Google 서비스 통합 진입점."""

    def __init__(self, page: Page):
        self.page = page
        self._gmail = None
        self._calendar = None
        self._drive = None
        self._docs = None
        self._sheets = None

    # ── 인증 ──────────────────────────────────────────────────────────

    def login(self, google_id: str | None = None, google_pw: str | None = None,
              wait_for_user_s: int = 300) -> dict:
        """ID/PW 자동 로그인 + 2FA 사용자 위임."""
        from scripts.google.auth import login_google
        return login_google(self.page, google_id, google_pw, wait_for_user_s)

    def ensure_login(self, **kwargs) -> dict:
        """미로그인 시 자동 로그인 + 원래 페이지 복귀."""
        from scripts.google.auth import ensure_google_login
        return ensure_google_login(self.page, **kwargs)

    # ── 서비스 (lazy load) ────────────────────────────────────────────

    @property
    def gmail(self):
        if self._gmail is None:
            from scripts.google.gmail_api import GmailAPI
            self._gmail = GmailAPI(self.page)
        return self._gmail

    @property
    def calendar(self):
        if self._calendar is None:
            from scripts.google.calendar_api import CalendarAPI
            self._calendar = CalendarAPI(self.page)
        return self._calendar

    @property
    def drive(self):
        if self._drive is None:
            from scripts.google.drive_api import DriveAPI
            self._drive = DriveAPI(self.page)
        return self._drive

    @property
    def docs(self):
        if self._docs is None:
            from scripts.google.docs_api import DocsAPI
            self._docs = DocsAPI(self.page)
        return self._docs

    @property
    def sheets(self):
        if self._sheets is None:
            from scripts.google.sheets_api import SheetsAPI
            self._sheets = SheetsAPI(self.page)
        return self._sheets


__all__ = ["Google"]

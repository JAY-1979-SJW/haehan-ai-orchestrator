"""Google service entrypoint."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.sync_api import Page
else:
    Page = Any


class Google:
    """Convenience wrapper for Google service helpers."""

    def __init__(self, page: Page):
        self.page = page
        self._gmail = None
        self._calendar = None
        self._drive = None
        self._docs = None
        self._sheets = None

    def login(self, wait_for_user_s: int = 300) -> dict:
        """Open Google sign-in and wait for user-present login."""
        from scripts.google.auth import login_google

        return login_google(self.page, wait_for_user_s=wait_for_user_s)

    def ensure_login(self, **kwargs) -> dict:
        """Ensure a user-present Google login session."""
        from scripts.google.auth import ensure_google_login

        return ensure_google_login(self.page, **kwargs)

    @property
    def gmail(self):
        if self._gmail is None:
            from scripts.google.common.gmail_api import GmailAPI

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

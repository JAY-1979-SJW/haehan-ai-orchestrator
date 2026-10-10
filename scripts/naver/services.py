"""네이버 개인 서비스 통합 진입점(NaverServices) — 광고 제외.

scripts/naver/__init__.py 에 있던 것을 그대로 옮겼다(패키지 __init__ 은 재수출 없이 문서만).

    from scripts.naver.services import NaverServices
    from scripts.browser.cdp.connection import get_page

    n = NaverServices(get_page())
    n.login()                                  # 자동 로그인
    n.blog.write_post(title=..., body=...)     # 블로그 글
    n.cafe.open_my_cafes()                     # 내 카페
    n.calendar.add_event(title=..., start=...) # 일정
    n.mybox.upload(local_path=...)             # 파일 업로드
    n.pay.list_orders(limit=30)                # 결제내역
    n.talk.list_chats()                        # 톡톡 대화
    n.place.list_places()                      # 스마트플레이스
"""

from __future__ import annotations

from importlib import import_module

from playwright.sync_api import Page


def _load_class(module_name: str, class_name: str):
    return getattr(import_module(module_name), class_name)


class NaverServices:
    """네이버 개인 서비스 통합 진입점 (광고 제외)."""

    def __init__(self, page: Page):
        self.page = page
        self._blog = None
        self._cafe = None
        self._calendar = None
        self._mybox = None
        self._pay = None
        self._talk = None
        self._place = None
        self._smartstore = None

    def login(self, naver_id: str | None = None, naver_pw: str | None = None) -> dict:
        """네이버 자동 로그인 (자격증명 환경변수/파일/파라미터)."""
        from scripts.naver.common.auth import login_naver

        return login_naver(self.page, naver_id, naver_pw)

    def logged_in_user(self) -> str | None:
        """현재 로그인 사용자명."""
        from scripts.auth.login_detector import get_logged_in_user

        return get_logged_in_user(self.page)

    # ── 서비스별 lazy 인스턴스 ─────────────────────────────────────────

    @property
    def blog(self):
        if self._blog is None:
            from scripts.naver.blog.writer import BlogWriter

            self._blog = BlogWriter(self.page)
        return self._blog

    @property
    def cafe(self):
        if self._cafe is None:
            NaverCafe = _load_class("scripts.naver.cafe", "NaverCafe")
            self._cafe = NaverCafe(self.page)
        return self._cafe

    @property
    def calendar(self):
        if self._calendar is None:
            from scripts.naver.common.calendar_tasks import NaverCalendar

            self._calendar = NaverCalendar(self.page)
        return self._calendar

    @property
    def mybox(self):
        if self._mybox is None:
            from scripts.naver.common.mybox import NaverMyBox

            self._mybox = NaverMyBox(self.page)
        return self._mybox

    @property
    def pay(self):
        if self._pay is None:
            from scripts.naver.pay import NaverPay

            self._pay = NaverPay(self.page)
        return self._pay

    @property
    def talk(self):
        if self._talk is None:
            from scripts.naver.common.talk import NaverTalk

            self._talk = NaverTalk(self.page)
        return self._talk

    @property
    def place(self):
        if self._place is None:
            from scripts.naver.common.place import NaverPlace

            self._place = NaverPlace(self.page)
        return self._place

    @property
    def smartstore(self):
        if self._smartstore is None:
            from scripts.naver.smartstore import NaverSmartStore

            self._smartstore = NaverSmartStore(self.page)
        return self._smartstore


__all__ = ["NaverServices"]

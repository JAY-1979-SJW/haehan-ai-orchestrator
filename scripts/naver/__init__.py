"""네이버 서비스 통합 패키지.

기존 router.py / base.py / blog.py / mail.py 보존.
신규 모듈: auth / blog_writer / cafe / calendar / mybox / pay / talk / place

통합 진입점:
    from scripts.naver import NaverServices
    from scripts.web_connector import get_page

    n = NaverServices(get_page())
    n.login()                                  # 자동 로그인
    n.blog.write_post(title=..., body=...)     # 블로그 글
    n.mail.list_inbox(limit=20)                # 메일 목록
    n.cafe.open_my_cafes()                     # 내 카페
    n.calendar.add_event(title=..., start=...) # 일정
    n.mybox.upload(local_path=...)             # 파일 업로드
    n.pay.list_orders(limit=30)                # 결제내역
    n.talk.list_chats()                        # 톡톡 대화
    n.place.list_places()                      # 스마트플레이스

각 모듈은 개별 import도 가능:
    from scripts.naver.mail import NaverMail
    from scripts.naver.cafe import NaverCafe
    ...
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
        self._mail = None
        self._cafe = None
        self._calendar = None
        self._mybox = None
        self._pay = None
        self._talk = None
        self._place = None
        self._smartstore = None

    def login(self, naver_id: str | None = None, naver_pw: str | None = None) -> dict:
        """네이버 자동 로그인 (자격증명 환경변수/파일/파라미터)."""
        from scripts.naver.auth import login_naver
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
    def mail(self):
        if self._mail is None:
            from scripts.naver.mail import NaverMail
            self._mail = NaverMail(self.page)
        return self._mail

    @property
    def cafe(self):
        if self._cafe is None:
            NaverCafe = _load_class("scripts.naver.cafe", "NaverCafe")
            self._cafe = NaverCafe(self.page)
        return self._cafe

    @property
    def calendar(self):
        if self._calendar is None:
            from scripts.naver.calendar_tasks import NaverCalendar
            self._calendar = NaverCalendar(self.page)
        return self._calendar

    @property
    def mybox(self):
        if self._mybox is None:
            from scripts.naver.mybox import NaverMyBox
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
            from scripts.naver.talk import NaverTalk
            self._talk = NaverTalk(self.page)
        return self._talk

    @property
    def place(self):
        if self._place is None:
            from scripts.naver.place import NaverPlace
            self._place = NaverPlace(self.page)
        return self._place

    @property
    def smartstore(self):
        if self._smartstore is None:
            from scripts.naver.smartstore import NaverSmartStore
            self._smartstore = NaverSmartStore(self.page)
        return self._smartstore


# 외부에서 직접 사용 가능한 진입점
__all__ = ["NaverServices"]

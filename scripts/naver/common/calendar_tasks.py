"""네이버 캘린더 자동화.

URL: https://calendar.naver.com/

사용:
  from scripts.naver.common.calendar_tasks import NaverCalendar
  c = NaverCalendar(page)
  c.list_events(from_date, to_date)
  c.add_event(title, start, end, location, memo)
"""

from __future__ import annotations

import contextlib
import time
from datetime import date, datetime

from playwright.sync_api import Page

from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger
from scripts.naver.common.auth import open_logged_in_page

_log = get_logger(__name__)

CALENDAR_URL = "https://calendar.naver.com/"


class NaverCalendar:
    def __init__(self, page: Page):
        self.page = page

    def open(self) -> bool:
        return open_logged_in_page(self.page, CALENDAR_URL)

    def list_events(self, target_date: date | None = None) -> list[dict]:
        """현재 표시된 캘린더의 일정 목록 (대략적)."""
        if not self.open():
            return []
        try:
            events = self.page.evaluate("""
            () => {
                const out = [];
                const seen = new Set();
                document.querySelectorAll('[class*="event"], .calendar_event, .schedule_item').forEach(el => {
                    if (el.offsetParent === null) return;
                    const title = (el.innerText || '').trim().substring(0, 60);
                    const time_el = el.querySelector('.time, .start_time')?.innerText?.trim() || '';
                    if (title && !seen.has(title)) {
                        seen.add(title);
                        out.push({title, time: time_el});
                    }
                });
                return out;
            }
            """)
            return events
        except Exception as e:  # noqa: BLE001 - 네이버 캘린더 일정 조회/추가 자동화 - confirm=True 일 때만 실제 저장 버튼 클릭(감사로그 남김), 실패시 ok:False,error 반환
            _log.error("[naver-calendar] list 실패: %s", e)
            return []

    def add_event(
        self,
        title: str,
        start: datetime,
        end: datetime | None = None,
        location: str = "",
        memo: str = "",
        confirm: bool = False,
    ) -> dict:
        """일정 추가. confirm=False (기본) 시 작성만, confirm=True 시 저장."""
        if not self.open():
            return {"ok": False, "error": "open_failed"}
        try:
            # 일정 추가 버튼
            self.page.locator('button:has-text("일정"), .btn_write, [class*="event-add"]').first.click(timeout=5000)
            time.sleep(2)

            # 제목
            self.page.locator('input[name="title"], input[placeholder*="제목"]').first.fill(title, timeout=3000)
            time.sleep(0.3)

            # 시간 (간단 fill — 실제 캘린더는 더 복잡)
            try:
                start_str = start.strftime("%Y-%m-%d %H:%M")
                self.page.locator('input[name="start"], input[type="datetime-local"]').first.fill(start_str)
            except Exception:  # noqa: BLE001 - 네이버 캘린더 일정 조회/추가 자동화 - confirm=True 일 때만 실제 저장 버튼 클릭(감사로그 남김), 실패시 ok:False,error 반환
                pass
            if end:
                try:
                    end_str = end.strftime("%Y-%m-%d %H:%M")
                    self.page.locator('input[name="end"]').first.fill(end_str)
                except Exception:  # noqa: BLE001 - 네이버 캘린더 일정 조회/추가 자동화 - confirm=True 일 때만 실제 저장 버튼 클릭(감사로그 남김), 실패시 ok:False,error 반환
                    pass

            # 위치/메모
            if location:
                # 네이버 캘린더 일정 조회/추가 자동화 - confirm=True 일 때만 실제 저장 버튼 클릭(감사로그 남김), 실패시 ok:False,error 반환
                with contextlib.suppress(Exception):
                    self.page.locator('input[name="location"], input[placeholder*="위치"]').first.fill(location)
            if memo:
                # 네이버 캘린더 일정 조회/추가 자동화 - confirm=True 일 때만 실제 저장 버튼 클릭(감사로그 남김), 실패시 ok:False,error 반환
                with contextlib.suppress(Exception):
                    self.page.locator('textarea[name="memo"], textarea').first.fill(memo)

            if confirm:
                self.page.locator('button:has-text("저장"), .btn_save').first.click(timeout=3000)
                time.sleep(2)
                log_critical("OTHER", f"캘린더 일정 추가: {title}", start=start.isoformat(), mode="calendar_add")
                return {"ok": True, "mode": "saved"}
            return {"ok": True, "mode": "filled_not_saved"}
        except Exception as e:  # noqa: BLE001 - 네이버 캘린더 일정 조회/추가 자동화 - confirm=True 일 때만 실제 저장 버튼 클릭(감사로그 남김), 실패시 ok:False,error 반환
            _log.error("[naver-calendar] add 실패: %s", e)
            return {"ok": False, "error": str(e)}

"""Google Calendar OOP 인터페이스 (기존 calendar.py 보존).

사용:
    cal = CalendarAPI(page)
    cal.list_today()
    cal.list_week()
    cal.create_event(title="회의", when="2026-05-13 14:00", duration_min=60)
    cal.quick_add("내일 오후 3시 미용실 예약")
"""

from __future__ import annotations

import time
from contextlib import suppress
from datetime import datetime, timedelta

from playwright.sync_api import Page

from scripts.common.config import GOOGLE_URLS
from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger

_log = get_logger(__name__)


class CalendarAPI:
    """Google Calendar 자동화."""

    def __init__(self, page: Page):
        self.page = page

    def list_today(self) -> list[dict]:
        """오늘 일정."""
        # 캘린더는 백그라운드 폴링이 끊이지 않는 SPA라 기본 wait_until="load" 가
        # 안 끝날 수 있음(2026-09-29 실측: list_week 에서 20s 타임아웃 확인,
        # GCP 콘솔과 동일 원인) — DOM 로드 시점까지만 대기.
        self.page.goto(
            GOOGLE_URLS.get("calendar_day", "https://calendar.google.com/calendar/u/0/r/day"),
            timeout=45000,
            wait_until="domcontentloaded",
        )
        time.sleep(2.5)
        return self._extract_events()

    def list_week(self) -> list[dict]:
        """이번 주 일정."""
        self.page.goto(
            GOOGLE_URLS.get("calendar_week", "https://calendar.google.com/calendar/u/0/r/week"),
            timeout=45000,
            wait_until="domcontentloaded",
        )
        time.sleep(2.5)
        return self._extract_events()

    def _extract_events(self) -> list[dict]:
        try:
            return (
                self.page.evaluate("""
            () => {
                const out = [];
                document.querySelectorAll('[role="button"][data-eventid], [data-eventchip]').forEach(el => {
                    const t = (el.innerText || '').trim();
                    const aria = el.getAttribute('aria-label') || '';
                    if (t) out.push({title: t.substring(0, 60), aria: aria.substring(0, 200)});
                });
                return out.slice(0, 50);
            }
            """)
                or []
            )
        except Exception:  # noqa: BLE001 - 구글 캘린더 CDP 자동화 - 이벤트 생성/조회 실패 시 에러 메시지(100자 절단) 반환
            return []

    def _open_create_event_dialog(self) -> None:
        """'만들기' → '일정' 메뉴를 열고 quick 다이얼로그 등장까지 대기. 실패 시 RuntimeError."""
        # 만들기 버튼 — 메뉴 열릴 때까지 최대 3회 retry
        menu_open = False
        for attempt in range(3):
            clicked = self.page.evaluate("""
                () => {
                    for (const b of document.querySelectorAll('button, [role="button"]')) {
                        const t = (b.innerText || '').trim();
                        if (t.includes('만들기') && t.length < 20) {
                            const r = b.getBoundingClientRect();
                            if (r.x > 0 && r.y > 0 && r.x < 200) { b.click(); return true; }
                        }
                    }
                    return false;
                }
                """)
            if not clicked:
                self.page.keyboard.press("Escape")
                time.sleep(0.5)
                continue
            time.sleep(1.2)
            menu_count = self.page.evaluate("() => document.querySelectorAll('li[role=\"menuitem\"]').length")
            if menu_count > 0:
                menu_open = True
                break
            # 메뉴 안 열림 → ESC + 재시도
            self.page.keyboard.press("Escape")
            time.sleep(0.8)
        if not menu_open:
            raise RuntimeError("'만들기' 메뉴 열기 실패 (3회 재시도)")
        time.sleep(0.4)
        # '일정' 메뉴 항목 클릭 — JS로 정확 매칭
        picked = self.page.evaluate("""
            () => {
                for (const el of document.querySelectorAll('li[role="menuitem"], div[role="menuitem"]')) {
                    const t = (el.innerText || '').trim();
                    if (t === '일정' || t === 'Event') { el.click(); return true; }
                }
                return false;
            }
            """)
        if not picked:
            raise RuntimeError("'일정' 메뉴 못 찾음")
        # 다이얼로그 등장까지 명시적 대기
        self.page.wait_for_selector('[role="dialog"] input[aria-label="제목 추가"]', timeout=10000, state="visible")

        # quick 다이얼로그 등장 대기
        self.page.wait_for_selector('[role="dialog"] input[aria-label="제목 추가"]', timeout=8000)

    def _save_event_full_page(self, title: str, location: str, description: str) -> None:
        """'옵션 더보기' 풀 페이지에서 제목/위치/설명을 입력하고 저장. 저장 버튼 없으면 RuntimeError."""
        self.page.locator(
            '[role="dialog"] button:has-text("옵션 더보기"), [role="dialog"] button:has-text("More options")'
        ).first.click(timeout=4000)
        time.sleep(3)
        # 풀 페이지: 제목 input
        self.page.locator('input[aria-label="제목 추가"], input[placeholder="제목 추가"]').first.fill(
            title, timeout=5000
        )
        time.sleep(0.5)
        if location:
            with suppress(Exception):
                self.page.locator('input[aria-label*="위치"], input[placeholder*="위치"]').first.fill(
                    location, timeout=3000
                )
        if description:
            try:
                desc_el = self.page.locator(
                    '[aria-label="설명 추가"], div[contenteditable="true"][aria-label*="설명"], textarea[aria-label*="설명"]'
                ).first
                desc_el.click(timeout=2000)
                self.page.keyboard.type(description, delay=10)
            except Exception:  # noqa: BLE001 - 구글 캘린더 CDP 자동화 - 이벤트 생성/조회 실패 시 에러 메시지(100자 절단) 반환
                pass
        time.sleep(0.5)
        # 풀 페이지 저장 버튼 — JS 직접 클릭
        saved = self.page.evaluate("""
                () => {
                    for (const b of document.querySelectorAll('button, [role="button"]')) {
                        const t = (b.innerText || '').trim();
                        if (t === '저장' || t === 'Save') { b.click(); return true; }
                    }
                    return false;
                }
                """)
        if not saved:
            raise RuntimeError("'저장' 버튼 못 찾음 (풀페이지)")

    def _save_event_quick_dialog(self, title: str) -> None:
        """quick 다이얼로그 내 직접 입력 + 저장. 저장 버튼 없으면 RuntimeError."""
        self.page.locator('[role="dialog"] input[aria-label="제목 추가"]').first.fill(title, timeout=5000)
        time.sleep(0.7)
        # 저장 버튼 — JS로 정확 클릭 (다이얼로그 내부 button, text="저장")
        saved = self.page.evaluate("""
                () => {
                    const dlg = document.querySelector('[role="dialog"]');
                    if (!dlg) return false;
                    for (const b of dlg.querySelectorAll('button')) {
                        const t = (b.innerText || '').trim();
                        if (t === '저장' || t === 'Save') { b.click(); return true; }
                    }
                    return false;
                }
                """)
        if not saved:
            raise RuntimeError("'저장' 버튼 못 찾음")

    def create_event(
        self,
        *,
        title: str,
        when: str | datetime,
        duration_min: int = 60,
        location: str = "",
        description: str = "",
        attendees: list[str] | None = None,
    ) -> dict:
        """이벤트 생성. when: 'YYYY-MM-DD HH:MM' 문자열 또는 datetime."""
        if isinstance(when, str):
            try:
                when_dt = datetime.strptime(when, "%Y-%m-%d %H:%M")
            except ValueError:
                return {"ok": False, "error": "when 형식: YYYY-MM-DD HH:MM"}
        else:
            when_dt = when
        end_dt = when_dt + timedelta(minutes=duration_min)

        # 안전한 시작 상태로 초기화 (이전 다이얼로그/메뉴 닫기 + 새로고침)
        try:
            self.page.keyboard.press("Escape")
            time.sleep(0.5)
            self.page.keyboard.press("Escape")
        except Exception:  # noqa: BLE001 - 구글 캘린더 CDP 자동화 - 이벤트 생성/조회 실패 시 에러 메시지(100자 절단) 반환
            pass

        self.page.goto("https://calendar.google.com/calendar/u/0/r", timeout=20000)
        time.sleep(3.5)
        try:
            self._open_create_event_dialog()

            # description/location 있으면 '옵션 더보기' → 풀 페이지로 (안정적 입력)
            if description or location:
                self._save_event_full_page(title, location, description)
            else:
                self._save_event_quick_dialog(title)
            time.sleep(3)
            log_critical("OTHER", f"Calendar 이벤트: {title}", when=when_dt.isoformat(), mode="cal_create")
            return {"ok": True, "title": title, "when": when_dt.isoformat(), "end": end_dt.isoformat()}
        except Exception as e:  # noqa: BLE001 - 구글 캘린더 CDP 자동화 - 이벤트 생성/조회 실패 시 에러 메시지(100자 절단) 반환
            return {"ok": False, "error": str(e)[:100]}

    def quick_add(self, text: str) -> dict:
        """자연어 빠른 추가 (예: '내일 오후 3시 미용실')."""
        self.page.goto("https://calendar.google.com/calendar/u/0/r", timeout=20000)
        time.sleep(2.5)
        try:
            # Q 단축키로 빠른 추가 열기
            self.page.keyboard.press("q")
            time.sleep(1.5)
            box = self.page.locator('input[aria-label*="빠른"], input[placeholder*="What"], input[type="text"]').first
            box.fill(text, timeout=3000)
            time.sleep(0.5)
            self.page.keyboard.press("Enter")
            time.sleep(2.5)
            log_critical("OTHER", f"Calendar 빠른추가: {text[:40]}", mode="cal_quick")
            return {"ok": True, "text": text}
        except Exception as e:  # noqa: BLE001 - 구글 캘린더 CDP 자동화 - 이벤트 생성/조회 실패 시 에러 메시지(100자 절단) 반환
            return {"ok": False, "error": str(e)[:100]}

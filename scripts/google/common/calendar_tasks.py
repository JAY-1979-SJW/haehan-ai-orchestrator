"""Google Calendar 자동화"""

from __future__ import annotations

from typing import Any

from scripts.common.config import GOOGLE_URLS

from scripts.google.common.base import page_goto, page_wait_click, page_wait_type, page_wait_visible, task_context
from scripts.google.common.browser_tasks import ContextDeleteSpec, run_context_menu_delete, run_event_list


def run(task: str, args: list[str]) -> None:
    """Calendar 작업 실행."""
    with task_context("google", f"cal-{task}", args) as page:
        match task:
            case "today":
                _task_today(page, args)
            case "week":
                _task_week(page, args)
            case "create":
                _task_create(page, args)
            case "delete":
                _task_delete(page, args)
            case _:
                print(f"  [오류] 알 수 없는 작업: {task}")


_TODAY_EVENTS_JS = r"""() => {
        const results = [];
        for (const el of document.querySelectorAll('[data-eventchip], [role="button"][data-draggable-id*="event"]')) {
            const title = el.getAttribute('data-eventchip') || el.textContent.trim();
            const time = el.getAttribute('data-time') || '';
            if (title) results.push({title, time});
        }
        return results;
    }"""

_WEEK_EVENTS_JS = r"""() => {
        const results = [];
        for (const el of document.querySelectorAll('[data-eventchip]')) {
            const title = el.getAttribute('data-eventchip') || el.textContent.trim();
            const date = el.getAttribute('data-date') || '';
            if (title) results.push({title, date});
        }
        return results.slice(0, 20);
    }"""


def _task_today(page: Any, args: list[str]) -> None:
    """오늘 일정."""
    run_event_list(
        page,
        heading="Google Calendar 오늘 일정",
        url=GOOGLE_URLS["calendar_day"],
        ready_selector='[role="main"], [data-view="day"], .KF4T6b',
        events_js=_TODAY_EVENTS_JS,
        when_key="time",
    )


def _task_week(page: Any, args: list[str]) -> None:
    """주간 일정."""
    run_event_list(
        page,
        heading="Google Calendar 주간 일정",
        url=GOOGLE_URLS["calendar_week"],
        ready_selector='[role="main"], [data-view="week"], .KF4T6b',
        events_js=_WEEK_EVENTS_JS,
        when_key="date",
    )


def _task_create(page: Any, args: list[str]) -> None:
    """이벤트 생성.

    args[0]: 제목
    args[1]: 날짜 (YYYY-MM-DD)
    args[2]: 시간 (HH:MM)
    """
    if not args:
        print("  [오류] 이벤트 제목을 입력하세요")
        return

    title = args[0]
    date_str = args[1] if len(args) > 1 else ""
    time_str = args[2] if len(args) > 2 else ""

    print("\n[작업] Google Calendar 이벤트 생성")
    print(f"  제목: {title}")
    if date_str:
        print(f"  날짜: {date_str}")
    if time_str:
        print(f"  시간: {time_str}")

    page_goto(page, GOOGLE_URLS["calendar_home"])
    # 캘린더 로드 확인
    page_wait_visible(page, 'button[aria-label*="만들"], button[aria-label*="Create"]', timeout=20000)

    # 만들기 버튼 클릭
    if not page_wait_click(page, 'button[aria-label*="만들"], button[aria-label*="Create"]'):
        print("  ⚠  만들기 버튼 못 찾음")
        return

    # 이벤트 생성 폼 나타날 때까지 대기
    if not page_wait_visible(
        page, 'input[type="text"], input[placeholder*="제목"], input[placeholder*="Title"]', timeout=10000
    ):
        print("  ⚠  이벤트 입력 폼 못 찾음")
        return

    # 제목 입력
    if not page_wait_type(page, 'input[type="text"], input[placeholder*="제목"], input[placeholder*="Title"]', title):
        print("  ⚠  제목 입력 실패")
        return

    # 날짜 입력
    if date_str:
        page_wait_type(page, 'input[type="date"]', date_str)

    # 시간 입력
    if time_str:
        page_wait_type(page, 'input[type="time"]', time_str)

    # 저장 버튼 대기 후 클릭
    saved = page_wait_click(
        page, 'button:has-text("저장"), button:has-text("Save"), button[aria-label*="저장"], button[aria-label*="Save"]'
    )
    if saved:
        # 저장 후 캘린더 화면으로 복귀 대기
        page_wait_visible(page, '[role="main"]', timeout=10000)
        print("  ✓ 이벤트 생성 완료")
    else:
        print("  ⚠  저장 버튼 못 찾음")


def _task_delete(page: Any, args: list[str]) -> None:
    """이벤트 삭제."""
    run_context_menu_delete(
        page,
        args,
        ContextDeleteSpec(
            empty_message="  [오류] 삭제할 이벤트 제목을 입력하세요",
            heading="Google Calendar 이벤트 삭제",
            home_url=GOOGLE_URLS["calendar_day"],
            ready_selector='[role="main"]',
            ready_timeout=15000,
            candidates_selector='[role="button"]',
            match_condition="el.textContent.includes({name})",
            menu_selector='[role="menu"], [role="menuitem"]',
            done_message="  ✓ 이벤트 삭제 완료",
            fail_message="  ⚠  삭제 메뉴 못 찾음",
        ),
    )

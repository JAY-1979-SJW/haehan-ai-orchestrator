"""Google Calendar 자동화"""
from __future__ import annotations

from typing import Any

from .base import task_context


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


def _task_today(page: Any, args: list[str]) -> None:
    """오늘 일정."""
    print("\n[작업] Google Calendar 오늘 일정")

    page.goto("https://calendar.google.com/calendar/u/0/r/day", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    events = page.evaluate(r"""() => {
        const results = [];
        for (const el of document.querySelectorAll('[data-eventchip], [role="button"][data-draggable-id*="event"]')) {
            const title = el.getAttribute('data-eventchip') || el.textContent.trim();
            const time = el.getAttribute('data-time') || '';
            if (title) results.push({title, time});
        }
        return results;
    }""")

    print(f"  일정 수: {len(events)}")
    for i, evt in enumerate(events, 1):
        print(f"  [{i}] {evt['time']:20s} {evt['title'][:50]}")


def _task_week(page: Any, args: list[str]) -> None:
    """주간 일정."""
    print("\n[작업] Google Calendar 주간 일정")

    page.goto("https://calendar.google.com/calendar/u/0/r/week", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    events = page.evaluate(r"""() => {
        const results = [];
        for (const el of document.querySelectorAll('[data-eventchip]')) {
            const title = el.getAttribute('data-eventchip') || el.textContent.trim();
            const date = el.getAttribute('data-date') || '';
            if (title) results.push({title, date});
        }
        return results.slice(0, 20);
    }""")

    print(f"  일정 수: {len(events)}")
    for i, evt in enumerate(events, 1):
        print(f"  [{i}] {evt['date']:20s} {evt['title'][:50]}")


def _task_create(page: Any, args: list[str]) -> None:
    """이벤트 생성.

    args[0]: 제목
    args[1]: 날짜 (YYYY-MM-DD, 생략 가능)
    args[2]: 시간 (HH:MM, 생략 가능)
    """
    if not args:
        print("  [오류] 이벤트 제목을 입력하세요")
        return

    title = args[0]
    date_str = args[1] if len(args) > 1 else ""
    time_str = args[2] if len(args) > 2 else ""

    print(f"\n[작업] Google Calendar 이벤트 생성")
    print(f"  📌 제목: {title}")
    if date_str:
        print(f"  📅 날짜: {date_str}")
    if time_str:
        print(f"  🕐 시간: {time_str}")

    page.goto("https://calendar.google.com/calendar/u/0/r", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(4000)

    # 만들기 버튼 클릭 (JavaScript)
    page.evaluate("""() => {
        const btn = document.querySelector('button[aria-label*="만들"]');
        if (btn) {
            btn.click();
            return true;
        }
        return false;
    }""")
    page.wait_for_timeout(2000)

    # 제목 입력
    page.evaluate(f"""() => {{
        const inputs = document.querySelectorAll('input[type="text"]');
        if (inputs.length > 0) {{
            inputs[0].focus();
            inputs[0].value = {repr(title)};
            inputs[0].dispatchEvent(new Event('input', {{ bubbles: true }}));
        }}
    }}""")
    page.wait_for_timeout(300)

    # 날짜 입력
    if date_str:
        page.evaluate(f"""() => {{
            const dateInputs = document.querySelectorAll('input[type="date"]');
            if (dateInputs.length > 0) {{
                dateInputs[0].focus();
                dateInputs[0].value = {repr(date_str)};
                dateInputs[0].dispatchEvent(new Event('input', {{ bubbles: true }}));
                dateInputs[0].dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}
        }}""")
        page.wait_for_timeout(300)

    # 시간 입력
    if time_str:
        page.evaluate(f"""() => {{
            const timeInputs = document.querySelectorAll('input[type="time"]');
            if (timeInputs.length > 0) {{
                timeInputs[0].focus();
                timeInputs[0].value = {repr(time_str)};
                timeInputs[0].dispatchEvent(new Event('input', {{ bubbles: true }}));
                timeInputs[0].dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}
        }}""")
        page.wait_for_timeout(300)

    # 저장 버튼 클릭
    page.evaluate("""() => {
        const buttons = document.querySelectorAll('button');
        for (const btn of buttons) {
            const text = btn.textContent.toLowerCase();
            const aria = (btn.getAttribute('aria-label') || '').toLowerCase();
            if (text.includes('저장') || aria.includes('저장') ||
                text.includes('save') || aria.includes('save') ||
                text === 'ok' || aria === 'ok') {
                btn.click();
                return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1500)
    print("  ✓ 이벤트 생성 완료")


def _task_delete(page: Any, args: list[str]) -> None:
    """이벤트 삭제."""
    if not args:
        print("  [오류] 삭제할 이벤트 제목을 입력하세요")
        return

    event_name = " ".join(args)
    print(f"\n[작업] Google Calendar 이벤트 삭제: {event_name}")

    page.goto("https://calendar.google.com/calendar/u/0/r/day", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    # 이벤트 찾아 우클릭 → 삭제
    page.evaluate(f"""() => {{
        for (const el of document.querySelectorAll('[role="button"]')) {{
            if (el.textContent.includes({repr(event_name)})) {{
                el.dispatchEvent(new MouseEvent('contextmenu', {{ bubbles: true }}));
                break;
            }}
        }}
    }}""")
    page.wait_for_timeout(1000)

    # 삭제 메뉴 클릭
    page.evaluate("""() => {
        const del_items = Array.from(document.querySelectorAll('div, span')).filter(d =>
            d.textContent.includes('Delete') || d.textContent.includes('삭제')
        );
        if (del_items.length > 0) {
            del_items[0].click();
        }
    }""")
    page.wait_for_timeout(1000)
    print("  ✓ 이벤트 삭제 완료")

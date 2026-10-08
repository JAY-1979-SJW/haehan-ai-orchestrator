"""Google 웹 화면 작업(_task_*) 공용 본문.

docs·drive·sheets·calendar 모듈이 서비스 이름·URL·selector 만 바꿔 똑같이 쓰던 브라우저 작업
(검색, 우클릭 메뉴 삭제, 최근 목록, 새 문서 열기, 일정 목록)을 한 곳으로 모았다.
출력 문구·대기 selector·timeout 은 호출하는 쪽이 넘기며, 이 모듈은 순서만 정한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scripts.google.common.base import page_goto, page_wait_click, page_wait_type, page_wait_visible

_RECENT_TITLES_JS = r"""() => {
        const results = [];
        for (const el of document.querySelectorAll('[role="listitem"] [aria-label]')) {
            const title = el.getAttribute('aria-label') || el.textContent.trim();
            if (title && title.length > 2) results.push(title);
        }
        return results.slice(0, 10);
    }"""


def run_search(page: Any, args: list[str], *, service: str, home_url: str, search_selector: str) -> None:
    """홈 화면 검색창에 args 를 입력하고 Enter. 인자가 없으면 오류만 출력."""
    if not args:
        print("  [오류] 검색어를 입력하세요")
        return

    query = " ".join(args)
    print(f"\n[작업] {service} 검색: {query}")

    page_goto(page, home_url)
    page_wait_visible(page, '[role="main"]', timeout=20000)

    if page_wait_type(page, search_selector, query):
        page.keyboard.press("Enter")
        page_wait_visible(page, '[role="main"]', timeout=10000)
        print("  ✓ 검색 완료")
    else:
        print("  ⚠  검색창 못 찾음")


@dataclass(frozen=True)
class ContextDeleteSpec:
    """우클릭 메뉴 삭제 작업의 서비스별 문구·selector.

    match_condition 은 JS 조건식이며 '{name}' 자리에 이름의 파이썬 repr 이 들어간다
    (예: "el.textContent.includes({name})").
    """

    empty_message: str
    heading: str
    home_url: str
    ready_selector: str
    ready_timeout: int
    candidates_selector: str
    match_condition: str
    menu_selector: str
    done_message: str
    fail_message: str


def run_context_menu_delete(page: Any, args: list[str], spec: ContextDeleteSpec) -> None:
    """이름(args)으로 spec.candidates_selector 항목을 찾아 우클릭 메뉴의 '삭제'를 누른다."""
    if not args:
        print(spec.empty_message)
        return

    name = " ".join(args)
    print(f"\n[작업] {spec.heading}: {name}")

    page_goto(page, spec.home_url)
    page_wait_visible(page, spec.ready_selector, timeout=spec.ready_timeout)

    condition = spec.match_condition.format(name=repr(name))
    page.evaluate(f"""() => {{
        for (const el of document.querySelectorAll('{spec.candidates_selector}')) {{
            if ({condition}) {{
                el.dispatchEvent(new MouseEvent('contextmenu', {{ bubbles: true }}));
                break;
            }}
        }}
    }}""")

    if page_wait_visible(page, spec.menu_selector, timeout=5000):
        page_wait_click(
            page,
            '[role="menuitem"]:has-text("삭제"), [role="menuitem"]:has-text("Delete")',
        )
        page_wait_visible(page, spec.ready_selector, timeout=5000)
        print(spec.done_message)
    else:
        print(spec.fail_message)


def run_recent_titles(page: Any, *, heading: str, home_url: str, count_label: str) -> None:
    """홈 목록에서 최근 항목 제목 최대 10개를 출력."""
    print(f"\n[작업] {heading}")

    page_goto(page, home_url)
    page_wait_visible(page, '[role="listitem"], [data-item-id]', timeout=20000)

    titles = page.evaluate(_RECENT_TITLES_JS)

    print(f"  {count_label}: {len(titles)}")
    for i, title in enumerate(titles, 1):
        print(f"  [{i}] {title[:60]}")


def run_open_editor(page: Any, *, heading: str, url: str, editor_selector: str, done_message: str) -> None:
    """새 문서 URL 을 열고 편집기가 보일 때까지 기다린다."""
    print(f"\n[작업] {heading}")

    page_goto(page, url)
    page_wait_visible(page, editor_selector, timeout=30000)
    print(done_message)


def run_event_list(
    page: Any,
    *,
    heading: str,
    url: str,
    ready_selector: str,
    events_js: str,
    when_key: str,
) -> None:
    """캘린더 화면의 일정 목록을 events_js 로 읽어 '[번호] <when_key 값> 제목' 형식으로 출력."""
    print(f"\n[작업] {heading}")

    page_goto(page, url)
    page_wait_visible(page, ready_selector, timeout=15000)

    events = page.evaluate(events_js)

    print(f"  일정 수: {len(events)}")
    for i, evt in enumerate(events, 1):
        print(f"  [{i}] {evt[when_key]:20s} {evt['title'][:50]}")

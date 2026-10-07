"""Google Docs 자동화"""
from __future__ import annotations

from typing import Any

from scripts.common.config import GOOGLE_URLS

from scripts.google.common.base import page_goto, page_wait_visible, task_context
from scripts.google.common.browser_tasks import ContextDeleteSpec, run_context_menu_delete, run_open_editor, run_recent_titles, run_search


def run(task: str, args: list[str]) -> None:
    """Docs 작업 실행."""
    with task_context("google", f"docs-{task}", args) as page:
        match task:
            case "recent":
                _task_recent(page, args)
            case "new":
                _task_new(page, args)
            case "search":
                _task_search(page, args)
            case "open":
                _task_open(page, args)
            case "delete":
                _task_delete(page, args)
            case _:
                print(f"  [오류] 알 수 없는 작업: {task}")


def _task_recent(page: Any, args: list[str]) -> None:
    """최근 문서."""
    run_recent_titles(page, heading="Google Docs 최근 문서", home_url=GOOGLE_URLS["docs_home"], count_label="문서 수")


def _task_new(page: Any, args: list[str]) -> None:
    """새 문서 생성."""
    run_open_editor(
        page,
        heading="Google Docs 새 문서 생성",
        url=GOOGLE_URLS["docs_create"],
        editor_selector="#docs-editor, .docs-editor-container",
        done_message="  ✓ 새 문서 생성 완료",
    )


def _task_search(page: Any, args: list[str]) -> None:
    """문서 검색."""
    run_search(page, args, service="Docs", home_url=GOOGLE_URLS["docs_home"], search_selector='input[placeholder*="Search"], input[aria-label*="Search"]')


def _task_open(page: Any, args: list[str]) -> None:
    """문서 열기."""
    if not args:
        print("  [오류] 문서명을 입력하세요")
        return

    doc_name = " ".join(args)
    print(f"\n[작업] Docs 문서 열기: {doc_name}")

    page_goto(page, GOOGLE_URLS["docs_home"])
    page_wait_visible(page, '[role="listitem"]', timeout=20000)

    page.evaluate(f"""() => {{
        for (const el of document.querySelectorAll('[role="listitem"]')) {{
            if (el.textContent.includes({repr(doc_name)})) {{
                el.click();
                break;
            }}
        }}
    }}""")

    # 문서 에디터 로드 대기
    page_wait_visible(page, '#docs-editor, .docs-editor-container', timeout=20000)
    print("  ✓ 문서 열기 완료")


def _task_delete(page: Any, args: list[str]) -> None:
    """문서 삭제."""
    run_context_menu_delete(
        page,
        args,
        ContextDeleteSpec(
            empty_message="  [오류] 삭제할 문서명을 입력하세요",
            heading="Docs 문서 삭제",
            home_url=GOOGLE_URLS["docs_home"],
            ready_selector='[role="listitem"]',
            ready_timeout=20000,
            candidates_selector='[role="listitem"]',
            match_condition="el.textContent.includes({name})",
            menu_selector='[role="menu"]',
            done_message="  ✓ 문서 삭제 완료",
            fail_message="  ⚠  컨텍스트 메뉴 못 찾음",
        ),
    )

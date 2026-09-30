"""Google Sheets 자동화"""

from __future__ import annotations

from typing import Any

from scripts.config import GOOGLE_URLS

from .base import page_goto, page_wait_click, page_wait_type, page_wait_visible, task_context


def run(task: str, args: list[str]) -> None:
    """Sheets 작업 실행."""
    with task_context("google", f"sheets-{task}", args) as page:
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
            case "insert":
                _task_insert(page, args)
            case "edit":
                _task_edit(page, args)
            case _:
                print(f"  [오류] 알 수 없는 작업: {task}")


def _task_recent(page: Any, args: list[str]) -> None:
    """최근 시트."""
    print("\n[작업] Google Sheets 최근 시트")

    page_goto(page, GOOGLE_URLS["sheets_home"])
    page_wait_visible(page, '[role="listitem"], [data-item-id]', timeout=20000)

    sheets = page.evaluate(r"""() => {
        const results = [];
        for (const el of document.querySelectorAll('[role="listitem"] [aria-label]')) {
            const title = el.getAttribute('aria-label') || el.textContent.trim();
            if (title && title.length > 2) results.push(title);
        }
        return results.slice(0, 10);
    }""")

    print(f"  시트 수: {len(sheets)}")
    for i, sheet in enumerate(sheets, 1):
        print(f"  [{i}] {sheet[:60]}")


def _task_new(page: Any, args: list[str]) -> None:
    """새 시트 생성."""
    print("\n[작업] Google Sheets 새 시트 생성")

    page_goto(page, GOOGLE_URLS["sheets_create"])
    # 스프레드시트 에디터 로드 대기
    page_wait_visible(page, '#docs-editor, .docs-editor-container, [id*="grid"]', timeout=30000)
    print("  ✓ 새 시트 생성 완료")


def _task_search(page: Any, args: list[str]) -> None:
    """시트 검색."""
    if not args:
        print("  [오류] 검색어를 입력하세요")
        return

    query = " ".join(args)
    print(f"\n[작업] Sheets 검색: {query}")

    page_goto(page, GOOGLE_URLS["sheets_home"])
    page_wait_visible(page, '[role="main"]', timeout=20000)

    if page_wait_type(page, 'input[placeholder*="Search"], input[aria-label*="Search"]', query):
        page.keyboard.press("Enter")
        page_wait_visible(page, '[role="main"]', timeout=10000)
        print("  ✓ 검색 완료")
    else:
        print("  ⚠  검색창 못 찾음")


def _task_open(page: Any, args: list[str]) -> None:
    """시트 열기."""
    if not args:
        print("  [오류] 시트명을 입력하세요")
        return

    sheet_name = " ".join(args)
    print(f"\n[작업] Sheets 시트 열기: {sheet_name}")

    page_goto(page, GOOGLE_URLS["sheets_home"])
    page_wait_visible(page, '[role="listitem"]', timeout=20000)

    page.evaluate(f"""() => {{
        for (const el of document.querySelectorAll('[role="listitem"]')) {{
            if (el.textContent.includes({sheet_name!r})) {{
                el.click();
                break;
            }}
        }}
    }}""")

    # 시트 에디터 로드 대기
    page_wait_visible(page, "#docs-editor, .docs-editor-container", timeout=20000)
    print("  ✓ 시트 열기 완료")


def _task_delete(page: Any, args: list[str]) -> None:
    """시트 삭제."""
    if not args:
        print("  [오류] 삭제할 시트명을 입력하세요")
        return

    sheet_name = " ".join(args)
    print(f"\n[작업] Sheets 시트 삭제: {sheet_name}")

    page_goto(page, GOOGLE_URLS["sheets_home"])
    page_wait_visible(page, '[role="listitem"]', timeout=20000)

    page.evaluate(f"""() => {{
        for (const el of document.querySelectorAll('[role="listitem"]')) {{
            if (el.textContent.includes({sheet_name!r})) {{
                el.dispatchEvent(new MouseEvent('contextmenu', {{ bubbles: true }}));
                break;
            }}
        }}
    }}""")

    if page_wait_visible(page, '[role="menu"]', timeout=5000):
        page_wait_click(page, '[role="menuitem"]:has-text("삭제"), [role="menuitem"]:has-text("Delete")')
        page_wait_visible(page, '[role="listitem"]', timeout=5000)
        print("  ✓ 시트 삭제 완료")
    else:
        print("  ⚠  컨텍스트 메뉴 못 찾음")


def _task_insert(page: Any, args: list[str]) -> None:
    """행 데이터 추가.

    args[0]: 시트명
    args[1+]: 행 데이터
    """
    if len(args) < 2:
        print("  [오류] 사용법: sheets insert <시트명> <데이터1> [데이터2 ...]")
        return

    sheet_name = args[0]
    data = args[1:]

    print("\n[작업] Sheets 행 추가")
    print(f"  시트: {sheet_name}")
    print(f"  데이터: {', '.join(data)}")

    page_goto(page, GOOGLE_URLS["sheets_home"])
    page_wait_visible(page, '[role="listitem"]', timeout=20000)

    # 시트 찾아 열기
    page.evaluate(f"""() => {{
        for (const el of document.querySelectorAll('[role="listitem"]')) {{
            if (el.textContent.includes({sheet_name!r})) {{
                el.click();
                break;
            }}
        }}
    }}""")

    # 에디터 로드 대기
    if not page_wait_visible(page, "#docs-editor, .docs-editor-container", timeout=20000):
        print("  ⚠  시트 에디터 못 열림")
        return

    # Ctrl+End로 마지막 셀 이동 후 다음 행
    page.keyboard.press("Control+End")
    page.wait_for_timeout(500)
    page.keyboard.press("Enter")
    page.wait_for_timeout(300)

    # 데이터 입력
    for i, val in enumerate(data):
        page.keyboard.type(val)
        if i < len(data) - 1:
            page.keyboard.press("Tab")
        page.wait_for_timeout(150)

    page.keyboard.press("Enter")
    page.wait_for_timeout(800)
    print(f"  ✓ 행 추가 완료 ({len(data)}개 열)")


def _task_edit(page: Any, args: list[str]) -> None:
    """셀 편집.

    args[0]: 시트명
    args[1]: 셀 위치 (예: A1)
    args[2+]: 새 값
    """
    if len(args) < 3:
        print("  [오류] 사용법: sheets edit <시트명> <셀위치> <새값>")
        return

    sheet_name = args[0]
    cell_pos = args[1].upper()
    new_value = " ".join(args[2:])

    print(f"\n[작업] Sheets 셀 편집: {sheet_name} / {cell_pos} = {new_value}")

    page_goto(page, GOOGLE_URLS["sheets_home"])
    page_wait_visible(page, '[role="listitem"]', timeout=20000)

    page.evaluate(f"""() => {{
        for (const el of document.querySelectorAll('[role="listitem"]')) {{
            if (el.textContent.includes({sheet_name!r})) {{
                el.click();
                break;
            }}
        }}
    }}""")

    if not page_wait_visible(page, "#docs-editor, .docs-editor-container", timeout=20000):
        print("  ⚠  시트 에디터 못 열림")
        return

    # 이름 상자(셀 주소창)에 직접 입력
    if page_wait_type(
        page,
        '.docs-spreadsheet-name-box input, [aria-label*="이름 상자"], [aria-label*="Name Box"]',
        cell_pos,
        timeout=8000,
    ):
        page.keyboard.press("Enter")
        page.wait_for_timeout(400)
    else:
        # Ctrl+G fallback
        page.keyboard.press("Control+g")
        page.wait_for_timeout(500)
        page_wait_type(page, "input", cell_pos, timeout=5000)
        page.keyboard.press("Enter")
        page.wait_for_timeout(400)

    # 셀 값 입력
    page.keyboard.type(new_value)
    page.keyboard.press("Enter")
    page.wait_for_timeout(800)
    print("  ✓ 셀 편집 완료")

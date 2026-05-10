"""Google Sheets 자동화"""
from __future__ import annotations

from typing import Any

from .base import task_context


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

    page.goto("https://docs.google.com/spreadsheets/u/0/", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

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

    page.goto("https://docs.google.com/spreadsheets/create", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    print("  ✓ 새 시트 생성 완료")


def _task_search(page: Any, args: list[str]) -> None:
    """시트 검색."""
    if not args:
        print("  [오류] 검색어를 입력하세요")
        return

    query = " ".join(args)
    print(f"\n[작업] Sheets 검색: {query}")

    page.goto("https://docs.google.com/spreadsheets/u/0/", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    page.evaluate(f"""() => {{
        const inp = document.querySelector('input[placeholder*="Search"]') ||
                   document.querySelector('input[aria-label*="Search"]');
        if (inp) {{
            inp.focus();
            inp.value = {repr(query)};
            inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
        }}
    }}""")
    page.wait_for_timeout(3000)
    print("  ✓ 검색 완료")


def _task_open(page: Any, args: list[str]) -> None:
    """시트 열기."""
    if not args:
        print("  [오류] 시트명을 입력하세요")
        return

    sheet_name = " ".join(args)
    print(f"\n[작업] Sheets 시트 열기: {sheet_name}")

    page.goto("https://docs.google.com/spreadsheets/u/0/", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    page.evaluate(f"""() => {{
        for (const el of document.querySelectorAll('[role="listitem"]')) {{
            if (el.textContent.includes({repr(sheet_name)})) {{
                el.click();
                break;
            }}
        }}
    }}""")
    page.wait_for_timeout(3000)
    print("  ✓ 시트 열기 완료")


def _task_delete(page: Any, args: list[str]) -> None:
    """시트 삭제."""
    if not args:
        print("  [오류] 삭제할 시트명을 입력하세요")
        return

    sheet_name = " ".join(args)
    print(f"\n[작업] Sheets 시트 삭제: {sheet_name}")

    page.goto("https://docs.google.com/spreadsheets/u/0/", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    # 시트 찾아 우클릭 → 삭제
    page.evaluate(f"""() => {{
        for (const el of document.querySelectorAll('[role="listitem"]')) {{
            if (el.textContent.includes({repr(sheet_name)})) {{
                el.dispatchEvent(new MouseEvent('contextmenu', {{ bubbles: true }}));
                break;
            }}
        }}
    }}""")
    page.wait_for_timeout(1000)

    # 삭제 버튼 클릭
    page.evaluate("""() => {
        const del_btn = Array.from(document.querySelectorAll('div, span')).find(d =>
            d.textContent.includes('Delete') || d.textContent.includes('삭제')
        );
        if (del_btn) del_btn.click();
    }""")
    page.wait_for_timeout(1000)
    print("  ✓ 시트 삭제 완료")


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

    print(f"\n[작업] Sheets 행 추가")
    print(f"  시트: {sheet_name}")
    print(f"  데이터: {', '.join(data)}")

    # 시트 열기
    page.goto("https://docs.google.com/spreadsheets/u/0/", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    page.evaluate(f"""() => {{
        for (const el of document.querySelectorAll('[role="listitem"]')) {{
            if (el.textContent.includes({repr(sheet_name)})) {{
                el.click();
                break;
            }}
        }}
    }}""")
    page.wait_for_timeout(3000)

    # 마지막 행 찾아 데이터 입력
    page.evaluate(f"""() => {{
        const cells = document.querySelectorAll('[data-value], [data-userformat]');
        if (cells.length > 0) {{
            const lastCell = cells[cells.length - 1];
            lastCell.click();
            // 아래쪽으로 이동
            document.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'End', bubbles: true }}));
            document.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', bubbles: true }}));
        }}
    }}""")
    page.wait_for_timeout(500)

    # 데이터 입력
    for i, val in enumerate(data):
        page.keyboard.type(val)
        if i < len(data) - 1:
            page.keyboard.press("Tab")
        page.wait_for_timeout(200)

    page.keyboard.press("Enter")
    page.wait_for_timeout(1000)
    print(f"  ✓ 행 추가 완료 ({len(data)}개 열)")


def _task_edit(page: Any, args: list[str]) -> None:
    """셀 편집.

    args[0]: 시트명
    args[1]: 셀 위치 (예: A1, B2)
    args[2+]: 새 값
    """
    if len(args) < 3:
        print("  [오류] 사용법: sheets edit <시트명> <셀위치> <새값>")
        return

    sheet_name = args[0]
    cell_pos = args[1].upper()
    new_value = " ".join(args[2:])

    print(f"\n[작업] Sheets 셀 편집")
    print(f"  시트: {sheet_name}")
    print(f"  셀: {cell_pos}")
    print(f"  값: {new_value}")

    # 시트 열기
    page.goto("https://docs.google.com/spreadsheets/u/0/", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    page.evaluate(f"""() => {{
        for (const el of document.querySelectorAll('[role="listitem"]')) {{
            if (el.textContent.includes({repr(sheet_name)})) {{
                el.click();
                break;
            }}
        }}
    }}""")
    page.wait_for_timeout(3000)

    # Ctrl+G로 셀로 이동
    page.keyboard.press("Control+g")
    page.wait_for_timeout(500)

    # 셀 위치 입력
    nav_input = page.locator('input[aria-label*="이동"], input[placeholder*="셀"]').first
    if nav_input:
        nav_input.fill(cell_pos)
        page.keyboard.press("Enter")
        page.wait_for_timeout(500)

    # 셀 값 입력
    page.keyboard.type(new_value)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1000)
    print(f"  ✓ 셀 편집 완료")

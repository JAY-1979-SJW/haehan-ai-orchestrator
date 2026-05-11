"""Google Drive 자동화"""
from __future__ import annotations

from typing import Any

from .base import task_context, page_goto, page_wait_click, page_wait_type, page_wait_visible
from scripts.config import GOOGLE_URLS


def run(task: str, args: list[str]) -> None:
    """Drive 작업 실행."""
    with task_context("google", f"drive-{task}", args) as page:
        match task:
            case "list":
                _task_list(page, args)
            case "search":
                _task_search(page, args)
            case "rename":
                _task_rename(page, args)
            case "delete":
                _task_delete(page, args)
            case "upload":
                _task_upload(page, args)
            case "download":
                _task_download(page, args)
            case "info":
                _task_info(page, args)
            case _:
                print(f"  [오류] 알 수 없는 작업: {task}")


def _task_list(page: Any, args: list[str]) -> None:
    """파일 목록."""
    folder = args[0] if args else "my-drive"
    print(f"\n[작업] Google Drive 파일 목록: {folder}")

    page_goto(page, GOOGLE_URLS["drive_home"])
    # 파일 목록 렌더 확인
    page_wait_visible(page, '[role="main"], [data-id]', timeout=20000)

    files = page.evaluate(r"""() => {
        const results = [];
        for (const el of document.querySelectorAll('[data-id][data-name]')) {
            const name = el.getAttribute('data-name');
            const type = el.querySelector('[data-type]')?.getAttribute('data-type') || '';
            if (name) results.push({name, type});
        }
        return results.slice(0, 20);
    }""")

    print(f"  파일 수: {len(files)}")
    for i, f in enumerate(files, 1):
        print(f"  [{i}] {f['name'][:50]:50s} ({f['type']})")


def _task_search(page: Any, args: list[str]) -> None:
    """파일 검색."""
    if not args:
        print("  [오류] 검색어를 입력하세요")
        return

    query = " ".join(args)
    print(f"\n[작업] Drive 검색: {query}")

    page_goto(page, GOOGLE_URLS["drive_home"])
    page_wait_visible(page, '[role="main"]', timeout=20000)

    if page_wait_type(page, 'input[aria-label*="Search"], input[placeholder*="Drive 검색"]', query):
        page.keyboard.press("Enter")
        page_wait_visible(page, '[role="main"]', timeout=10000)
        print("  ✓ 검색 완료")
    else:
        print("  ⚠  검색창 못 찾음")


def _task_rename(page: Any, args: list[str]) -> None:
    """파일명 변경."""
    if len(args) < 2:
        print("  [오류] 사용법: rename <현재명> <새이름>")
        return

    old_name, new_name = args[0], args[1]
    print(f"\n[작업] 파일명 변경: {old_name} → {new_name}")

    page_goto(page, GOOGLE_URLS["drive_home"])
    page_wait_visible(page, '[data-id]', timeout=20000)

    # 파일 우클릭
    page.evaluate(f"""() => {{
        for (const el of document.querySelectorAll('[data-name]')) {{
            if (el.getAttribute('data-name') === {repr(old_name)}) {{
                el.dispatchEvent(new MouseEvent('contextmenu', {{ bubbles: true }}));
                break;
            }}
        }}
    }}""")

    # 컨텍스트 메뉴 대기 후 이름변경 클릭
    if page_wait_visible(page, '[role="menu"]', timeout=5000):
        page_wait_click(page, '[role="menuitem"]:has-text("이름 변경"), [role="menuitem"]:has-text("Rename")')
        # 이름 입력 다이얼로그 대기
        if page_wait_visible(page, 'input[type="text"][value]', timeout=5000):
            page_wait_type(page, 'input[type="text"][value]', new_name)
            page.keyboard.press("Enter")
            page_wait_visible(page, '[data-id]', timeout=5000)
            print("  ✓ 이름 변경 완료")
        else:
            print("  ⚠  이름 입력창 못 찾음")
    else:
        print("  ⚠  컨텍스트 메뉴 못 찾음")


def _task_delete(page: Any, args: list[str]) -> None:
    """파일 삭제."""
    if not args:
        print("  [오류] 삭제할 파일명을 입력하세요")
        return

    file_name = " ".join(args)
    print(f"\n[작업] Drive 파일 삭제: {file_name}")

    page_goto(page, GOOGLE_URLS["drive_home"])
    page_wait_visible(page, '[data-id]', timeout=20000)

    page.evaluate(f"""() => {{
        for (const el of document.querySelectorAll('[data-name]')) {{
            if (el.getAttribute('data-name') === {repr(file_name)}) {{
                el.dispatchEvent(new MouseEvent('contextmenu', {{ bubbles: true }}));
                break;
            }}
        }}
    }}""")

    if page_wait_visible(page, '[role="menu"]', timeout=5000):
        page_wait_click(page, '[role="menuitem"]:has-text("삭제"), [role="menuitem"]:has-text("Delete")')
        page_wait_visible(page, '[data-id]', timeout=5000)
        print("  ✓ 삭제 완료")
    else:
        print("  ⚠  컨텍스트 메뉴 못 찾음")


def _task_upload(page: Any, args: list[str]) -> None:
    """파일 업로드."""
    if not args:
        print("  [오류] 업로드할 파일 경로를 입력하세요")
        return

    file_path = args[0]
    print(f"\n[작업] Drive 파일 업로드: {file_path}")

    page_goto(page, GOOGLE_URLS["drive_home"])
    page_wait_visible(page, '[role="main"]', timeout=20000)

    try:
        file_input = page.locator('input[type="file"]').first
        file_input.set_input_files(file_path)
        # 업로드 진행 표시 대기
        page_wait_visible(page, '[aria-label*="업로드"], [aria-label*="Upload"]', timeout=10000)
        print("  ✓ 업로드 완료")
    except Exception as e:
        print(f"  ⚠  업로드 실패: {e}")


def _task_download(page: Any, args: list[str]) -> None:
    """파일 다운로드."""
    if not args:
        print("  [오류] 다운로드할 파일명을 입력하세요")
        return

    file_name = " ".join(args)
    print(f"\n[작업] Drive 파일 다운로드: {file_name}")

    page_goto(page, GOOGLE_URLS["drive_home"])
    page_wait_visible(page, '[data-id]', timeout=20000)

    page.evaluate(f"""() => {{
        for (const el of document.querySelectorAll('[data-name]')) {{
            if (el.getAttribute('data-name') === {repr(file_name)}) {{
                el.dispatchEvent(new MouseEvent('contextmenu', {{ bubbles: true }}));
                break;
            }}
        }}
    }}""")

    if page_wait_visible(page, '[role="menu"]', timeout=5000):
        page_wait_click(page, '[role="menuitem"]:has-text("다운로드"), [role="menuitem"]:has-text("Download")')
        print("  ✓ 다운로드 요청 완료")
    else:
        print("  ⚠  컨텍스트 메뉴 못 찾음")


def _task_info(page: Any, args: list[str]) -> None:
    """저장용량 정보."""
    print("\n[작업] Drive 저장용량 정보")

    page_goto(page, GOOGLE_URLS["drive_home"])
    page_wait_visible(page, '[role="main"]', timeout=20000)

    info = page.evaluate(r"""() => {
        const storage_el = document.querySelector('[aria-label*="storage"]');
        return { total: storage_el?.textContent || 'Unknown' };
    }""")

    print(f"  저장용량: {info['total']}")

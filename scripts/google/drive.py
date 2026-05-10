"""Google Drive 자동화"""
from __future__ import annotations

from typing import Any

from .base import task_context


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

    page.goto("https://drive.google.com/drive/u/0/", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    # 파일 목록 추출
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

    page.goto("https://drive.google.com/drive/u/0/", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    # 검색
    page.evaluate(f"""() => {{
        const inp = document.querySelector('input[aria-label*="Search"]');
        if (inp) {{
            inp.focus();
            inp.value = {repr(query)};
            inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
            inp.form?.dispatchEvent(new Event('submit', {{ bubbles: true }}));
        }}
    }}""")
    page.wait_for_timeout(3000)
    print("  ✓ 검색 완료")


def _task_rename(page: Any, args: list[str]) -> None:
    """파일명 변경."""
    if len(args) < 2:
        print("  [오류] 사용법: rename <현재명> <새이름>")
        return

    old_name, new_name = args[0], args[1]
    print(f"\n[작업] 파일명 변경: {old_name} → {new_name}")

    page.goto("https://drive.google.com/drive/u/0/", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    # 파일 찾아 우클릭 → 이름 변경
    page.evaluate(f"""() => {{
        for (const el of document.querySelectorAll('[data-name]')) {{
            if (el.getAttribute('data-name') === {repr(old_name)}) {{
                el.dispatchEvent(new MouseEvent('contextmenu', {{ bubbles: true }}));
                break;
            }}
        }}
    }}""")
    page.wait_for_timeout(1000)

    # 메뉴에서 "이름 변경" 클릭
    page.evaluate(f"""() => {{
        const rename_btn = Array.from(document.querySelectorAll('div')).find(d =>
            d.textContent.includes('Rename') || d.textContent.includes('이름')
        );
        if (rename_btn) rename_btn.click();
    }}""")
    page.wait_for_timeout(1000)

    # 이름 입력
    page.evaluate(f"""() => {{
        const inp = document.querySelector('input[type="text"]');
        if (inp) {{
            inp.value = {repr(new_name)};
            inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
            inp.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', bubbles: true }}));
        }}
    }}""")
    page.wait_for_timeout(1000)
    print("  ✓ 이름 변경 완료")


def _task_delete(page: Any, args: list[str]) -> None:
    """파일 삭제."""
    if not args:
        print("  [오류] 삭제할 파일명을 입력하세요")
        return

    file_name = " ".join(args)
    print(f"\n[작업] Drive 파일 삭제: {file_name}")

    page.goto("https://drive.google.com/drive/u/0/", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    # 파일 찾아 우클릭 → 삭제
    page.evaluate(f"""() => {{
        for (const el of document.querySelectorAll('[data-name]')) {{
            if (el.getAttribute('data-name') === {repr(file_name)}) {{
                el.dispatchEvent(new MouseEvent('contextmenu', {{ bubbles: true }}));
                break;
            }}
        }}
    }}""")
    page.wait_for_timeout(1000)

    # "Delete" 클릭
    page.evaluate("""() => {
        const del_btn = Array.from(document.querySelectorAll('div')).find(d =>
            d.textContent.includes('Delete') || d.textContent.includes('삭제')
        );
        if (del_btn) del_btn.click();
    }""")
    page.wait_for_timeout(1000)
    print("  ✓ 삭제 완료")


def _task_upload(page: Any, args: list[str]) -> None:
    """파일 업로드."""
    if not args:
        print("  [오류] 업로드할 파일 경로를 입력하세요")
        return

    file_path = args[0]
    print(f"\n[작업] Drive 파일 업로드: {file_path}")

    page.goto("https://drive.google.com/drive/u/0/", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    # 파일 선택 입력 찾기 및 업로드
    try:
        file_input = page.locator('input[type="file"]').first
        file_input.set_input_files(file_path)
        page.wait_for_timeout(3000)
        print("  ✓ 업로드 완료")
    except Exception as e:
        print(f"  [경고] 업로드 실패: {e}")


def _task_download(page: Any, args: list[str]) -> None:
    """파일 다운로드."""
    if not args:
        print("  [오류] 다운로드할 파일명을 입력하세요")
        return

    file_name = " ".join(args)
    print(f"\n[작업] Drive 파일 다운로드: {file_name}")

    page.goto("https://drive.google.com/drive/u/0/", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    # 파일 찾아 클릭 → 다운로드
    page.evaluate(f"""() => {{
        for (const el of document.querySelectorAll('[data-name]')) {{
            if (el.getAttribute('data-name') === {repr(file_name)}) {{
                el.dispatchEvent(new MouseEvent('contextmenu', {{ bubbles: true }}));
                break;
            }}
        }}
    }}""")
    page.wait_for_timeout(1000)

    # "Download" 클릭
    page.evaluate("""() => {
        const dl_btn = Array.from(document.querySelectorAll('div')).find(d =>
            d.textContent.includes('Download') || d.textContent.includes('다운로드')
        );
        if (dl_btn) dl_btn.click();
    }""")
    page.wait_for_timeout(2000)
    print("  ✓ 다운로드 완료")


def _task_info(page: Any, args: list[str]) -> None:
    """저장용량 정보."""
    print("\n[작업] Drive 저장용량 정보")

    page.goto("https://drive.google.com/drive/u/0/", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    info = page.evaluate(r"""() => {
        const storage_el = document.querySelector('[aria-label*="storage"]');
        return {
            total: storage_el?.textContent || 'Unknown'
        };
    }""")

    print(f"  저장용량: {info['total']}")

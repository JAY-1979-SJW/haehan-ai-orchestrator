"""Google Docs 자동화"""
from __future__ import annotations

from typing import Any

from .base import task_context


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
    print("\n[작업] Google Docs 최근 문서")

    page.goto("https://docs.google.com/document/u/0/", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    docs = page.evaluate(r"""() => {
        const results = [];
        for (const el of document.querySelectorAll('[role="listitem"] [aria-label]')) {
            const title = el.getAttribute('aria-label') || el.textContent.trim();
            if (title && title.length > 2) results.push(title);
        }
        return results.slice(0, 10);
    }""")

    print(f"  문서 수: {len(docs)}")
    for i, doc in enumerate(docs, 1):
        print(f"  [{i}] {doc[:60]}")


def _task_new(page: Any, args: list[str]) -> None:
    """새 문서 생성."""
    print("\n[작업] Google Docs 새 문서 생성")

    page.goto("https://docs.google.com/document/create", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    print("  ✓ 새 문서 생성 완료")


def _task_search(page: Any, args: list[str]) -> None:
    """문서 검색."""
    if not args:
        print("  [오류] 검색어를 입력하세요")
        return

    query = " ".join(args)
    print(f"\n[작업] Docs 검색: {query}")

    page.goto("https://docs.google.com/document/u/0/", timeout=30000, wait_until="domcontentloaded")
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
    """문서 열기."""
    if not args:
        print("  [오류] 문서명을 입력하세요")
        return

    doc_name = " ".join(args)
    print(f"\n[작업] Docs 문서 열기: {doc_name}")

    page.goto("https://docs.google.com/document/u/0/", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    page.evaluate(f"""() => {{
        for (const el of document.querySelectorAll('[role="listitem"]')) {{
            if (el.textContent.includes({repr(doc_name)})) {{
                el.click();
                break;
            }}
        }}
    }}""")
    page.wait_for_timeout(3000)
    print("  ✓ 문서 열기 완료")


def _task_delete(page: Any, args: list[str]) -> None:
    """문서 삭제."""
    if not args:
        print("  [오류] 삭제할 문서명을 입력하세요")
        return

    doc_name = " ".join(args)
    print(f"\n[작업] Docs 문서 삭제: {doc_name}")

    page.goto("https://docs.google.com/document/u/0/", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    # 문서 찾아 우클릭 → 삭제
    page.evaluate(f"""() => {{
        for (const el of document.querySelectorAll('[role="listitem"]')) {{
            if (el.textContent.includes({repr(doc_name)})) {{
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
    print("  ✓ 문서 삭제 완료")

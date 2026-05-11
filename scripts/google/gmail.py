"""Google Gmail 자동화"""
from __future__ import annotations

from typing import Any

from .base import task_context, page_goto, page_wait_click, page_wait_type, page_wait_visible
from scripts.config import GOOGLE_URLS


def run(task: str, args: list[str]) -> None:
    """Gmail 작업 실행.

    task: list, compose, search, delete
    """
    with task_context("gmail", task, args) as page:
        match task:
            case "list":
                _task_list(page, args)
            case "compose":
                _task_compose(page, args)
            case "search":
                _task_search(page, args)
            case "delete":
                _task_delete(page, args)
            case _:
                print(f"  [오류] 알 수 없는 작업: {task}")


def _task_list(page: Any, args: list[str]) -> None:
    """메일 목록 조회."""
    folder = args[0] if args else "inbox"
    print(f"\n[작업] Gmail 메일 목록: {folder}")

    url_map = {
        "inbox":   GOOGLE_URLS["gmail_inbox"],
        "sent":    GOOGLE_URLS["gmail_sent"],
        "drafts":  GOOGLE_URLS["gmail_drafts"],
        "archive": GOOGLE_URLS["gmail_archive"],
        "trash":   GOOGLE_URLS["gmail_trash"],
    }
    url = url_map.get(folder, url_map["inbox"])

    page_goto(page, url)
    # 메일 목록 렌더 확인
    page_wait_visible(page, '[role="main"], [role="listitem"], tr[jsmodel]', timeout=20000)

    mails = page.evaluate(r"""() => {
        const rows = [];
        for (const el of document.querySelectorAll('[role="listitem"]')) {
            const from = el.querySelector('[data-senders]')?.getAttribute('data-senders') || '';
            const subject = el.querySelector('[data-subject]')?.getAttribute('data-subject') || '';
            const date = el.querySelector('[data-date-time]')?.getAttribute('data-date-time') || '';
            if (from || subject) {
                rows.push({from, subject, date});
            }
        }
        return rows.slice(0, 10);
    }""")

    print(f"  메일 수: {len(mails)}")
    for i, mail in enumerate(mails, 1):
        print(f"  [{i}] {mail['from'][:30]:30s} | {mail['subject'][:40]}")


def _task_compose(page: Any, args: list[str]) -> None:
    """메일 발송."""
    if len(args) < 3:
        print("  [오류] 사용법: compose <수신자> <제목> <본문>")
        return

    to, subject, body = args[0], args[1], " ".join(args[2:])
    print(f"\n[작업] 메일 발송: {to}")

    page_goto(page, GOOGLE_URLS["gmail_home"])
    # 작성 버튼 대기
    page_wait_visible(page, '[role="main"]', timeout=20000)

    # 작성 버튼 클릭
    if not page_wait_click(page, 'div[role="button"]:has-text("편지쓰기"), div[role="button"]:has-text("Compose")'):
        print("  ⚠  편지쓰기 버튼 못 찾음")
        return

    # 작성 폼 대기
    if not page_wait_visible(page, 'input[aria-label*="To"], input[aria-label*="받는사람"]', timeout=10000):
        print("  ⚠  작성 폼 못 열림")
        return

    # To 입력
    page_wait_type(page, 'input[aria-label*="To"], input[aria-label*="받는사람"]', to)
    page.keyboard.press("Tab")

    # Subject 입력
    page_wait_type(page, 'input[aria-label*="Subject"], input[name*="subject"]', subject)

    # Body 입력
    if page_wait_visible(page, 'div[contenteditable="true"]', timeout=5000):
        page.evaluate(f"""() => {{
            const editor = document.querySelector('div[contenteditable="true"]');
            if (editor) {{
                editor.focus();
                editor.textContent = {repr(body)};
                editor.dispatchEvent(new Event('input', {{ bubbles: true }}));
            }}
        }}""")

    # 발송 버튼 클릭
    if page_wait_click(page, 'button:has-text("보내기"), button[aria-label*="Send"], button[aria-label*="보내기"]'):
        # 전송 완료 후 메인 화면 복귀 대기
        page_wait_visible(page, '[role="main"]', timeout=10000)
        print("  ✓ 발송 완료")
    else:
        print("  ⚠  보내기 버튼 못 찾음")


def _task_search(page: Any, args: list[str]) -> None:
    """메일 검색."""
    if not args:
        print("  [오류] 검색어를 입력하세요")
        return

    query = " ".join(args)
    print(f"\n[작업] Gmail 검색: {query}")

    page_goto(page, GOOGLE_URLS["gmail_home"])
    page_wait_visible(page, '[role="main"]', timeout=20000)

    # 검색창 입력
    if page_wait_type(page, 'input[placeholder*="Search"], input[aria-label*="검색"]', query):
        page.keyboard.press("Enter")
        # 검색 결과 대기
        page_wait_visible(page, '[role="main"]', timeout=10000)
        print("  ✓ 검색 완료")
    else:
        print("  ⚠  검색창 못 찾음")


def _task_delete(page: Any, args: list[str]) -> None:
    """메일 삭제."""
    if not args:
        print("  [오류] 삭제할 메일 번호를 입력하세요")
        return

    num = int(args[0])
    print(f"\n[작업] Gmail 메일 삭제: #{num}")

    page_goto(page, GOOGLE_URLS["gmail_inbox"])
    page_wait_visible(page, '[role="main"]', timeout=20000)

    # n번째 메일 클릭
    page.evaluate(f"""() => {{
        const items = document.querySelectorAll('[role="listitem"]');
        if (items[{num - 1}]) items[{num - 1}].click();
    }}""")

    # 메일 열림 대기
    page_wait_visible(page, '[role="article"], [data-message-id]', timeout=10000)

    # 삭제 버튼 클릭
    if page_wait_click(page, 'button[aria-label*="Delete"], button[aria-label*="삭제"], button[title*="Delete"]'):
        page_wait_visible(page, '[role="main"]', timeout=5000)
        print("  ✓ 삭제 완료")
    else:
        print("  ⚠  삭제 버튼 못 찾음")

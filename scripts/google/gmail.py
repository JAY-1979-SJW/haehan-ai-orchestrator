"""Google Gmail 자동화"""
from __future__ import annotations

from typing import Any

from .base import task_context


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
    """메일 목록 조회 (받은편지함 기본)."""
    folder = args[0] if args else "inbox"
    print(f"\n[작업] Gmail 메일 목록: {folder}")

    url_map = {
        "inbox": "https://mail.google.com/mail/u/0/#inbox",
        "sent": "https://mail.google.com/mail/u/0/#sent",
        "drafts": "https://mail.google.com/mail/u/0/#drafts",
        "archive": "https://mail.google.com/mail/u/0/#all",
        "trash": "https://mail.google.com/mail/u/0/#trash",
    }
    url = url_map.get(folder, url_map["inbox"])

    page.goto(url, timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    # 메일 목록 추출
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

    page.goto("https://mail.google.com/mail/u/0/#compose", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    # To 입력
    page.evaluate(f"""() => {{
        const inp = document.querySelector('input[aria-label*="To"]') ||
                   document.querySelector('input[placeholder*="To"]');
        if (inp) {{
            inp.focus();
            inp.value = {repr(to)};
            inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
        }}
    }}""")
    page.wait_for_timeout(500)

    # Subject 입력
    page.evaluate(f"""() => {{
        const inp = document.querySelector('input[aria-label*="Subject"]') ||
                   document.querySelector('input[name*="subject"]');
        if (inp) {{
            inp.focus();
            inp.value = {repr(subject)};
            inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
        }}
    }}""")
    page.wait_for_timeout(500)

    # Body 입력
    page.evaluate(f"""() => {{
        const editor = document.querySelector('div[contenteditable="true"]');
        if (editor) {{
            editor.focus();
            editor.textContent = {repr(body)};
            editor.dispatchEvent(new Event('input', {{ bubbles: true }}));
        }}
    }}""")
    page.wait_for_timeout(500)

    # 발송 버튼 클릭
    page.evaluate("""() => {
        const btn = Array.from(document.querySelectorAll('button')).find(b =>
            b.textContent.includes('Send') || b.getAttribute('aria-label')?.includes('Send')
        );
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(2000)
    print("  ✓ 발송 완료")


def _task_search(page: Any, args: list[str]) -> None:
    """메일 검색."""
    if not args:
        print("  [오류] 검색어를 입력하세요")
        return

    query = " ".join(args)
    print(f"\n[작업] Gmail 검색: {query}")

    page.goto("https://mail.google.com/mail/u/0/", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    # 검색창 입력
    page.evaluate(f"""() => {{
        const inp = document.querySelector('input[placeholder*="Search"]');
        if (inp) {{
            inp.focus();
            inp.value = {repr(query)};
            inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
            inp.parentElement.querySelector('button')?.click();
        }}
    }}""")
    page.wait_for_timeout(3000)
    print("  ✓ 검색 완료")


def _task_delete(page: Any, args: list[str]) -> None:
    """메일 삭제."""
    if not args:
        print("  [오류] 삭제할 메일 번호를 입력하세요")
        return

    num = int(args[0])
    print(f"\n[작업] Gmail 메일 삭제: #{num}")

    page.goto("https://mail.google.com/mail/u/0/#inbox", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    # n번째 메일 선택 후 삭제
    page.evaluate(f"""() => {{
        const items = document.querySelectorAll('[role="listitem"]');
        if (items[{num - 1}]) {{
            items[{num - 1}].click();
        }}
    }}""")
    page.wait_for_timeout(1000)

    # 삭제 버튼
    page.evaluate("""() => {
        const btn = Array.from(document.querySelectorAll('button')).find(b =>
            b.getAttribute('aria-label')?.includes('Delete') ||
            b.title.includes('Delete')
        );
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(1000)
    print("  ✓ 삭제 완료")

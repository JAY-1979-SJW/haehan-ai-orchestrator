"""Safe Gmail CLI adapter.

The Gmail router may read, search, or fill a compose draft. It must not click
final Send/Delete controls. Final state-changing work belongs to the approved
Google workflow path.
"""
from __future__ import annotations

from typing import Any

from scripts.common.config import GOOGLE_URLS

from scripts.google.common import gmail_analysis
from scripts.google.common.base import task_context, page_goto, page_wait_type, page_wait_visible


def run(task: str, args: list[str]) -> None:
    """Run a safe Gmail task."""
    with task_context("gmail", task, args) as page:
        match task:
            case "list":
                _task_list(page, args)
            case "compose" | "send":
                _task_compose_draft(page, args)
            case "search":
                _task_search(page, args)
            case "analyze":
                _task_analyze(page, args)
            case "delete":
                print("  [blocked] Gmail delete is disabled in automation; use approval-gated user flow.")
            case _:
                print(f"  [error] unknown Gmail task: {task}")


def _task_list(page: Any, args: list[str]) -> None:
    folder = args[0] if args else "inbox"
    print(f"\n[task] Gmail list: {folder}")
    url_map = {
        "inbox": GOOGLE_URLS["gmail_inbox"],
        "sent": GOOGLE_URLS["gmail_sent"],
        "drafts": GOOGLE_URLS["gmail_drafts"],
        "archive": GOOGLE_URLS["gmail_archive"],
        "trash": GOOGLE_URLS["gmail_trash"],
    }
    page_goto(page, url_map.get(folder, url_map["inbox"]))
    page_wait_visible(page, '[role="main"], [role="listitem"], tr.zA', timeout=20000)
    rows = page.evaluate(
        r"""() => {
            const out = [];
            for (const row of document.querySelectorAll('tr.zA, [role="listitem"]')) {
                const fromEl = row.querySelector('.yW span[name], .zF, [data-senders]');
                const subjectEl = row.querySelector('.y6 span:not(.T3), [data-subject]');
                const dateEl = row.querySelector('.xW span, td.xW, [data-date-time]');
                const from = fromEl?.getAttribute('name') || fromEl?.getAttribute('data-senders') || fromEl?.innerText || '';
                const subject = subjectEl?.getAttribute('data-subject') || subjectEl?.innerText || '';
                const date = dateEl?.getAttribute('title') || dateEl?.getAttribute('data-date-time') || dateEl?.innerText || '';
                if (from || subject) out.push({from: from.slice(0, 80), subject: subject.slice(0, 120), date});
                if (out.length >= 10) break;
            }
            return out;
        }"""
    )
    print(f"  visible_messages: {len(rows)}")
    for index, row in enumerate(rows, 1):
        has_sender = "yes" if row.get("from") else "no"
        has_subject = "yes" if row.get("subject") else "no"
        print(f"  [{index}] sender_present={has_sender} subject_present={has_subject}")


def _task_compose_draft(page: Any, args: list[str]) -> None:
    if len(args) < 3:
        print("  [error] usage: compose <to> <subject> <body>")
        return
    to, subject, body = args[0], args[1], " ".join(args[2:])
    print("\n[task] Gmail compose draft")
    page_goto(page, GOOGLE_URLS["gmail_home"])
    page_wait_visible(page, '[role="main"]', timeout=20000)
    _open_compose(page)
    _fill_recipient(page, to)
    _fill_subject(page, subject)
    _fill_body(page, body)
    print("  [safe] draft filled; final Send was not clicked.")


def _task_search(page: Any, args: list[str]) -> None:
    if not args:
        print("  [error] search query is required")
        return
    query = " ".join(args)
    print(f"\n[task] Gmail search: {query[:80]}")
    page_goto(page, GOOGLE_URLS["gmail_home"])
    page_wait_visible(page, '[role="main"]', timeout=20000)
    if page_wait_type(page, _gmail_search_selector(), query):
        page.keyboard.press("Enter")
        page_wait_visible(page, '[role="main"]', timeout=10000)
        print("  [ok] search submitted")
    else:
        print("  [warn] search input not found")


def _task_analyze(page: Any, args: list[str]) -> None:
    index = 0
    if args:
        try:
            index = max(0, int(args[0]))
        except ValueError:
            print("  [error] usage: analyze [zero_based_mail_index]")
            return
    result, path = gmail_analysis.analyze_visible_message(page, index)
    gmail_analysis.print_analysis_summary(result, path)


def _open_compose(page: Any) -> None:
    clicked = page.evaluate(
        """() => {
            for (const el of document.querySelectorAll('div[role="button"], button')) {
                const text = (el.innerText || '').trim();
                const aria = (el.getAttribute('aria-label') || '').trim();
                if (text.includes('Compose') || aria.includes('Compose')) {
                    const box = el.getBoundingClientRect();
                    if (box.width > 0 && box.height > 0) {
                        el.click();
                        return true;
                    }
                }
            }
            return false;
        }"""
    )
    if not clicked:
        raise RuntimeError("Gmail compose control not found")


def _fill_recipient(page: Any, value: str) -> None:
    selector = 'textarea[name="to"], div[name="to"] input[type="text"], input[aria-label*="To"]'
    if not page_wait_type(page, selector, value):
        raise RuntimeError("Gmail recipient field not found")
    page.keyboard.press("Enter")


def _fill_subject(page: Any, value: str) -> None:
    if not page_wait_type(page, 'input[name="subjectbox"], input[aria-label*="Subject"]', value):
        raise RuntimeError("Gmail subject field not found")


def _fill_body(page: Any, value: str) -> None:
    focused = page.evaluate(
        """() => {
            const editor = document.querySelector('div[contenteditable="true"][role="textbox"], div[contenteditable="true"]');
            if (!editor) return false;
            editor.focus();
            return true;
        }"""
    )
    if not focused:
        raise RuntimeError("Gmail body field not found")
    page.keyboard.type(value, delay=5)


def _gmail_search_selector() -> str:
    return (
        'input[name="q"], '
        'input[placeholder*="Search"], input[placeholder*="검색"], '
        'input[aria-label*="Search"], input[aria-label*="search"], input[aria-label*="검색"], '
        'input[type="search"], input[type="text"][role="combobox"]'
    )

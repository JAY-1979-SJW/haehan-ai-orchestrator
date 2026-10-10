"""Bounded tab lifecycle helpers for CDP browser tasks.

The project runs many browser automations through one Chrome DevTools
connection. This module keeps that model, but makes tab ownership explicit:
reuse a matching tab first, create a new tab only when needed, and clean only
the tabs that belong to the finished task.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

BLANK_URLS = {"", "about:blank", "chrome://newtab/"}
DEFAULT_MAX_TOTAL_TABS = 6


class BrowserTaskTabLimitError(RuntimeError):
    """Raised when a browser task would create more tabs than policy allows."""


@dataclass(frozen=True)
class BrowserTaskPolicy:
    task_id: str
    allowed_hosts: tuple[str, ...] = ()
    url_patterns: tuple[str, ...] = ()
    start_url: str | None = None
    max_tabs: int = 1
    max_total_tabs: int = DEFAULT_MAX_TOTAL_TABS
    close_blank_tabs: bool = True


def normalize_host(host: str) -> str:
    return host.lower().strip().strip(".")


def host_from_url(url: str) -> str:
    try:
        return normalize_host(urlparse(url).hostname or "")
    except Exception:  # noqa: BLE001 - 브라우저 탭/페이지 소유권 관리 유틸 - URL 조회/탭 정리 실패 시 빈 문자열 또는 무시로 폴백
        return ""


def host_matches(host: str, allowed_hosts: Iterable[str]) -> bool:
    clean = normalize_host(host)
    for allowed in allowed_hosts:
        suffix = normalize_host(allowed)
        if clean == suffix or clean.endswith("." + suffix):
            return True
    return False


def page_url(page: Any) -> str:
    try:
        return str(page.url or "")
    except Exception:  # noqa: BLE001 - 브라우저 탭/페이지 소유권 관리 유틸 - URL 조회/탭 정리 실패 시 빈 문자열 또는 무시로 폴백
        return ""


def is_blank_page(page: Any) -> bool:
    return page_url(page) in BLANK_URLS


def page_matches_policy(page: Any, policy: BrowserTaskPolicy) -> bool:
    url = page_url(page)
    if not url or url in BLANK_URLS:
        return False
    if policy.url_patterns and any(pattern in url for pattern in policy.url_patterns if pattern):
        return True
    if policy.allowed_hosts and host_matches(host_from_url(url), policy.allowed_hosts):
        return True
    return False


def select_reusable_page(pages: Iterable[Any], policy: BrowserTaskPolicy) -> Any | None:
    matching = [page for page in pages if page_matches_policy(page, policy)]
    return matching[-1] if matching else None


def mark_task_owned(page: Any, policy: BrowserTaskPolicy, *, owned: bool) -> None:
    try:
        setattr(page, "_haehan_task_id", policy.task_id)
        setattr(page, "_haehan_task_owned_page", owned)
    except Exception:  # noqa: BLE001 - 브라우저 탭/페이지 소유권 관리 유틸 - URL 조회/탭 정리 실패 시 빈 문자열 또는 무시로 폴백
        pass


def get_or_create_task_page(context: Any, policy: BrowserTaskPolicy) -> Any:
    """Return one page for a task, reusing matching pages before creating one."""
    pages = list(getattr(context, "pages", []))
    reusable = select_reusable_page(pages, policy)
    if reusable is not None:
        mark_task_owned(reusable, policy, owned=False)
        return reusable

    reusable_blank = next((page for page in pages if is_blank_page(page)), None)
    if reusable_blank is not None and policy.start_url:
        reusable_blank.goto(policy.start_url, timeout=30000)
        mark_task_owned(reusable_blank, policy, owned=True)
        return reusable_blank

    if policy.max_total_tabs > 0 and len(pages) >= policy.max_total_tabs:
        raise BrowserTaskTabLimitError(
            f"Browser already has {len(pages)} tab(s); max total allowed is {policy.max_total_tabs}. "
            "Reuse an existing task tab or clean up surplus tabs before creating another."
        )

    page = context.new_page()
    mark_task_owned(page, policy, owned=True)
    if policy.start_url:
        page.goto(policy.start_url, timeout=30000)
    return page


def cleanup_task_pages(context: Any, policy: BrowserTaskPolicy, *, keep_page: Any | None = None) -> dict[str, int]:
    """Close task-owned surplus, duplicate, and blank tabs after a task ends."""
    closed = 0
    kept = 0
    for page in list(getattr(context, "pages", [])):
        should_close = False
        if keep_page is not None and page is keep_page:
            kept += 1
            continue
        if policy.close_blank_tabs and is_blank_page(page):
            should_close = True
        elif bool(getattr(page, "_haehan_task_owned_page", False)):
            should_close = True
        elif page_matches_policy(page, policy):
            if kept >= max(1, policy.max_tabs):
                should_close = True
            else:
                kept += 1

        if not should_close:
            continue
        try:
            page.close()
            closed += 1
        except Exception:  # noqa: BLE001 - 브라우저 탭/페이지 소유권 관리 유틸 - URL 조회/탭 정리 실패 시 빈 문자열 또는 무시로 폴백
            pass
    return {"closed": closed, "kept": kept}


def close_all_pages(context: Any) -> int:
    """Close every page in a browser context for full browser shutdown."""
    closed = 0
    for page in list(getattr(context, "pages", [])):
        try:
            page.close()
            closed += 1
        except Exception:  # noqa: BLE001 - 브라우저 탭/페이지 소유권 관리 유틸 - URL 조회/탭 정리 실패 시 빈 문자열 또는 무시로 폴백
            pass
    return closed

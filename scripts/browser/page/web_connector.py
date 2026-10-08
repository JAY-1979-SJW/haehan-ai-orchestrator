"""웹 접속 모듈 — 도메인/태스크 단위 탭 관리(연결 자체는 scripts/browser/cdp/connection.py).

모든 웹 자동화 스크립트의 브라우저 연결 진입점.

사용법:
    from scripts.browser.cdp.connection import open_page, close_page
    from scripts.browser.page.web_connector import browser_session

    # 단건
    page = open_page(allow_new_tab=True, reason="manual-single")
    ...
    close_page(page)

    # 컨텍스트 매니저
    with browser_session() as page:
        page_goto(page, "https://...")
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import Page

from ai_orchestrator.paths.runtime import data_dir
from scripts.browser.cdp.connection import _connect_browser, close_page, fit_viewport, get_page, open_page
from scripts.browser.session.browser_sandbox_gate import assert_browser_launch_allowed
from scripts.browser.session.browser_task_session import (
    BrowserTaskPolicy,
    cleanup_task_pages,
    get_or_create_task_page,
    mark_task_owned,
)
from scripts.common.logger import get_logger

log = get_logger(__name__)


def get_page_by_url(*patterns: str, create_url: str | None = None) -> Page:
    """Return an existing CDP page whose URL contains one of the patterns.

    This avoids mixing independent tabs such as EUM and Hiworks when both are
    open in the same browser context.
    """
    _, ctx = _connect_browser()
    needles = [p for p in patterns if p]
    for page in reversed(ctx.pages):
        url = page.url or ""
        if needles and any(needle in url for needle in needles):
            log.debug("URL matched page: %s", url)
            return page
    if create_url:
        page = ctx.new_page()
        mark_task_owned(page, BrowserTaskPolicy(task_id="get-page-by-url", start_url=create_url), owned=True)
        page.goto(create_url, timeout=30000)
        return page
    return get_page()


def _host_key(url: str) -> str:
    """URL에서 도메인 키 추출(www. 정규화). 예: https://www.naver.com/x → naver.com"""
    from urllib.parse import urlparse

    try:
        host = (urlparse(url).netloc or "").lower()
    except Exception:  # noqa: BLE001 - CDP 브라우저 연결/탭 관리 공용 커넥터 — 연결 실패는 캐시 초기화 후 재시도, 뷰포트/창위치 설정 실패는 비치명적이라 로그만, 종료 처리는 이미 닫히는 중이라 무시해도 안전(2026-09-28 검토)
        host = ""
    return host[4:] if host.startswith("www.") else host


def get_domain_page(url: str) -> Page:
    """동일 도메인은 하나의 탭만 — 같은 호스트 탭이 있으면 재사용, 없으면 새 탭.

    AI 브라우저 작업이 사이트를 열 때 같은 도메인 탭이 중복 생성되지 않게 한다.
    (예: 네이버를 두 번 열어도 네이버 탭은 1개. 스토어/EUM 등 다른 도메인은 각자 탭.)
    """
    _, ctx = _connect_browser()
    key = _host_key(url)
    if key:
        for page in ctx.pages:
            try:
                if _host_key(page.url or "") == key:
                    mark_task_owned(page, BrowserTaskPolicy(task_id="get-domain-page"), owned=False)
                    fit_viewport(page)
                    log.debug("동일 도메인 탭 재사용: %s", page.url)
                    return page
            except Exception:  # noqa: BLE001 - CDP 브라우저 연결/탭 관리 공용 커넥터 — 연결 실패는 캐시 초기화 후 재시도, 뷰포트/창위치 설정 실패는 비치명적이라 로그만, 종료 처리는 이미 닫히는 중이라 무시해도 안전(2026-09-28 검토)
                continue
    # 같은 도메인 탭 없음 → 새 탭(단, 빈 about:blank 탭이 있으면 그것을 사용)
    blank = next((p for p in ctx.pages if (p.url or "") in ("about:blank", "")), None)
    page = blank or ctx.new_page()
    mark_task_owned(page, BrowserTaskPolicy(task_id="get-domain-page", start_url=url), owned=True)
    fit_viewport(page)
    log.debug("동일 도메인 탭 없음 → 새 탭: %s", url)
    return page


def get_task_page(
    *,
    task_id: str,
    allowed_hosts: tuple[str, ...] = (),
    url_patterns: tuple[str, ...] = (),
    start_url: str | None = None,
    max_tabs: int = 1,
) -> Page:
    """Return the bounded tab for a task, creating at most one when needed."""
    _, ctx = _connect_browser()
    policy = BrowserTaskPolicy(
        task_id=task_id,
        allowed_hosts=allowed_hosts,
        url_patterns=url_patterns,
        start_url=start_url,
        max_tabs=max_tabs,
    )
    page = get_or_create_task_page(ctx, policy)
    fit_viewport(page)
    return page


def cleanup_task_tabs(
    *,
    task_id: str,
    allowed_hosts: tuple[str, ...] = (),
    url_patterns: tuple[str, ...] = (),
    keep_page: Page | None = None,
    max_tabs: int = 1,
) -> dict[str, int]:
    """Clean task-owned, duplicate, and blank tabs after a CDP task."""
    _, ctx = _connect_browser()
    policy = BrowserTaskPolicy(
        task_id=task_id,
        allowed_hosts=allowed_hosts,
        url_patterns=url_patterns,
        max_tabs=max_tabs,
    )
    return cleanup_task_pages(ctx, policy, keep_page=keep_page)


@contextmanager
def browser_session() -> Generator[Page]:
    """CDP 페이지를 컨텍스트 매니저로 제공.

    with browser_session() as page:
        page_goto(page, url)
    """
    page = open_page(allow_new_tab=True, reason="browser-session")
    try:
        yield page
    finally:
        close_page(page)


# ── Persistent Context (세션 저장/복원) ──────────────────────────────


@contextmanager
def browser_task_session(
    *,
    task_id: str,
    allowed_hosts: tuple[str, ...] = (),
    url_patterns: tuple[str, ...] = (),
    start_url: str | None = None,
    max_tabs: int = 1,
) -> Generator[Page]:
    """Yield one bounded task tab and clean task-owned tabs on exit."""
    page = get_task_page(
        task_id=task_id,
        allowed_hosts=allowed_hosts,
        url_patterns=url_patterns,
        start_url=start_url,
        max_tabs=max_tabs,
    )
    try:
        yield page
    finally:
        cleanup_task_tabs(
            task_id=task_id,
            allowed_hosts=allowed_hosts,
            url_patterns=url_patterns,
            keep_page=page,
            max_tabs=max_tabs,
        )


SESSION_BASE_DIR = data_dir() / "browser_sessions"


def session_dir(name: str) -> Path:
    """세션 디렉터리 경로 반환."""
    return SESSION_BASE_DIR / name


@contextmanager
def persistent_session(
    name: str,
    headless: bool = False,
) -> Generator[tuple]:
    """세션을 유지하는 Playwright persistent context 제공.

    with persistent_session("ai_assistant") as (ctx, page):
        page.goto("https://www.naver.com/")

    - user_data_dir 기반으로 쿠키/세션 자동 저장/복원
    - 종료 시 storage_state 자동 저장
    """
    from playwright.sync_api import sync_playwright

    s_dir = session_dir(name)
    s_dir.mkdir(parents=True, exist_ok=True)
    storage_path = s_dir / "state.json"

    with sync_playwright() as p:
        assert_browser_launch_allowed(component="scripts.web_connector", action="playwright_persistent_context")
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(s_dir),
            headless=headless,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.new_page()
        log.debug("persistent_session 시작: name=%s headless=%s", name, headless)
        try:
            yield ctx, page
        finally:
            try:
                ctx.storage_state(path=str(storage_path))
                log.debug("세션 저장 완료: %s", storage_path)
            except Exception as e:  # noqa: BLE001 - CDP 브라우저 연결/탭 관리 공용 커넥터 — 연결 실패는 캐시 초기화 후 재시도, 뷰포트/창위치 설정 실패는 비치명적이라 로그만, 종료 처리는 이미 닫히는 중이라 무시해도 안전(2026-09-28 검토)
                log.debug("세션 저장 실패: %s", e)
            ctx.close()

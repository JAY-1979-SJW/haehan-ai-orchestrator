"""웹 접속 모듈 — CDP 브라우저 연결 전담.

모든 웹 자동화 스크립트의 브라우저 연결 진입점.

사용법:
    from scripts.web_connector import open_page, close_page, browser_session

    # 단건
    page = open_page()
    ...
    close_page(page)

    # 컨텍스트 매니저
    with browser_session() as page:
        page_goto(page, "https://...")
"""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
_DAEMON_STATE = ROOT / "data" / "cdp_daemon_state.json"

import sys
sys.path.insert(0, str(ROOT))
from scripts.config import CDP_HOST as _DEFAULT_CDP_HOST, CDP_PORT as _DEFAULT_CDP_PORT  # noqa: E402
from scripts.logger import get_logger  # noqa: E402

log = get_logger(__name__)

# ── 브라우저 context 캐싱 ────────────────────────────────────────────
_BROWSER_CONTEXT_CACHE = None
_BROWSER_CACHE = None


def _get_cdp_port() -> int:
    """cdp_daemon_state.json에서 CDP 포트 읽기."""
    if not _DAEMON_STATE.exists():
        raise RuntimeError(
            "CDP 데몬이 실행 중이지 않습니다. "
            "'python scripts/cdp_daemon.py start' 실행하세요"
        )
    state = json.loads(_DAEMON_STATE.read_text(encoding="utf-8"))
    return state.get("cdp_port", _DEFAULT_CDP_PORT)


def _connect_browser():
    """CDP 브라우저에 연결해 (browser, context) 반환.

    context를 캐싱해서 여러 번 호출해도 같은 context를 반환합니다.
    """
    global _BROWSER_CONTEXT_CACHE, _BROWSER_CACHE

    # 캐시된 context가 있으면 재사용
    if _BROWSER_CONTEXT_CACHE is not None:
        return _BROWSER_CACHE, _BROWSER_CONTEXT_CACHE
    port = _get_cdp_port()
    log.debug("CDP 연결 시도: port=%s", port)

    p = sync_playwright().start()
    browser = p.chromium.connect_over_cdp(f"http://{_DEFAULT_CDP_HOST}:{port}")

    ctx = None
    for _ in range(10):
        if browser.contexts:
            ctx = browser.contexts[0]
            break
        time.sleep(1)

    if not ctx:
        log.error("CDP 브라우저 컨텍스트 생성 실패")
        raise RuntimeError("CDP 브라우저 컨텍스트 생성 실패")

    # 캐싱 (전역 변수 업데이트)
    globals()['_BROWSER_CACHE'] = browser
    globals()['_BROWSER_CONTEXT_CACHE'] = ctx
    log.debug("브라우저 context 캐싱 완료")

    return browser, ctx


def open_page() -> Page:
    """CDP 브라우저에 연결해 새 페이지 반환."""
    _, ctx = _connect_browser()
    page = ctx.new_page()
    log.debug("새 페이지 생성 완료")
    return page


def get_page() -> Page:
    """CDP 브라우저의 기존 탭을 재사용. 없으면 새 탭 생성.

    open_page()와 달리 매번 새 탭을 만들지 않는다.
    여러 단계에 걸쳐 같은 탭을 유지해야 할 때 사용.
    """
    _, ctx = _connect_browser()
    pages = ctx.pages
    # about:blank 가 아닌 기존 탭 우선 재사용
    active = [p for p in pages if p.url not in ("about:blank", "")]
    if active:
        page = active[-1]
        log.debug("기존 탭 재사용: %s", page.url)
        return page
    # 탭이 없거나 모두 blank면 새 탭 생성
    page = ctx.new_page()
    log.debug("새 페이지 생성 완료")
    return page


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
        page.goto(create_url, timeout=30000)
        return page
    return get_page()


def close_page(page: Page) -> None:
    """페이지 닫기."""
    try:
        page.close()
        log.debug("페이지 닫힘")
    except Exception as e:
        log.debug("페이지 닫기 무시: %s", e)


@contextmanager
def browser_session() -> Generator[Page, None, None]:
    """CDP 페이지를 컨텍스트 매니저로 제공.

    with browser_session() as page:
        page_goto(page, url)
    """
    page = open_page()
    try:
        yield page
    finally:
        close_page(page)


# ── Persistent Context (세션 저장/복원) ──────────────────────────────

SESSION_BASE_DIR = ROOT / "data" / "browser_sessions"


def session_dir(name: str) -> Path:
    """세션 디렉터리 경로 반환."""
    return SESSION_BASE_DIR / name


@contextmanager
def persistent_session(
    name: str,
    headless: bool = False,
) -> Generator[tuple, None, None]:
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
            except Exception as e:
                log.debug("세션 저장 실패: %s", e)
            ctx.close()

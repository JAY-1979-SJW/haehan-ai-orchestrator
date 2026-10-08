"""page_helper 네비게이션 헬퍼 — goto / wait_visible / wait_nav."""

from __future__ import annotations

from playwright.sync_api import Page

from scripts.browser.page.page_helper_common import (
    _find_frame,
    _safe_auto_login_detect,
    _safe_auto_popup,
    _safe_critical_log,
)
from scripts.common.logger import get_logger

log = get_logger(__name__)


def page_goto(page: Page, url: str, timeout: int = 30000) -> None:
    """이동 → domcontentloaded → 팝업 처리 → 중요사이트 로깅 → 로그인 상태 감지."""
    log.debug("goto: %s", url)
    page.goto(url, timeout=timeout, wait_until="domcontentloaded")
    _safe_auto_popup(page)
    _safe_critical_log(url)
    _safe_auto_login_detect(page, url)


def page_goto_wait(page: Page, url: str, selector: str, timeout: int = 20000) -> bool:
    """이동 후 목표 요소 등장 → 팝업 처리 → 중요사이트 로깅 → 로그인 상태 감지."""
    log.debug("goto_wait: %s | %s", url, selector)
    page.goto(url, timeout=30000, wait_until="domcontentloaded")
    _safe_auto_popup(page)
    _safe_critical_log(url)
    _safe_auto_login_detect(page, url)
    return page_wait_visible(page, selector, timeout=timeout)


def page_wait_visible(page: Page, selector: str, timeout: int = 20000) -> bool:
    """요소 등장 대기. 메인 프레임 실패 시 iframe 자동 탐색."""
    log.debug("wait_visible: %s", selector)
    try:
        page.wait_for_selector(selector, timeout=timeout, state="visible")
        log.debug("visible OK: %s", selector)
        return True
    except Exception:  # noqa: BLE001 - 브라우저 자동화 헬퍼(요소 가시성 확인·URL 패턴 대기) — 실패 시 대체 탐색(iframe) 시도 또는 False 반환하는 best-effort 판정, 승인/차단 로직 아님, 실제 클릭·제출 없음
        pass

    # iframe 탐색 fallback
    frame, el = _find_frame(page, selector)
    if el:
        log.debug("visible OK (iframe): %s", selector)
        return True
    log.warn("visible 타임아웃: %s", selector)
    return False


def page_wait_nav(page: Page, url_pattern: str, timeout: int = 20000) -> bool:
    """URL 패턴 전환 대기."""
    log.debug("wait_nav: %s", url_pattern)
    try:
        page.wait_for_url(url_pattern, timeout=timeout)
        log.debug("nav OK: %s", url_pattern)
        return True
    except Exception:  # noqa: BLE001 - 브라우저 자동화 헬퍼(요소 가시성 확인·URL 패턴 대기) — 실패 시 대체 탐색(iframe) 시도 또는 False 반환하는 best-effort 판정, 승인/차단 로직 아님, 실제 클릭·제출 없음
        log.warn("nav 타임아웃: %s", url_pattern)
        return False

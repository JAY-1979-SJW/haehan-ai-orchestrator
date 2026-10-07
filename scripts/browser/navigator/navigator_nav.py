"""navigator_nav — 페이지 이동 및 로그인 감지."""

from __future__ import annotations

import time

from scripts.browser.navigator.navigator_common import resolve
from scripts.browser.cdp.connection import get_page
from scripts.common.logger import get_logger
from scripts.auth.login_check import is_logged_in_by_cookie
from scripts.common.op_log import log_op

_log = get_logger(__name__)


def goto(target: str, timeout_ms: int = 60000, auto_scan: bool = True, handle_popups: bool = True) -> None:
    """대상 페이지로 활성 탭 이동. 탭은 닫지 않고 그대로 둠. 성공 시 자동 scan_page().

    Args:
        target: 별칭 또는 URL
        timeout_ms: 페이지 로드 타임아웃
        auto_scan: 이동 후 페이지 스캔 실행 여부
        handle_popups: 페이지 진입 시 팝업 자동 처리 여부
    """
    url = resolve(target)
    print("=" * 60)
    print(f"페이지 전환: {target} → {url}")
    print("=" * 60)
    _log.info("goto: %s → %s", target, url)
    t0 = time.perf_counter()
    page = get_page()
    page.goto(url, timeout=timeout_ms)
    elapsed = int((time.perf_counter() - t0) * 1000)
    print(f"✓ 이동 완료: {page.url}")
    log_op("goto", ok=True, duration_ms=elapsed, target=target, url=url)

    # 팝업 자동 처리
    if handle_popups:
        try:
            from scripts.browser.popup.popup_detector import handle_page_popups

            result = handle_page_popups(page)
            if result.get("had_popup"):
                print(f"✓ 팝업 처리 완료 ({result.get('popups_closed')}개)")
        except Exception as e:  # noqa: BLE001 - 페이지 이동 후 팝업 자동 처리 best-effort — 팝업 처리 실패해도 경고만 출력하고 이후 네비게이션/스캔 로직은 계속 진행.
            print(f"⚠️  팝업 처리 실패: {e}")

    print("=" * 60)
    if auto_scan:
        from scripts.browser.navigator.navigator_scan import scan_page

        scan_page()


def wait_login(site: str, timeout_s: int = 300, interval_s: int = 3) -> bool:
    """사이트 로그인 완료를 폴링으로 감지. 완료 시 True, 타임아웃 시 False."""
    print("=" * 60)
    print(f"로그인 감지 대기: {site} (최대 {timeout_s}초, {interval_s}초 간격)")
    print("=" * 60)
    _log.info("wait_login: site=%s timeout=%ss", site, timeout_s)
    t0 = time.time()
    page = get_page()
    deadline = t0 + timeout_s
    elapsed = 0
    while time.time() < deadline:
        if is_logged_in_by_cookie(page, site):
            print(f"✓ 로그인 감지됨 ({elapsed}초 경과)")
            print("=" * 60)
            log_op("wait_login", ok=True, duration_ms=int(elapsed * 1000), site=site)
            return True
        time.sleep(interval_s)
        elapsed += interval_s
        if elapsed % 30 == 0:
            print(f"  대기 중... {elapsed}초 경과")
    print(f"✗ 타임아웃 — {timeout_s}초 내 로그인 감지 안 됨")
    print("=" * 60)
    log_op("wait_login", ok=False, duration_ms=int(timeout_s * 1000), message="타임아웃", site=site)
    return False

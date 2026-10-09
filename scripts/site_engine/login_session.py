"""로그인 세션 모듈 — 사이트별 로그인 상태 확인 및 자동 로그인.

모든 웹 자동화 스크립트에서 공통으로 사용.

사용법:
    from scripts.site_engine.login_session import ensure_login, is_logged_in

    # 로그인 확인 후 미로그인이면 바로 자동 로그인(저장된 자격증명). 실패·추가 인증이면 최대 5분 대기
    ensure_login(page, "google")
    ensure_login(page, "naver")

    # 상태만 확인 (True/False)
    if is_logged_in(page, "google"):
        ...
"""

from __future__ import annotations

import time
from collections.abc import Callable

from playwright.sync_api import Page

from scripts.common.config import LOGIN_PROBE_URLS
from scripts.common.logger import get_logger

log = get_logger(__name__)


# ── 공통 판별 헬퍼 ───────────────────────────────────────────────────


def _probe(page: Page, site: str, logged_in_sels: list[str], logged_out_sels: list[str], url_block: str = "") -> bool:
    """공통 로그인 판별 — URL 이동 후 셀렉터 다중 매칭."""
    if site.lower() == "google":
        from core.agent_runtime.policy import site_entry_policy

        site_entry_policy.assert_main_page_first(LOGIN_PROBE_URLS[site], site_key="google")
    try:
        page.goto(LOGIN_PROBE_URLS[site], timeout=15000, wait_until="domcontentloaded")
        time.sleep(1)
        # URL 리다이렉트 기반 판별 (url_block이 현재 URL에 있으면 미로그인)
        if url_block and url_block in page.url:
            return False
        import json

        js_in = json.dumps(logged_in_sels)
        js_out = json.dumps(logged_out_sels)
        result = page.evaluate(f"""() => {{
            const loggedInSels  = {js_in};
            const loggedOutSels = {js_out};
            if (loggedInSels.some(s  => !!document.querySelector(s))) return 'logged_in';
            if (loggedOutSels.some(s => !!document.querySelector(s))) return 'logged_out';
            return 'unknown';
        }}""")
        return result == "logged_in"
    except Exception:  # noqa: BLE001 - 사이트별 로그인 판별 프로브(_probe, 읽기전용) - 페이지 이동/평가 실패 시 False(미로그인으로 간주)를 반환하는 안전한 방향의 기본값, ensure_login이 이를 근거로 재로그인 대기를 트리거할 뿐 세션을 파기하지 않음
        return False


# ── 사이트별 로그인 판별 ─────────────────────────────────────────────


def _check_google(page: Page) -> bool:
    return _probe(
        page,
        "google",
        logged_in_sels=[
            'a[href*="SignOutOptions"]',
            'img[aria-label*="Google"]',
            "[data-ogsr-up]",
            'a[href*="accounts.google.com/SignOut"]',
        ],
        logged_out_sels=[
            'a[href*="ServiceLogin"]',
            'input[type="email"]',
        ],
        url_block="accounts.google.com",
    )


def _check_naver(page: Page) -> bool:
    return _probe(
        page,
        "naver",
        logged_in_sels=[
            "#gnb_my_name",
            ".gnb_id",
            '[class*="gnb_my"]',
            '[class*="MyView"]',
            'a[href*="logout"]',
            'a[href*="nid.naver.com/user2/help/myInfo"]',
        ],
        logged_out_sels=[
            'a[href*="nid.naver.com/nidlogin"]',
            "a.link_login",
            "#gnb-login-button",
            'a[href*="/login.naver"]',
        ],
    )


def _check_kakao(page: Page) -> bool:
    return _probe(
        page,
        "kakao",
        logged_in_sels=[
            'a[href*="logout"]',
            ".thumb_profile",
            '[class*="profile"]',
        ],
        logged_out_sels=[
            'input[name="loginKey"]',
            'a[href*="/login"]',
        ],
        url_block="accounts.kakao.com/login",
    )


def _check_youtube(page: Page) -> bool:
    return _probe(
        page,
        "youtube",
        logged_in_sels=[
            "#avatar-btn",
            "ytd-topbar-menu-button-renderer",
        ],
        logged_out_sels=[
            'button[aria-label*="Sign in"]',
            'a[href*="/signin"]',
        ],
    )


def _check_github(page: Page) -> bool:
    return _probe(
        page,
        "github",
        logged_in_sels=[
            ".avatar-user",
            'meta[name="user-login"]',
            'a[href="/logout"]',
        ],
        logged_out_sels=[
            'a[href="/login"]',
            'input[name="login"]',
        ],
    )


# 사이트 별칭 → 확인 함수 매핑
_SITE_CHECKERS: dict[str, Callable[[Page], bool]] = {
    "google": _check_google,
    "gmail": _check_google,
    "calendar": _check_google,
    "drive": _check_google,
    "docs": _check_google,
    "sheets": _check_google,
    "naver": _check_naver,
    "blog": _check_naver,
    "cafe": _check_naver,
    "kakao": _check_kakao,
    "youtube": _check_youtube,
    "github": _check_github,
}


def is_logged_in(page: Page, site: str) -> bool:
    """사이트 로그인 상태 확인. True = 로그인됨.

    쿠키 마커 기반(페이지 이동 없음)으로 1차 판별.
    마커 미등록 사이트만 기존 셀렉터 기반 _SITE_CHECKERS로 폴백.
    """
    from scripts.auth.login_check import _LOGIN_MARKERS, _domain_of, is_logged_in_by_cookie

    domain = _domain_of(site)
    if domain in _LOGIN_MARKERS:
        result = is_logged_in_by_cookie(page, site)
        log.debug("is_logged_in[cookie]: %s → %s", site, "로그인됨" if result else "미로그인")
        return result

    checker = _SITE_CHECKERS.get(site.lower())
    if checker is None:
        log.debug("is_logged_in: 미등록 사이트 '%s' — 로그인 상태로 간주", site)
        return True
    result = checker(page)
    log.debug("is_logged_in[probe]: %s → %s", site, "로그인됨" if result else "미로그인")
    return result


# 하위 서비스 별칭 → site_registry 의 사이트 키
_REGISTRY_KEY = {
    "gmail": "google",
    "calendar": "google",
    "drive": "google",
    "docs": "google",
    "sheets": "google",
    "blog": "naver",
    "cafe": "naver",
}


def _auto_login(page: Page, site: str) -> bool:
    """등록된 사이트면 저장된 자격증명으로 바로 로그인한다. 로그인됐으면 True, 못 하면 False(대기 방식으로 넘어감)."""
    from scripts.site_engine.site_registry import get_site

    key = _REGISTRY_KEY.get(site.lower(), site.lower())
    if not get_site(key):
        return False
    from scripts.site_engine.site_access import LoginError, ensure_logged_in

    try:
        ensure_logged_in(page, key)
    except LoginError as e:
        log.warn("%s 자동 로그인 실패(%s) — 사용자 로그인을 기다립니다", site, e.kind)
        return False
    except Exception as e:  # noqa: BLE001 - 자동 로그인 실패는 기존 대기 방식으로 폴백(세션을 파기하지 않음)
        log.warn("%s 자동 로그인 예외(%s) — 사용자 로그인을 기다립니다", site, e)
        return False
    return True


def ensure_login(page: Page, site: str, wait_seconds: int = 300) -> None:
    """로그인 상태 확인, 미로그인이면 바로 자동 로그인. 자동 로그인이 안 되면(캡차·자격증명 없음 등) 사용자 대기.

    Raises:
        RuntimeError: 대기 시간 초과
    """
    if is_logged_in(page, site):
        log.info("%s 로그인 확인됨", site)
        return

    if _auto_login(page, site) and is_logged_in(page, site):
        log.info("%s 자동 로그인 완료", site)
        return

    log.warn("%s 로그인 필요 — 브라우저에서 로그인하세요 (최대 %ds)", site, wait_seconds)

    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        time.sleep(5)
        if is_logged_in(page, site):
            log.info("%s 로그인 완료", site)
            return

    raise RuntimeError(f"{site} 로그인 타임아웃 ({wait_seconds}초 초과)")

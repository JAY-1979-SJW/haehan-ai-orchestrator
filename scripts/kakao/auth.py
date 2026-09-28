"""카카오 로그인 모듈 — manual_only.

카카오는 SMS 인증/카카오앱 인증이 필수이므로 자동 로그인 불가.
브라우저에서 사용자가 직접 로그인하면 monitor_for_login()이 감지한다.

사용:
    from scripts.kakao.auth import is_logged_in, login
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.logger import get_logger  # noqa: E402

log = get_logger(__name__)

KAKAO_BASE = "https://www.kakao.com"
KAKAO_LOGIN_URL = "https://accounts.kakao.com/login"

_LOGIN_DOMAIN = "accounts.kakao.com"
_LOGGED_IN_TOKENS = ("로그아웃", "내 계정", "닉네임", "프로필")


def is_logged_in(page) -> bool:
    """카카오 로그인 상태 확인.

    판정 순서:
        1. accounts.kakao.com (로그인 페이지) → 미로그인
        2. 로그아웃 버튼/링크 → 로그인됨
        3. 로그인 폼 visible → 미로그인
        4. kakao.com 하위 보호 페이지 + 로그인 신호 → 로그인됨
        5. 그 외 → 미로그인 (보수적)
    """
    try:
        url = page.url or ""
    except Exception:  # noqa: BLE001 - 카카오 로그인 상태 감지 - 예외 시 항상 False(미로그인)로 fail-closed 반환
        return False

    if _LOGIN_DOMAIN in url:
        log.debug("kakao: 로그인 페이지 URL — 미로그인 url=%s", url)
        return False

    # 로그아웃 버튼 (강한 신호)
    for sel in ("a:has-text('로그아웃')", "button:has-text('로그아웃')", "[href*='logout']"):
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                log.debug("kakao: 로그아웃 버튼 발견 — 로그인됨")
                return True
        except Exception:  # noqa: BLE001 - 선택자 탐색 중 개별 실패는 무시하고 다음 신호를 계속 확인
            pass

    # 로그인 폼 visible → 미로그인
    for sel in ("input[name='loginId']", "input[name='password']", "#loginId", "#password"):
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                log.debug("kakao: 로그인 폼 visible — 미로그인")
                return False
        except Exception:  # noqa: BLE001 - 선택자 탐색 중 개별 실패는 무시하고 다음 신호를 계속 확인
            pass

    # body 텍스트 토큰
    try:
        text = page.locator("body").inner_text(timeout=2000)
        if any(tok in text for tok in _LOGGED_IN_TOKENS):
            log.debug("kakao: 로그인 토큰 발견 — 로그인됨")
            return True
    except Exception:  # noqa: BLE001 - 선택자 탐색 중 개별 실패는 무시하고 다음 신호를 계속 확인
        pass

    log.debug("kakao: 로그인 신호 없음 — 미로그인 처리 url=%s", url)
    return False


def login(page) -> dict:
    """카카오 로그인 — 사용자 직접 수행, monitor_for_login으로 감지.

    SMS/카카오앱 인증이 필수이므로 자동 로그인 불가.
    브라우저를 카카오 로그인 페이지로 이동 후 사용자가 로그인하면 감지한다.
    """
    from scripts.login_detector import monitor_for_login

    if is_logged_in(page):
        log.info("kakao: 이미 로그인됨")
        return {"ok": True, "reason": "기존 세션 재사용", "user": "", "needs_manual": False}

    try:
        page.goto(KAKAO_LOGIN_URL, timeout=30000)
    except Exception as e:  # noqa: BLE001 - 카카오 로그인 상태 감지 - 예외 시 항상 False(미로그인)로 fail-closed 반환
        log.warning("kakao: 로그인 페이지 이동 실패: %s", e)

    log.info("kakao: 수동 로그인 대기 (최대 5분)")
    return {
        "ok": False,
        "reason": "manual_login_required",
        "user": "",
        "needs_manual": True,
        "monitor": monitor_for_login,
    }

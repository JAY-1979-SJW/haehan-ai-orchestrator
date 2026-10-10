"""가비아(Gabia) 로그인 모듈 — manual_only.

가비아는 OTP/2FA 인증이 필수이므로 자동 로그인 불가.
브라우저에서 사용자가 직접 로그인하면 monitor_for_login()이 감지한다.

사용:
    from scripts.gabia.auth import is_logged_in, login
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.common.logger import get_logger  # noqa: E402

log = get_logger(__name__)

GABIA_BASE = "https://www.gabia.com"
GABIA_LOGIN_URL = "https://account.gabia.com/gabia/login"

# 로그인 성공 판단 URL 키워드
_LOGIN_DOMAIN = "account.gabia.com"
_LOGGED_IN_URL_PATTERNS = ("my.gabia.com", "gabia.com/mypage", "gabia.com/console")

# 로그인 상태 판단 텍스트 토큰
_LOGGED_IN_TOKENS = ("로그아웃", "내정보", "마이가비아", "계정관리")
_LOGGED_OUT_TOKENS = ("로그인", "아이디", "비밀번호")


def _logout_button_visible(page) -> bool:
    """로그아웃 버튼/링크가 보이는지(강한 로그인 신호). 탐색 실패는 무시(보수적)."""
    for sel in ("a:has-text('로그아웃')", "button:has-text('로그아웃')", "[href*='logout']"):
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                return True
        except Exception:  # noqa: BLE001 - 가비아 로그인 상태 확인 - 가비아는 OTP/2FA 필수라 자동 로그인 불가, 예외는 '미로그인'(보수적) 방향 폴백이며 인증 우회 아님
            pass
    return False


def is_logged_in(page) -> bool:
    """가비아 로그인 상태 확인.

    판정 순서:
        1. 로그인 페이지 URL → 미로그인
        2. 로그아웃 버튼 / 내정보 텍스트 → 로그인됨
        3. 로그인 폼 visible → 미로그인
        4. 보호 URL 패턴 → 로그인 추정
        5. 그 외 → 미로그인 (보수적)
    """
    try:
        url = page.url or ""
    except Exception:  # noqa: BLE001 - 가비아 로그인 상태 확인(is_logged_in) — 가비아는 OTP/2FA 필수라 자동 로그인 자체가 불가능한 구조이며, 모든 except가 '미로그인'(보수적) 방향으로 폴백해 인증 우회가 아님. login()은 사용자 수동 로그인을 안내할 뿐 자동 인증을 시도하지 않음.
        return False

    if _LOGIN_DOMAIN in url:
        log.debug("gabia: 로그인 페이지 URL — 미로그인 url=%s", url)
        return False

    # 로그아웃 버튼 (강한 신호)
    if _logout_button_visible(page):
        log.debug("gabia: 로그아웃 버튼 발견 — 로그인됨")
        return True

    # body 텍스트로 판단
    try:
        text = page.locator("body").inner_text(timeout=2000)
        if any(tok in text for tok in _LOGGED_IN_TOKENS):
            log.debug("gabia: 로그인 토큰 발견 — 로그인됨")
            return True
        if any(tok in text for tok in _LOGGED_OUT_TOKENS):
            log.debug("gabia: 로그아웃 토큰 발견 — 미로그인")
            return False
    except Exception:  # noqa: BLE001 - 가비아 로그인 상태 확인(is_logged_in) — 가비아는 OTP/2FA 필수라 자동 로그인 자체가 불가능한 구조이며, 모든 except가 '미로그인'(보수적) 방향으로 폴백해 인증 우회가 아님. login()은 사용자 수동 로그인을 안내할 뿐 자동 인증을 시도하지 않음.
        pass

    # 보호 URL 패턴
    for pat in _LOGGED_IN_URL_PATTERNS:
        if pat in url:
            log.debug("gabia: 보호 URL 패턴 매치 — 로그인 추정 url=%s", url)
            return True

    log.debug("gabia: 로그인 신호 없음 — 미로그인 처리 url=%s", url)
    return False


def _open_login_page(page) -> None:
    """gabia 로그인 페이지로 이동한다 — 실패해도 경고 로그만 남기고 수동 로그인 대기로 진행한다."""
    try:
        page.goto(GABIA_LOGIN_URL, timeout=30000)
    except Exception as e:  # noqa: BLE001 - 가비아 로그인 상태 확인(is_logged_in) — 가비아는 OTP/2FA 필수라 자동 로그인 자체가 불가능한 구조이며, 모든 except가 '미로그인'(보수적) 방향으로 폴백해 인증 우회가 아님. login()은 사용자 수동 로그인을 안내할 뿐 자동 인증을 시도하지 않음.
        log.warning("gabia: 로그인 페이지 이동 실패: %s", e)


def login(page) -> dict:
    """가비아 로그인 — 사용자 직접 수행, monitor_for_login으로 감지.

    OTP/2FA 필수이므로 자동 로그인 불가.
    브라우저를 가비아 로그인 페이지로 이동 후 사용자가 로그인하면 감지한다.
    """
    from scripts.auth.login_detector import manual_only_login

    return manual_only_login(page, site="gabia", is_logged_in=is_logged_in, open_login_page=_open_login_page, log=log)

"""네이버 인증창 게이트 — 범용 엔진 + NAVER_PROFILE 래퍼.

실제 로직은 범용 `scripts.common.auth_window_gate` 엔진에 있고, 이 모듈은 NAVER_PROFILE 을
주입한 하위호환 API(detect_auth_stage(page)/advance_once(page)/run_auth_gate(page)/click_sso(page))를
제공한다. (auth.py·smartstore 등 기존 호출부 무변경)

L4 Browser Engine 계층.
"""

from __future__ import annotations

from typing import Any

from scripts.common.auth_window_gate import (
    NAVER_PROFILE,
    STAGE_CALLBACK,
    STAGE_CAPTCHA,
    STAGE_LANDING,
    STAGE_LOGGED_IN,
    STAGE_LOGIN,
    STAGE_TWO_FACTOR,
    STAGE_UNKNOWN,
)
from scripts.common.auth_window_gate import (
    advance_once as _advance,
)
from scripts.common.auth_window_gate import (
    click_sso as _click,
)
from scripts.common.auth_window_gate import (
    detect_auth_stage as _detect,
)
from scripts.common.auth_window_gate import (
    run_auth_gate as _run,
)
from scripts.auth.login_detector import detect_login_state

# 하위호환 별칭 — 기존 네이버 모듈이 노출하던 단계명
STAGE_COMMERCE_LOGIN = STAGE_LOGIN
STAGE_NAVER_LOGIN = STAGE_LOGIN

__all__ = [
    "STAGE_CALLBACK",
    "STAGE_CAPTCHA",
    "STAGE_COMMERCE_LOGIN",
    "STAGE_LANDING",
    "STAGE_LOGGED_IN",
    "STAGE_LOGIN",
    "STAGE_NAVER_LOGIN",
    "STAGE_TWO_FACTOR",
    "STAGE_UNKNOWN",
    "advance_once",
    "click_sso",
    "detect_auth_stage",
    "run_auth_gate",
]


def detect_auth_stage(page) -> dict[str, Any]:
    return _detect(page, NAVER_PROFILE)


def click_sso(page) -> str | None:
    return _click(page, NAVER_PROFILE)


def advance_once(page, *, click_sso_if_present: bool = True) -> dict[str, Any]:
    return _advance(page, NAVER_PROFILE, click_sso_if_present=click_sso_if_present)


def run_auth_gate(page, *, max_wait_s: int = 180, poll: float = 2.5, notify=None) -> dict[str, Any]:
    return _run(
        page,
        NAVER_PROFILE,
        max_wait_s=max_wait_s,
        poll=poll,
        notify=notify,
        logged_in_check=lambda p: detect_login_state(p).get("logged_in", True),
    )

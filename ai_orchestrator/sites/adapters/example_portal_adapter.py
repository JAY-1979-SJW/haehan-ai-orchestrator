"""예시 사이트 어댑터 — 로그인 판정 + 재인증 대기 골격만 제공.

이 어댑터는 실제 외부 서비스에 대한 수집/제출 로직을 포함하지 않는다.
오직 아래 시나리오 골격만 담당한다:

    1. 홈 URL 로 이동
    2. URL 리다이렉트 + DOM 신호(로그인 버튼/사용자 메뉴)로 로그인 여부 판정
    3. 로그인되어 있지 않으면 로그인 페이지 오픈
    4. 사람이 직접 로그인/2차 인증 완료할 때까지 대기

안전 규칙:
    - 비밀번호/OTP 자동 입력 금지
    - CAPTCHA 자동 해석 금지
    - 외부 서비스 정책을 위반하는 수집/제출 동작 포함 금지
    - URL/짧은 신호 식별자 외에는 로그에 남기지 않음
"""
from __future__ import annotations

import logging
from typing import Any, ClassVar
from urllib.parse import urlparse

from ..site_adapter import LoginCheckResult, SiteAdapter

logger = logging.getLogger(__name__)


class ExamplePortalAdapter(SiteAdapter):
    """테스트/데모용 포털 어댑터.

    실제 운영 연동 시에는 이 클래스를 복사해서 선택자만 사이트에 맞게 조정하고,
    HOME_URL / LOGIN_URL 상수만 바꾼다.
    """

    site_id: ClassVar[str] = "example_portal"
    display_name: ClassVar[str] = "Example Portal"

    HOME_URL: ClassVar[str] = "https://example.test/"
    LOGIN_URL: ClassVar[str] = "https://example.test/login"

    # 로그인 화면을 가리키는 URL 조각. 여기로 리다이렉트되면 세션 만료로 판정.
    LOGIN_URL_HINTS: ClassVar[tuple[str, ...]] = ("/login", "/signin", "/auth")

    # 로그인 성공 시에만 나타나는 신호. URL 확인 + 이 셀렉터 중 하나 존재 시 logged_in.
    LOGGED_IN_SELECTORS: ClassVar[tuple[str, ...]] = (
        "#user-menu",
        "button[data-action='logout']",
        "a[href*='/logout']",
    )

    default_reauth_timeout_sec: ClassVar[int] = 180
    default_reauth_poll_interval_sec: ClassVar[float] = 5.0

    # ── 진입점 ────────────────────────────────────────────────
    def open_home(self, page: Any) -> None:
        logger.info("[ADAPTER-OPEN-HOME] site=%s url=%s", self.site_id, self.HOME_URL)
        page.goto(self.HOME_URL)

    def open_login_page(self, page: Any) -> None:
        logger.info("[ADAPTER-OPEN-LOGIN] site=%s url=%s", self.site_id, self.LOGIN_URL)
        page.goto(self.LOGIN_URL)

    # ── 로그인 판정 ────────────────────────────────────────────
    def check_logged_in(self, page: Any) -> LoginCheckResult:
        """URL + DOM 신호 조합으로 로그인 여부 판정.

        판정 규칙:
            1) 현재 URL 이 LOGIN_URL_HINTS 에 일치하면 무조건 is_logged_in=False
               ("redirected_to_login").
            2) LOGGED_IN_SELECTORS 중 하나라도 존재하면 is_logged_in=True.
            3) 그 외에는 is_logged_in=False ("no_user_menu"). 쿠키 존재만으로 True 로 판정하지 않는다.
        """
        current_url = self._safe_url(page)
        parsed_path = urlparse(current_url).path or ""

        # 1) URL 신호 — 로그인 페이지로 튕겼는가
        for hint in self.LOGIN_URL_HINTS:
            if hint in parsed_path:
                return LoginCheckResult(
                    is_logged_in=False,
                    reason="redirected_to_login",
                    detected_url=current_url,
                    matched_signals=[f"url_hint:{hint}"],
                )

        # 2) DOM 신호 — 로그아웃/사용자 메뉴 존재 여부
        matched: list[str] = []
        for selector in self.LOGGED_IN_SELECTORS:
            if self._has_selector(page, selector):
                matched.append(f"selector:{selector}")
        if matched:
            return LoginCheckResult(
                is_logged_in=True,
                reason="logged_in_signals_matched",
                detected_url=current_url,
                matched_signals=matched,
            )

        # 3) 신호 없음
        return LoginCheckResult(
            is_logged_in=False,
            reason="no_user_menu",
            detected_url=current_url,
            matched_signals=[],
        )

    # ── 내부 헬퍼 (예외 안전 래퍼) ─────────────────────────────
    def _safe_url(self, page: Any) -> str:
        try:
            url = page.url
            return url if isinstance(url, str) else ""
        except Exception as exc:  # noqa: BLE001 — 연결 끊김/페이지 닫힘 등
            logger.debug("페이지 URL 읽기 실패: %s", type(exc).__name__)
            return ""

    def _has_selector(self, page: Any, selector: str) -> bool:
        """페이지에서 selector 가 존재하는지 안전하게 확인.

        Playwright Page 의 `query_selector` 를 사용. 예외가 발생하면 False.
        민감 원문(HTML/텍스트)은 여기서 절대 로깅하지 않는다.
        """
        try:
            el = page.query_selector(selector)
            return el is not None
        except Exception as exc:  # noqa: BLE001
            logger.debug("selector 존재 확인 실패: %s", type(exc).__name__)
            return False


__all__ = ["ExamplePortalAdapter"]

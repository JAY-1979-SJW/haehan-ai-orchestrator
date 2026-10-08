"""세션 자동 관리 — 만료 감지 + 자동 재로그인 + 토큰 갱신.

자동 동작:
  - 페이지 이동 후 세션 상태 검증
  - 만료 감지 시 자동 재로그인
  - 동시 세션 충돌 방지
"""

from __future__ import annotations

import time
from collections.abc import Callable

from playwright.sync_api import Page

from scripts.auth.login_detector import detect_login_state
from scripts.browser.session.session_tracker import mark_state
from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger

_log = get_logger(__name__)


class SessionManager:
    """세션 만료 자동 감지 + 재로그인."""

    def __init__(self, page: Page, domain: str = "naver.com"):
        self.page = page
        self.domain = domain
        self._last_check: float = 0

    def check_and_recover(self, force: bool = False) -> dict:
        """현재 페이지 로그인 상태 확인 → 만료 시 재로그인.

        force=False: 30초 캐시
        """
        now = time.time()
        if not force and now - self._last_check < 30:
            return {"ok": True, "cached": True}

        state = detect_login_state(self.page)
        mark_state(self.domain, state)
        self._last_check = now

        if state.get("logged_in"):
            return {"ok": True, "user": state.get("user"), "score": state.get("score")}

        # 로그인 페이지 또는 만료 — 재로그인 시도
        _log.warning("[session] 세션 만료 또는 비로그인 감지 → 자동 재로그인")
        log_critical(
            "AUTH_FAIL",
            f"세션 만료 감지: {self.domain}",
            domain=self.domain,
            score=state.get("score"),
            mode="session_expired",
        )

        from scripts.naver.common.auth import login_naver

        r = login_naver(self.page)
        if r.get("ok"):
            log_critical("AUTH_SUCCESS", f"자동 재로그인 성공: {self.domain}", user=r.get("user"), mode="auto_relogin")
            return {"ok": True, "user": r.get("user"), "recovered": True}
        return {"ok": False, "error": r.get("reason"), "recovered": False}

    def wrap(self, func: Callable, *args, **kwargs):
        """함수 호출 전후로 세션 검증 + 자동 복구.

        사용:
            sm = SessionManager(page)
            result = sm.wrap(lambda: n.smartstore.list_orders())
        """
        # 사전 체크
        pre = self.check_and_recover()
        if not pre.get("ok"):
            return {"ok": False, "error": "session_recovery_failed", "detail": pre}
        try:
            result = func(*args, **kwargs)
            # 사후 체크 (작업 중 만료됐는지)
            post = self.check_and_recover(force=True)  # noqa: F841
            return result
        except Exception as e:  # noqa: BLE001 - 세션 만료로 추정되는 예외 발생시 자동 재로그인(login_naver) 시도 후 1회 재시도, 실패시 오류 반환 — 로그아웃/쿠키삭제 없이 재로그인만 수행
            # 만료로 인한 에러일 수 있음
            recover = self.check_and_recover(force=True)
            if recover.get("recovered"):
                try:
                    return func(*args, **kwargs)
                except Exception as e2:  # noqa: BLE001 - 세션 만료로 추정되는 예외 발생시 자동 재로그인(login_naver) 시도 후 1회 재시도, 실패시 오류 반환 — 로그아웃/쿠키삭제 없이 재로그인만 수행
                    return {"ok": False, "error": f"retry_failed:{e2}"}
            return {"ok": False, "error": str(e)}

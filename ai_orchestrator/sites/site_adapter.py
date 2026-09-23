"""사이트 어댑터 베이스 (세션 유지 + 로그인 판정 + 재인증 대기).

`SiteConnector` (connector 모듈) 는 orchestrator/오케스트레이터 간 action dispatch 인터페이스를
정의한다. 이 모듈의 `SiteAdapter` 는 그 아래 계층으로, **브라우저 세션 + 로그인 여부 + 재인증 대기**
에 집중한다. 두 인터페이스가 겹치지 않도록 의도적으로 분리한다.

원칙:
- CAPTCHA/OTP 자동 해석/우회 금지 — adapter 는 "사람이 직접 로그인을 완료할 때까지 대기" 만 한다.
- 비밀번호/OTP/쿠키 원문은 이 모듈에서 로깅하지 않는다.
- Playwright 가 설치되어 있지 않거나 브라우저를 띄우지 못하는 환경(CI, 서버 헤드리스)에서도
  import/테스트가 깨지지 않아야 한다. Page 타입은 `Any` 로 느슨하게 둔다.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


# ── 로그인 판정 결과 ──────────────────────────────────────────────
# reason 은 짧은 코드 식별자. 상세 문장/HTML 원문은 담지 않는다.
LoginReasonCode = str  # 예: "logged_in_signals_matched", "redirected_to_login", "no_user_menu"


@dataclass
class LoginCheckResult:
    """로그인 상태 판정 결과.

    - is_logged_in: True/False. 쿠키 존재만으로 True 로 판정하지 말 것.
    - reason: 짧은 코드 (enum-like 문자열). 민감 원문 금지.
    - detected_url: 판정 시점의 최종 URL (redirect 결과 포함 가능).
    - matched_signals: 판정에 사용한 셀렉터/신호 식별자 목록 (예: "has_logout_button").
    """

    is_logged_in: bool
    reason: LoginReasonCode = ""
    detected_url: str = ""
    matched_signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_logged_in": self.is_logged_in,
            "reason": self.reason,
            "detected_url": self.detected_url,
            "matched_signals": list(self.matched_signals),
        }


# ── 재인증 대기 결과 ──────────────────────────────────────────────
@dataclass
class ReauthWaitResult:
    """wait_for_human_reauth 결과.

    - succeeded: 사용자가 재인증을 완료했고 post_login_verify 가 True 를 반환했는지
    - elapsed_sec: 실제 대기한 초
    - timed_out: 타임아웃으로 종료됐는지
    - last_check: 마지막 LoginCheckResult (있으면)
    """

    succeeded: bool
    elapsed_sec: float = 0.0
    timed_out: bool = False
    last_check: LoginCheckResult | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "succeeded": self.succeeded,
            "elapsed_sec": self.elapsed_sec,
            "timed_out": self.timed_out,
            "last_check": self.last_check.to_dict() if self.last_check else None,
        }


class SiteAdapter(ABC):
    """사이트 자동화 어댑터 베이스.

    수명 주기:
        session_manager.open(site_id)
            → adapter.open_home(page)
            → adapter.check_logged_in(page) → LoginCheckResult
                ├─ is_logged_in=True  → 작업 진행
                └─ is_logged_in=False → adapter.open_login_page(page)
                                        → adapter.wait_for_human_reauth(page)
                                        → 성공 시 작업 재개
    """

    site_id: ClassVar[str] = ""
    # 외부 화면에 보여줘도 되는 짧은 사람 읽기용 이름 (비밀 아님).
    display_name: ClassVar[str] = ""
    # 기본 재인증 타임아웃 (초). adapter 별로 override 가능.
    default_reauth_timeout_sec: ClassVar[int] = 180
    # post_login_verify 재확인 간격.
    default_reauth_poll_interval_sec: ClassVar[float] = 5.0

    @abstractmethod
    def open_home(self, page: Any) -> None:
        """사이트 홈/진입점으로 이동. Playwright page 를 받지만 타입은 느슨하게 둔다."""

    @abstractmethod
    def check_logged_in(self, page: Any) -> LoginCheckResult:
        """현재 페이지 상태로 로그인 여부 판정. URL + DOM 신호를 조합해서 판정한다."""

    @abstractmethod
    def open_login_page(self, page: Any) -> None:
        """로그인 화면으로 이동. 실제 자격증명 입력은 사람이 직접 수행한다."""

    def post_login_verify(self, page: Any) -> LoginCheckResult:
        """재인증 후 로그인 성공 여부 재확인. 기본은 check_logged_in 과 같은 로직."""
        return self.check_logged_in(page)

    def wait_for_human_reauth(
        self,
        page: Any,
        *,
        timeout_sec: int | None = None,
        poll_interval_sec: float | None = None,
        sleeper: Any = None,
        clock: Any = None,
    ) -> ReauthWaitResult:
        """사람이 직접 로그인/2차 인증을 완료할 때까지 대기.

        - 주기적으로 post_login_verify 를 호출해 로그인 성공 여부 확인.
        - 성공 시 succeeded=True 로 즉시 반환.
        - timeout_sec 를 초과하면 timed_out=True 로 반환.

        sleeper/clock 은 테스트에서 시간 의존성을 분리하기 위한 주입점.
        운영에서는 None 으로 두면 time.sleep / time.monotonic 을 사용한다.
        """
        import time as _time

        timeout = int(timeout_sec if timeout_sec is not None else self.default_reauth_timeout_sec)
        interval = float(poll_interval_sec if poll_interval_sec is not None else self.default_reauth_poll_interval_sec)
        _sleep = sleeper if sleeper is not None else _time.sleep
        _now = clock if clock is not None else _time.monotonic

        start = _now()
        last: LoginCheckResult | None = None
        while True:
            last = self.post_login_verify(page)
            elapsed = _now() - start
            if last.is_logged_in:
                logger.info(
                    "[REAUTH-SUCCESS] site=%s elapsed_sec=%.1f signals=%s",
                    self.site_id,
                    elapsed,
                    last.matched_signals,
                )
                return ReauthWaitResult(succeeded=True, elapsed_sec=elapsed, last_check=last)
            if elapsed >= timeout:
                logger.warning(
                    "[REAUTH-TIMEOUT] site=%s elapsed_sec=%.1f timeout_sec=%d reason=%s",
                    self.site_id,
                    elapsed,
                    timeout,
                    last.reason,
                )
                return ReauthWaitResult(
                    succeeded=False,
                    elapsed_sec=elapsed,
                    timed_out=True,
                    last_check=last,
                )
            _sleep(interval)

    # ── 선택 기능 ────────────────────────────────────────────────
    def collect_list(self, page: Any, *, cursor: str = "") -> dict[str, Any]:
        """목록 조회용 선택 hook. 어댑터가 구현하지 않으면 빈 결과 반환.

        cursor 는 재개용 커서. 실제 시맨틱은 어댑터가 정의한다.
        """
        return {"items": [], "cursor": cursor, "done": True}


__all__ = [
    "LoginCheckResult",
    "LoginReasonCode",
    "ReauthWaitResult",
    "SiteAdapter",
]

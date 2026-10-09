"""사이트 진입 정책 — main-page-first.

L2 (Policy/Gate) — 사이트별 자동 업무 진입 시 따라야 하는 정책:
  1. 로그인 전용 URL(nidlogin.login, accounts.google.com 등) 직접 진입 금지
  2. main_url 먼저 navigate 하여 세션 유효성 확인
  3. LOGGED_IN 이면 work_url 로 이동 (필요 시)
  4. LOGIN_REQUIRED 이면 site 의 정식 login flow 시작
  5. 로그인 완료 후 work_url 자동 재개

본 모듈은 정책 데이터와 helper 만 제공한다 — 실제 navigate/평가는 caller (browser
executor 또는 router) 가 수행한다. 신규 모듈 — 기존 코드 무단 변경 없음.

연결되는 시스템 모듈:
  - core.agent_runtime.browser.login_state_detector — has_logout/has_id_form 등 page signal 매핑
  - desktop.local_server._handle_browser_action — navigate 전 정책 적용
  - scripts.naver.router 외 site router — 호출 시점 정책 확인
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# ── 상수 ─────────────────────────────────────────────────────────────

STATE_LOGGED_IN = "LOGGED_IN"
STATE_LOGIN_REQUIRED = "LOGIN_REQUIRED"
STATE_SESSION_EXPIRED = "SESSION_EXPIRED"
STATE_LOGIN_UNKNOWN = "LOGIN_UNKNOWN"

# 로그인 전용 URL 패턴 (직접 진입 금지).
FORBIDDEN_LOGIN_URL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^https?://nid\.naver\.com/nidlogin\.login"),
    re.compile(r"^https?://accounts\.google\.com/"),
    re.compile(r"^https?://accounts\.kakao\.com/login"),
    re.compile(r"^https?://logins\.daum\.net/"),
    re.compile(r"^https?://logins\.daum\.kakao\.com/"),
    # YouTube 의 ServiceLogin
    re.compile(r"^https?://(www\.)?youtube\.com/signin"),
)


# ── 데이터 ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SiteEntryPolicy:
    """사이트별 진입 정책.

    Attributes:
        site_key: 식별자 (naver, google, kakao, ...)
        main_url: 세션 확인용 1차 진입 URL — 항상 여기로 먼저 간다
        work_url_default: 업무 진입 기본 URL (없으면 main_url 과 동일)
        logged_in_signals: 페이지 상태 dict 에서 True 면 LOGGED_IN 으로 본다
        login_required_signals: True 면 LOGIN_REQUIRED 로 본다
        forbid_login_url_direct: True 면 본 사이트의 로그인 전용 URL 직접 진입 차단
    """

    site_key: str
    main_url: str
    work_url_default: str = ""
    logged_in_signals: tuple[str, ...] = ()
    login_required_signals: tuple[str, ...] = ()
    forbid_login_url_direct: bool = True

    def work_url(self, override: str = "") -> str:
        return override or self.work_url_default or self.main_url


# ── 등록 ─────────────────────────────────────────────────────────────

_REGISTRY: dict[str, SiteEntryPolicy] = {}


def register(p: SiteEntryPolicy) -> None:
    _REGISTRY[p.site_key] = p


def get(site_key: str) -> SiteEntryPolicy | None:
    return _REGISTRY.get(site_key)


def all_policies() -> list[SiteEntryPolicy]:
    return list(_REGISTRY.values())


# ── 기본 정책 ────────────────────────────────────────────────────────

# 공통 signal 키 (page state dict 의 bool 키와 일치해야 함):
#   has_logout / has_mypage_link / has_user_menu / has_id_form / has_pw_form /
#   has_login_btn / has_relogin_msg

_NAVER_LOGGED_IN = ("has_logout", "has_mypage_link", "has_user_menu")
_NAVER_LOGIN_REQ = ("has_id_form", "has_pw_form")

register(
    SiteEntryPolicy(
        site_key="naver",
        main_url="https://www.naver.com/",
        work_url_default="https://www.naver.com/",
        logged_in_signals=_NAVER_LOGGED_IN,
        login_required_signals=_NAVER_LOGIN_REQ,
    )
)
register(
    SiteEntryPolicy(
        site_key="naver_blog",
        main_url="https://section.blog.naver.com/BlogHome.naver",
        work_url_default="https://section.blog.naver.com/BlogHome.naver",
        logged_in_signals=_NAVER_LOGGED_IN,
        login_required_signals=_NAVER_LOGIN_REQ,
    )
)
register(
    SiteEntryPolicy(
        site_key="naver_cafe",
        main_url="https://section.cafe.naver.com/",
        work_url_default="https://section.cafe.naver.com/",
        logged_in_signals=_NAVER_LOGGED_IN,
        login_required_signals=_NAVER_LOGIN_REQ,
    )
)
register(
    SiteEntryPolicy(
        site_key="google",
        main_url="https://www.google.com/",
        work_url_default="https://www.google.com/",
        logged_in_signals=("has_user_menu", "has_mypage_link"),
        login_required_signals=("has_login_btn",),
    )
)
register(
    SiteEntryPolicy(
        site_key="youtube",
        main_url="https://www.youtube.com/",
        work_url_default="https://www.youtube.com/",
        logged_in_signals=("has_user_menu",),
        login_required_signals=("has_login_btn",),
    )
)
register(
    SiteEntryPolicy(
        site_key="kakao",
        main_url="https://www.kakao.com/",
        work_url_default="https://www.kakao.com/",
        logged_in_signals=("has_logout", "has_user_menu"),
        login_required_signals=("has_login_btn",),
    )
)
register(
    SiteEntryPolicy(
        site_key="daum",
        main_url="https://www.daum.net/",
        work_url_default="https://www.daum.net/",
        logged_in_signals=("has_logout", "has_user_menu"),
        login_required_signals=("has_login_btn",),
    )
)
register(
    SiteEntryPolicy(
        site_key="eum",
        main_url="https://eum.cw.or.kr/",
        work_url_default="https://eum.cw.or.kr/main",
        logged_in_signals=("has_logout", "has_mypage_link"),
        login_required_signals=("has_id_form", "has_pw_form"),
    )
)


# ── helper ──────────────────────────────────────────────────────────


def is_login_url_forbidden(url: str) -> bool:
    """로그인 전용 URL 직접 진입 금지 대상인지."""
    if not url:
        return False
    for pat in FORBIDDEN_LOGIN_URL_PATTERNS:
        if pat.match(url):
            return True
    return False


def resolve_entry(site_key: str, work_url: str = "") -> tuple[str, str]:
    """진입 계획 반환.

    Returns:
        (first_url, follow_up_work_url)
        - first_url: 항상 main_url
        - follow_up_work_url: 세션 유효 시 이어서 갈 URL
    """
    p = get(site_key)
    if p is None:
        # 정책 미등록 사이트 — caller 가 work_url 그대로 사용
        return (work_url, work_url)
    return (p.main_url, p.work_url(work_url))


def judge_login_state(
    site_key: str,
    page_state: dict[str, Any],
) -> str:
    """page_state(bool 신호 dict) 와 정책으로 login_state 판정.

    page_state 예시:
        {"has_logout": True, "has_id_form": False, "has_login_btn": False,
         "has_relogin_msg": False, ...}
    """
    p = get(site_key)
    if p is None:
        return STATE_LOGIN_UNKNOWN

    # 1) 명시적 재로그인 안내
    if page_state.get("has_relogin_msg"):
        return STATE_SESSION_EXPIRED

    # 2) 로그인 폼 직접 노출
    if page_state.get("has_id_form") and page_state.get("has_pw_form"):
        # 쿠키가 있는데 폼이 뜨면 만료
        if page_state.get("has_naver_session_cookie") or page_state.get("has_any_auth_cookie"):
            return STATE_SESSION_EXPIRED
        return STATE_LOGIN_REQUIRED

    # 3) 정책의 logged_in_signals 중 하나라도 True
    if any(bool(page_state.get(k)) for k in p.logged_in_signals):
        return STATE_LOGGED_IN

    # 4) login_required_signals
    if any(bool(page_state.get(k)) for k in p.login_required_signals):
        return STATE_LOGIN_REQUIRED

    return STATE_LOGIN_UNKNOWN


def assert_main_page_first(target_url: str, site_key: str = "") -> None:
    """caller 진입 시점 가드 — 로그인 URL 직접 진입을 차단한다.

    Raises:
        ValueError: 로그인 전용 URL 직접 진입 시도
    """
    if is_login_url_forbidden(target_url):
        raise ValueError(
            f"FORBIDDEN_LOGIN_URL_DIRECT_ENTRY: {target_url!r} — "
            f"main-page-first 정책에 따라 site_entry_policy.resolve_entry({site_key!r}) 사용."
        )

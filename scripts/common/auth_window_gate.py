"""범용 순차 인증창 게이트 — 사이트 무관 엔진.

로그인 시 나타나는 창(로그인 → SSO → 2단계인증/캡차 → 콜백 → 완료)을 순서대로 감지·처리한다.
사이트별 차이는 `SiteAuthProfile`(단계 규칙·SSO 버튼·도메인)로 주입하고, 엔진 로직은 공통이다.

설계 핵심:
- 브라우저에서는 **범용 probe**(url, 본문 텍스트, 버튼 텍스트, 비밀번호 입력 유무)만 수집한다.
- **단계 판정(`classify`)은 순수 함수** — probe dict + profile 만으로 결정 → 브라우저 없이 단위검증 가능.
- 자동 단계(SSO 클릭, 콜백 대기)는 엔진이 처리, 보안 단계(OTP/캡차/비번)는 창을 앞으로 띄우고 사용자 완료를 폴링(자동 입력 금지).

L4 Browser Engine 계층. 업무 로직 없음.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from scripts.common.logger import get_logger

_log = get_logger(__name__)

# ── 단계(공통) ───────────────────────────────────────────────────────────────
STAGE_LOGGED_IN = "logged_in"
STAGE_LOGIN = "login"  # 아이디/비밀번호 로그인 페이지
STAGE_TWO_FACTOR = "two_factor"  # 2단계 인증(OTP)
STAGE_CAPTCHA = "captcha"  # 보안문자
STAGE_CERT = "cert"  # 공동/금융 인증서 (G2B 등)
STAGE_CALLBACK = "callback"  # 로그인 콜백(전이)
STAGE_LANDING = "landing"  # 비로그인 랜딩
STAGE_UNKNOWN = "unknown"

_NEEDS_USER = {STAGE_TWO_FACTOR, STAGE_CAPTCHA, STAGE_CERT, STAGE_LOGIN}

_DEFAULT_HINT = {
    STAGE_TWO_FACTOR: "2단계 인증 — 받은 인증번호 입력 후 확인",
    STAGE_CAPTCHA: "보안문자(캡차) 입력 필요",
    STAGE_CERT: "공동/금융 인증서 선택·암호 입력 필요",
    STAGE_LOGIN: "아이디/비밀번호 로그인 필요",
}


@dataclass
class StageRule:
    """한 단계의 매칭 규칙. url_contains 중 하나라도 들어있거나 text_regex 가 본문에 매치하면 해당 단계."""

    stage: str
    url_contains: tuple[str, ...] = ()
    text_regex: str = ""
    hint: str = ""


@dataclass
class SiteAuthProfile:
    """사이트별 인증창 프로필."""

    site: str
    rules: tuple[StageRule, ...] = ()  # 순서대로 평가, 먼저 매치하는 규칙 채택
    sso_button_regex: str = ""  # SSO/간편 로그인 버튼 텍스트
    login_btn_regex: str = "로그인하기"  # 이 버튼 존재 = 미로그인 신호
    domain_contains: tuple[str, ...] = ()  # 이 도메인 + 미로그인신호 없음 = 로그인됨
    landing_url_contains: tuple[str, ...] = ()  # 비로그인 랜딩 경로


# 브라우저에서 수집하는 범용 probe (사이트 무관)
_PROBE_JS = r"""
(() => {
  const url = location.href;
  const text = ((document.body && document.body.innerText) || '').replace(/\s+/g, ' ').slice(0, 600);
  const buttons = [...document.querySelectorAll('a,button')]
      .map(e => (e.textContent || '').trim()).filter(Boolean).slice(0, 40);
  const hasPw = !!document.querySelector('input[type=password]');
  return { url, text, buttons, hasPw };
})()
"""


def probe_page(page) -> dict[str, Any]:
    try:
        return page.evaluate(_PROBE_JS)
    except Exception as e:  # noqa: BLE001 - 범용 로그인 인증창 감지 엔진 — probe_page/click_sso/_bring_front 실패 시 안전한 기본값(빈 probe, None, 무시)을 반환하며, 보안단계(OTP/캡차)는 자동입력 없이 사용자에게 창을 띄우는 설계이고 단계판정(classify)은 예외를 던지지 않는 순수함수.
        return {"url": "", "text": "", "buttons": [], "hasPw": False, "error": str(e)[:80]}


def classify(probe: dict[str, Any], profile: SiteAuthProfile) -> dict[str, Any]:
    """순수 함수: probe + profile → 단계 판정. (브라우저 불필요 — 단위검증 대상)"""
    url = probe.get("url", "") or ""
    text = probe.get("text", "") or ""
    buttons = probe.get("buttons", []) or []

    has_login_btn = bool(profile.login_btn_regex) and any(re.search(profile.login_btn_regex, b) for b in buttons)
    sso = None
    if profile.sso_button_regex:
        sso = next((b for b in buttons if re.search(profile.sso_button_regex, b)), None)

    # 1) 명시 규칙 (순서대로)
    for rule in profile.rules:
        hit = any(u in url for u in rule.url_contains)
        if not hit and rule.text_regex:
            hit = bool(re.search(rule.text_regex, text))
        if hit:
            stage = rule.stage
            return {
                "stage": stage,
                "url": url,
                "sso": sso,
                "needs_user": stage in _NEEDS_USER,
                "hint": rule.hint or _DEFAULT_HINT.get(stage, ""),
            }

    # 2) 랜딩(비로그인)
    if has_login_btn or any(u in url for u in profile.landing_url_contains):
        return {"stage": STAGE_LANDING, "url": url, "sso": sso, "needs_user": False, "hint": ""}

    # 3) 로그인됨 (사이트 도메인 + 미로그인 신호 없음)
    if any(d in url for d in profile.domain_contains):
        return {"stage": STAGE_LOGGED_IN, "url": url, "sso": sso, "needs_user": False, "hint": ""}

    return {"stage": STAGE_UNKNOWN, "url": url, "sso": sso, "needs_user": False, "hint": ""}


def detect_auth_stage(page, profile: SiteAuthProfile) -> dict[str, Any]:
    return classify(probe_page(page), profile)


def click_sso(page, profile: SiteAuthProfile) -> str | None:
    """SSO/간편 로그인 버튼이 있으면 클릭. 클릭한 라벨 반환."""
    if not profile.sso_button_regex:
        return None
    js = r"""
    (re_src) => {
      const rx = new RegExp(re_src);
      const e = [...document.querySelectorAll('a,button')].find(x => rx.test(x.textContent || ''));
      if (e) { e.click(); return (e.textContent || '').trim().slice(0, 40); }
      return null;
    }
    """
    try:
        return page.evaluate(js, profile.sso_button_regex)
    except Exception:  # noqa: BLE001 - 범용 로그인 인증창 감지 엔진 — probe_page/click_sso/_bring_front 실패 시 안전한 기본값(빈 probe, None, 무시)을 반환하며, 보안단계(OTP/캡차)는 자동입력 없이 사용자에게 창을 띄우는 설계이고 단계판정(classify)은 예외를 던지지 않는 순수함수.
        return None


def _bring_front(page) -> None:
    with suppress(Exception):
        page.bring_to_front()


def advance_once(page, profile: SiteAuthProfile, *, click_sso_if_present: bool = True) -> dict[str, Any]:
    """비차단 한 스텝: 단계 판정 → SSO 가능하면 클릭, 보안단계면 창 앞으로.

    action: logged_in | sso_clicked | wait_callback | needs_user | none
    """
    st = detect_auth_stage(page, profile)
    stage = st["stage"]
    action = "none"

    if stage == STAGE_LOGGED_IN:
        action = "logged_in"
    elif stage in (STAGE_LOGIN, STAGE_LANDING) and st.get("sso") and click_sso_if_present:
        label = click_sso(page, profile)
        action = "sso_clicked" if label else "needs_user"
        st["sso_clicked"] = label
        if action == "needs_user":
            _bring_front(page)
    elif stage == STAGE_CALLBACK:
        action = "wait_callback"
    elif st.get("needs_user") or stage in (STAGE_LOGIN, STAGE_LANDING):
        _bring_front(page)
        action = "needs_user"

    st["action"] = action
    return st


def run_auth_gate(
    page,
    profile: SiteAuthProfile,
    *,
    max_wait_s: int = 180,
    poll: float = 2.5,
    notify: Callable[[dict], None] | None = None,
    logged_in_check: Callable[[Any], bool] | None = None,
) -> dict[str, Any]:
    """인증 창들을 순서대로 끝까지 처리(블로킹). 대화형/포그라운드 용.

    logged_in_check: 최종 로그인 교차검증 콜백(없으면 단계 판정만 사용).
    """
    deadline = time.time() + max_wait_s
    last_stage = None
    notified: set[str] = set()

    while time.time() < deadline:
        st = advance_once(page, profile)
        stage = st["stage"]
        if stage != last_stage:
            _log.info(
                "[auth-gate:%s] stage=%s action=%s url=%s",
                profile.site,
                stage,
                st.get("action"),
                (st.get("url") or "")[:60],
            )
            last_stage = stage

        if st.get("action") == "logged_in" and (logged_in_check is None or logged_in_check(page)):
            return {"ok": True, "stage": STAGE_LOGGED_IN, "site": profile.site}

        if st.get("action") == "needs_user" and stage not in notified:
            notified.add(stage)
            _log.warning("[auth-gate:%s] 사용자 입력 대기: %s (%s)", profile.site, stage, st.get("hint"))
            if notify:
                with suppress(Exception):
                    notify({"site": profile.site, "stage": stage, "hint": st.get("hint")})

        time.sleep(poll)

    final = detect_auth_stage(page, profile)
    return {
        "ok": False,
        "site": profile.site,
        "stage": final["stage"],
        "reason": "timeout",
        "needs_user": final.get("needs_user"),
        "hint": final.get("hint"),
    }


# ── 사이트 프로필 ─────────────────────────────────────────────────────────────
NAVER_PROFILE = SiteAuthProfile(
    site="naver",
    rules=(
        StageRule(
            STAGE_TWO_FACTOR,
            url_contains=("certify",),
            text_regex=r"2단계 인증|인증번호 6자리|2차\s*인증",
            hint="2단계 인증(2FA) — 이메일/휴대전화로 받은 6자리 인증번호 입력 후 확인",
        ),
        StageRule(STAGE_CAPTCHA, text_regex=r"캡차|보안문자|captcha", hint="보안문자(캡차) 입력 필요"),
        StageRule(STAGE_CALLBACK, url_contains=("login-callback",)),
        StageRule(
            STAGE_LOGIN,
            url_contains=("nid.naver.com", "accounts.commerce.naver.com/login"),
            hint="네이버 로그인 필요(네이버 세션 있으면 SSO 자동)",
        ),
    ),
    sso_button_regex=r"간편 로그인|네이버 아이디로 로그인",
    login_btn_regex=r"로그인하기",
    domain_contains=("smartstore.naver.com", "cafe.naver.com", "mail.naver.com", "pay.naver.com", "naver.com"),
    landing_url_contains=("/home/about",),
)

# 비네이버 스켈레톤 (각 사이트 로그인창 패턴 — 추후 정밀화 가능)
GABIA_PROFILE = SiteAuthProfile(
    site="gabia",
    rules=(
        StageRule(STAGE_CAPTCHA, text_regex=r"캡차|보안문자|captcha|자동입력 방지"),
        StageRule(STAGE_TWO_FACTOR, text_regex=r"2단계 인증|인증번호|OTP"),
        StageRule(STAGE_LOGIN, url_contains=("login.gabia.com", "/login")),
    ),
    login_btn_regex=r"로그인",
    domain_contains=("gabia.com", "hosting.gabia.com"),
)

G2B_PROFILE = SiteAuthProfile(
    site="g2b",
    rules=(
        StageRule(
            STAGE_CERT,
            text_regex=r"공동인증서|금융인증서|인증서 선택|인증서 로그인",
            hint="나라장터 — 공동/금융 인증서 선택·암호 입력 필요",
        ),
        StageRule(STAGE_CAPTCHA, text_regex=r"캡차|보안문자|captcha"),
        StageRule(STAGE_LOGIN, url_contains=("login", "Login")),
    ),
    login_btn_regex=r"로그인",
    domain_contains=("g2b.go.kr",),
)

EUM_PROFILE = SiteAuthProfile(
    site="eum",
    rules=(
        StageRule(STAGE_CAPTCHA, text_regex=r"캡차|보안문자|captcha"),
        StageRule(STAGE_TWO_FACTOR, text_regex=r"2단계 인증|인증번호|OTP"),
        StageRule(STAGE_LOGIN, url_contains=("login", "Login")),
    ),
    login_btn_regex=r"로그인",
    domain_contains=("eum.cw.or.kr",),
)

PROFILES: dict[str, SiteAuthProfile] = {p.site: p for p in (NAVER_PROFILE, GABIA_PROFILE, G2B_PROFILE, EUM_PROFILE)}

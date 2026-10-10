"""Naver Mail 진입 + 세션 확인 + 로그인 대기.

흐름 (main-page-first 정책):
  1. www.naver.com → 세션 신호 평가 → LOGGED_IN/LOGIN_REQUIRED
  2. LOGIN_REQUIRED 면: 사용자에게 안내(콜백 또는 stdout) + 로그인 대기 폴링
  3. mail.naver.com 진입 → 추가 인증 redirect 시 동일 대기 흐름
  4. mail.naver.com/v2/folders/* 도달 시 READY 반환

사용자 자격증명 자동 입력은 절대 하지 않는다 (정책).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from core.agent_runtime.policy import site_entry_policy as sep
from scripts.naver.mail.read import cdp

# 진입 결과 상수
READY = "READY"  # mail.naver.com 진입 + 세션 정상
NEED_LOGIN = "NEED_LOGIN"  # 사용자 수동 로그인 필요 (일반 NID)
NEED_MAIL_LOGIN = "NEED_MAIL_LOGIN"  # mail 진입 시 추가 인증 redirect
TIMED_OUT = "TIMED_OUT"
ERROR = "ERROR"


@dataclass
class EntryResult:
    state: str
    target_id: str = ""
    final_url: str = ""
    title: str = ""
    notes: list[str] = field(default_factory=list)


PAGE_SIGNAL_EXPR = r"""
JSON.stringify((function(){
  const txt = (document.body && document.body.innerText) || '';
  return {
    href: location.href, title: document.title,
    has_logout: /로그아웃/.test(txt) || !!document.querySelector('a[href*="logout"]'),
    has_mypage_link: !!document.querySelector('a[href*="mypage"], a[href*="my.naver"]'),
    has_id_form: !!document.querySelector('#id, input[name="id"]'),
    has_pw_form: !!document.querySelector('#pw, input[name="pw"], input[type="password"]'),
    has_naver_session_cookie: /NID_SES|NID_AUT/.test(document.cookie||''),
    has_relogin_msg: /다시 로그인|세션이 만료|로그인이 필요/.test(txt),
    has_mail_app: !!document.querySelector('li.mail_item, .mail_list_wrap, [class*="MailList"]'),
    body_len: txt.length,
  };
})())
"""


def _navigate_and_eval(target_id: str, url: str, wait_s: float = 4.0, timeout_total: float = 18.0) -> dict:
    sep.assert_main_page_first(url, site_key="naver")
    cdp.navigate(target_id, url)
    time.sleep(wait_s)
    deadline = time.time() + timeout_total
    while time.time() < deadline:
        data = cdp.evaluate(target_id, PAGE_SIGNAL_EXPR, timeout=6.0)
        if isinstance(data, dict) and data.get("href") and not data["href"].startswith("about:"):
            if data.get("body_len", 0) >= 50:
                return data
        time.sleep(1.0)
    return data if isinstance(data, dict) else {}


def probe_session(target_id: str) -> tuple[str, dict]:
    """www.naver.com 진입 후 세션 상태 판정."""
    data = _navigate_and_eval(target_id, "https://www.naver.com/")
    state = sep.judge_login_state("naver", data)
    return state, data


def enter_mail(target_id: str) -> tuple[str, dict]:
    """mail.naver.com 진입 + redirect 여부 판정."""
    cdp.navigate(target_id, "https://mail.naver.com/")
    time.sleep(4.0)
    cdp.wait_dom(target_id, "document.querySelector('li.mail_item, #id')", timeout=15.0)
    data = cdp.evaluate(target_id, PAGE_SIGNAL_EXPR, timeout=6.0) or {}
    href = (data.get("href") or "") if isinstance(data, dict) else ""
    if "nidlogin.login" in href:
        return NEED_MAIL_LOGIN, data
    if data.get("has_mail_app"):
        return READY, data
    if data.get("has_id_form") and data.get("has_pw_form"):
        return NEED_MAIL_LOGIN, data
    return ERROR, data


def wait_until_logged_in(
    target_id: str, *, timeout_s: float = 300.0, poll_interval_s: float = 3.0, on_status=None
) -> EntryResult:
    """사용자 수동 로그인 대기 (자동 입력 없음).

    반복적으로 www.naver.com 신호 또는 현재 위치 신호를 평가하여
    LOGGED_IN 으로 전환되는 시점을 감지한다.
    """
    deadline = time.time() + timeout_s
    last_state = ""
    while time.time() < deadline:
        # 현재 페이지 신호로 1차 확인
        data = cdp.evaluate(target_id, PAGE_SIGNAL_EXPR, timeout=6.0) or {}
        href = data.get("href", "") if isinstance(data, dict) else ""
        is_logged = bool(data.get("has_logout") or data.get("has_mypage_link"))
        is_loginpage = bool(data.get("has_id_form") and data.get("has_pw_form"))
        # mail v2 페이지 도달 또는 일반 로그인 후
        if "mail.naver.com/v2" in href and not is_loginpage:
            return EntryResult(READY, target_id, href, data.get("title", ""), notes=["mail v2 진입 감지"])
        if is_logged and "nidlogin" not in href:
            # www.naver.com 또는 다른 로그인 완료 페이지
            return EntryResult("LOGGED_IN", target_id, href, data.get("title", ""))
        state = "WAIT_LOGIN" if is_loginpage else ("LOGGED_IN" if is_logged else "UNKNOWN")
        if state != last_state and on_status:
            on_status(state, href)
            last_state = state
        time.sleep(poll_interval_s)
    return EntryResult(TIMED_OUT, target_id)

"""로그인 자동 탐지 + 저장 모듈.

CDP 포트의 활성 탭을 모니터링하여 로그인을 감지하면 자동으로 세션을 저장합니다.

주기적으로:
1. 현재 활성 탭의 URL과 DOM 상태 확인
2. 로그인 패턴 매칭
3. 로그인 감지되면 자동 저장 + 로깅
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from scripts.logger import get_logger
from scripts import cdp_db

_log = get_logger(__name__)

# 사이트별 로그인 감지 패턴
LOGIN_PATTERNS = {
    "naver": {
        "domains": ["naver.com", "mail.naver.com"],
        "logged_in_signs": [
            ("selector", "#gnb_my_name"),
            ("selector", ".gnb_id"),
            ("selector", "[class*='MyView']"),
        ],
    },
    "google": {
        "domains": ["google.com", "mail.google.com", "drive.google.com"],
        "logged_in_signs": [
            ("selector", "[data-ogsr-up]"),
            ("selector", "a[href*='SignOut']"),
        ],
    },
    "kakao": {
        "domains": ["kakao.com", "accounts.kakao.com"],
        "logged_in_signs": [
            ("selector", ".thumb_profile"),
            ("selector", "[class*='profile']"),
        ],
    },
    "eum.cw.or.kr": {
        "domains": ["eum.cw.or.kr"],
        "logged_in_signs": [
            ("text", "로그아웃"),  # 로그아웃 버튼 존재 = 로그인됨
            ("selector", "[class*='logout']"),
        ],
    },
}


def _extract_domain(url: str) -> str:
    """URL에서 도메인 추출."""
    match = re.search(r"https?://(?:www\.)?([^/?]+)", url)
    return match.group(1) if match else ""


def _find_site_by_domain(domain: str) -> str | None:
    """도메인으로 사이트 이름 찾기."""
    for site, config in LOGIN_PATTERNS.items():
        for d in config["domains"]:
            if d in domain:
                return site
    return None


def _check_login_on_page(page_content: str) -> bool:
    """페이지 내용에서 로그인 여부 판단."""
    if not page_content:
        return False

    # 로그아웃 링크 존재 여부로 판단
    logout_indicators = ["로그아웃", "logout", "sign out", "log out"]
    return any(ind.lower() in page_content.lower() for ind in logout_indicators)


def detect_login_on_current_tab(page) -> tuple[bool, str | None]:
    """현재 활성 탭에서 로그인 감지.

    Returns:
        (로그인_여부, 감지된_사이트명)
    """
    try:
        if not page:
            return False, None

        url = page.url
        domain = _extract_domain(url)
        site = _find_site_by_domain(domain)

        if not site:
            # 등록되지 않은 사이트는 로그인 감지 안함
            return False, None

        # 페이지 내용 획득
        try:
            body_text = page.evaluate("() => document.body.innerText || ''")
            is_logged_in = _check_login_on_page(body_text)

            if is_logged_in:
                _log.info("[login-detector] %s에서 로그인 감지: %s", site, url)
                return True, site
        except Exception as e:
            _log.debug("[login-detector] 페이지 내용 획득 실패 (%s): %s", site, e)

        return False, None

    except Exception as e:
        _log.debug("[login-detector] 오류: %s", e)
        return False, None


def save_detected_login(site: str, page=None) -> bool:
    """감지된 로그인을 DB에 저장.

    Args:
        site: 사이트명
        page: (선택사항) Playwright Page 객체

    Returns:
        저장 성공 여부
    """
    try:
        cdp_db.init_db()
        cdp_db.upsert_session(
            site_name=site,
            display=site.title(),
            logged_in=True,
            login_event=True
        )
        _log.info("[login-detector] %s 세션 저장됨", site)
        return True
    except Exception as e:
        _log.error("[login-detector] %s 세션 저장 실패: %s", site, e)
        return False


def monitor_for_login(page, check_interval: int = 10, timeout_s: int = 300) -> dict[str, Any]:
    """페이지에서 로그인을 모니터링하고 감지 시 자동 저장.

    Args:
        page: Playwright Page 객체
        check_interval: 체크 간격 (초)
        timeout_s: 최대 모니터링 시간 (초)

    Returns:
        {detected, site, url, elapsed_s}
    """
    start_time = time.time()
    detected_sites = set()

    while time.time() - start_time < timeout_s:
        try:
            is_logged_in, site = detect_login_on_current_tab(page)

            if is_logged_in and site and site not in detected_sites:
                detected_sites.add(site)
                save_detected_login(site, page)

                elapsed = int(time.time() - start_time)
                _log.info("[login-detector] 로그인 감지 + 저장 완료 (%ds 경과)", elapsed)

                return {
                    "detected": True,
                    "site": site,
                    "url": page.url,
                    "elapsed_s": elapsed,
                    "sites": list(detected_sites),
                }

            time.sleep(check_interval)

        except Exception as e:
            _log.debug("[login-detector] 모니터링 오류: %s", e)
            time.sleep(check_interval)

    elapsed = int(time.time() - start_time)
    return {
        "detected": len(detected_sites) > 0,
        "sites": list(detected_sites),
        "elapsed_s": elapsed,
        "timeout": True,
    }

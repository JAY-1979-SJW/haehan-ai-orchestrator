"""로그인 판별 — 쿠키 마커 기반 (페이지 이동 없음).

기존 login_session.py의 _probe()가 매번 LOGIN_PROBE_URLS로 page.goto()를
호출해 작업 흐름을 끊고, 보안 엄격 사이트(네이버 등)의 강제 로그아웃을
유발하던 문제를 제거하기 위한 모듈.

판별 방식:
    page.context.cookies() 로 현재 컨텍스트의 쿠키를 조회한 뒤
    사이트별 인증 마커 쿠키 존재 여부만 확인. 페이지를 이동하지 않음.

사용법:
    from scripts.auth.login_check import is_logged_in_by_cookie
    if is_logged_in_by_cookie(page, "google"):
        ...
"""

from __future__ import annotations

from playwright.sync_api import Page

# 사이트 별칭 → 도메인 매핑
_SITE_DOMAIN: dict[str, str] = {
    "google": "google.com",
    "gmail": "google.com",
    "calendar": "google.com",
    "drive": "google.com",
    "docs": "google.com",
    "sheets": "google.com",
    "youtube": "youtube.com",
    "naver": "naver.com",
    "blog": "naver.com",
    "cafe": "naver.com",
    "kakao": "kakao.com",
    "github": "github.com",
    "data.go.kr": "data.go.kr",
    "공공데이터포털": "data.go.kr",
}

# 도메인 → 인증 쿠키 마커 (cdp_session_manager.LOGIN_MARKERS와 동일 규칙)
_LOGIN_MARKERS: dict[str, list[str]] = {
    "google.com": ["SID", "HSID", "SSID", "APISID", "SAPISID"],
    "youtube.com": ["LOGIN_INFO", "SID"],
    "naver.com": ["NID_AUT", "NID_SES"],
    "kakao.com": ["_kawlt", "_kahai", "TIARA"],
    "github.com": ["user_session", "logged_in"],
    "data.go.kr": ["data_username", "SSO_COOKIE"],
}


def _domain_of(site: str) -> str:
    return _SITE_DOMAIN.get(site.lower(), site.lower())


def is_logged_in_by_cookie(page: Page, site: str) -> bool:
    """현재 페이지 컨텍스트의 쿠키만으로 로그인 여부 판별.

    페이지 이동 없음. 작업 중인 탭의 위치를 보존.
    """
    domain = _domain_of(site)
    markers = _LOGIN_MARKERS.get(domain, [])

    try:
        cookies = page.context.cookies()
    except Exception:  # noqa: BLE001 - 쿠키 마커 기반 로그인 판별(is_logged_in_by_cookie, 읽기전용) - 쿠키 조회 실패 시 False(미로그인 으로 간주)를 반환하는 안전한 방향의 기본값, 자격증명 값 자체는 노출하지 않고 쿠키 이름 존재 여부만 확인
        return False

    found_names = {c.get("name", "") for c in cookies if domain in (c.get("domain", "") or "")}

    if not markers:
        # 마커 미등록 도메인 — 도메인 쿠키 1개 이상이면 로그인으로 간주
        return len(found_names) > 0

    return any(m in found_names for m in markers)

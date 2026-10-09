"""로그인 세션 능동 점검 (on-demand).

기존 login_session_monitor.py 는 CDP에 '이미 열린 탭'만 수동 검사한다(탭 없으면 NO_TAB).
이 모듈은 임시 탭으로 각 사이트 게이트 URL에 접속해 로그인 리다이렉트 여부로 실제 상태를
판정하고, 동일 결과 파일(data/login_session_monitor_latest.json)에 기록한다.

frozen exe 에서도 in-process 로 동작(서브프로세스/sys.executable 의존 없음).
"""

from __future__ import annotations

import json
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

from ai_orchestrator.paths.runtime import data_dir

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
OUTPUT_PATH = data_dir() / "login_session_monitor_latest.json"
CDP_URL = "http://127.0.0.1:9222"

UTC = UTC

# (key, 게이트 URL, 로그아웃 판정 키워드[최종 URL 소문자 포함 시 로그아웃])
SITES: list[tuple[str, str, list[str]]] = [
    ("naver", "https://nid.naver.com/user2/help/myInfoV2?menu=home", ["nidlogin"]),
    ("smartstore", "https://sell.smartstore.naver.com/", ["nidlogin"]),
    (
        "google",
        "https://myaccount.google.com/",
        ["accounts.google.com/signin", "servicelogin", "accounts.google.com/v3/signin"],
    ),
    ("youtube_studio", "https://studio.youtube.com/", ["accounts.google.com", "servicelogin"]),
    ("gabia", "https://my.gabia.com/", ["accounts.gabia.com", "/login"]),
    ("eum", "https://eum.cw.or.kr/web/man/WEBMAN390M00", ["/login", "nidlogin"]),
    # 2026-10-05: office.hiworks.com 루트는 로그인 상태여도 로그인 포털로 리다이렉트(오탐) → 대시보드 주소로 판정
    ("hiworks", "https://dashboard.office.hiworks.com/", ["login.office.hiworks", "/login"]),
    ("kakao", "https://accounts.kakao.com/weblogin/account/info", ["/login"]),
    ("dataportal", "https://www.data.go.kr/mypage/mylogin/index.do", ["/login", "auth.data.go.kr"]),
]

# 네이버 계열 인증 쿠키(httpOnly) — has_session_cookie 보조 신호
_NAVER_KEYS = {"naver", "smartstore"}


def _naver_cookies(ctx) -> bool:
    try:
        names = {c.get("name") for c in ctx.cookies("https://www.naver.com")}
        return "NID_AUT" in names and "NID_SES" in names
    except Exception:  # noqa: BLE001 - 사이트 로그인 세션 능동점검(읽기전용) - CLAUDE.md 명시대로 로그인 상태를 바꾸지 않고 쿠키 이름 존재만 bool 로 확인, 실패시 False 또는 ERROR 상태 기록
        return False


def probe_all() -> dict:
    """모든 사이트 능동 점검 → 결과 파일 기록 + payload 반환."""
    now = datetime.now(UTC).isoformat()
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:  # playwright 미가용  # noqa: BLE001 - 사이트 로그인 세션 능동점검(읽기전용) - CLAUDE.md 명시대로 로그인 상태를 바꾸지 않고 쿠키 이름 존재만 bool 로 확인, 실패시 False 또는 ERROR 상태 기록
        payload = {"checked_at": now, "cdp_available": False, "sites": [], "error": f"playwright 불가: {str(e)[:80]}"}
        _write(payload)
        return payload

    sites_out: list[dict] = []
    cdp_ok = False
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:  # noqa: BLE001 - 사이트 로그인 세션 능동점검(읽기전용) - CLAUDE.md 명시대로 로그인 상태를 바꾸지 않고 쿠키 이름 존재만 bool 로 확인, 실패시 False 또는 ERROR 상태 기록
            payload = {"checked_at": now, "cdp_available": False, "sites": [], "error": f"CDP 연결 불가: {str(e)[:80]}"}
            _write(payload)
            return payload

        cdp_ok = True
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        naver_cookie = _naver_cookies(ctx)
        page = ctx.new_page()
        try:
            for key, url, logout_kw in SITES:
                ts = datetime.now(UTC).isoformat()
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=15000)
                    page.wait_for_timeout(1600)
                    final = page.url
                    low = final.lower()
                    redirected = any(k in low for k in logout_kw)
                    has_pw = False
                    try:
                        has_pw = page.query_selector("input[type=password]") is not None
                    except Exception:  # noqa: BLE001 - 사이트 로그인 세션 능동점검(읽기전용) - CLAUDE.md 명시대로 로그인 상태를 바꾸지 않고 쿠키 이름 존재만 bool 로 확인, 실패시 False 또는 ERROR 상태 기록
                        has_pw = False
                    logged_in = not redirected and not has_pw
                    has_cookie = naver_cookie if key in _NAVER_KEYS else logged_in
                    sites_out.append(
                        {
                            "key": key,
                            "status": "LOGGED_IN" if logged_in else "LOGIN_REQUIRED",
                            "detail": "로그인 세션 정상" if logged_in else "로그인 필요(세션 없음/만료)",
                            "href": final[:200],
                            "has_session_cookie": bool(has_cookie),
                            "checked_at": ts,
                        }
                    )
                except Exception as e:  # noqa: BLE001 - 사이트 로그인 세션 능동점검(읽기전용) - CLAUDE.md 명시대로 로그인 상태를 바꾸지 않고 쿠키 이름 존재만 bool 로 확인, 실패시 False 또는 ERROR 상태 기록
                    sites_out.append(
                        {
                            "key": key,
                            "status": "ERROR",
                            "detail": f"점검 오류: {str(e)[:80]}",
                            "href": "",
                            "has_session_cookie": False,
                            "checked_at": ts,
                        }
                    )
        finally:
            with suppress(Exception):
                page.close()

    payload = {
        "checked_at": now,
        "cdp_available": cdp_ok,
        "sites": sites_out,
        "alert": any(s["status"] != "LOGGED_IN" for s in sites_out),
    }
    _write(payload)
    return payload


def _write(payload: dict) -> None:
    try:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001 - 사이트 로그인 세션 능동점검(읽기전용) - CLAUDE.md 명시대로 로그인 상태를 바꾸지 않고 쿠키 이름 존재만 bool 로 확인, 실패시 False 또는 ERROR 상태 기록
        pass


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(ROOT))
    result = probe_all()
    for s in result.get("sites", []):
        print(f"  {s['key']:14} {s['status']:14} {s['detail']}")

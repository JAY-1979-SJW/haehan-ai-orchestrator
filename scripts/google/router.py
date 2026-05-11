"""Google 서비스 라우터"""
from __future__ import annotations

from . import calendar, docs, drive, gmail, sheets
from .base import check_session


def run_google(site: str, task: str, sub: str, args: list[str]) -> None:
    """Google 서비스 라우팅.

    site: google | gmail
    task: session-check | login | mail | drive | calendar | docs | sheets
    """

    if site == "gmail":
        task = "mail"

    match task:
        case "session-check":
            _cmd_session_check()
        case "login":
            _cmd_login()
        case "mail":
            gmail.run(sub or "list", args)
        case "drive":
            drive.run(sub or "list", args)
        case "calendar":
            calendar.run(sub or "today", args)
        case "docs":
            docs.run(sub or "recent", args)
        case "sheets":
            sheets.run(sub or "recent", args)
        case _:
            print(f"  [오류] 알 수 없는 작업: {task}")


def _cmd_session_check() -> None:
    print("=" * 60)
    print("Google 세션 확인")
    print("=" * 60)
    result = check_session()
    if result["error"]:
        print(f"⚠  데몬 연결 실패: {result['error']}")
    elif result["logged_in"]:
        print("✓ 로그인 상태 정상")
    else:
        print("✗ 로그인 필요")
        print("  python scripts/cdp_client.py google login")
    print("=" * 60)


def _cmd_login() -> None:
    import sys
    from scripts.web_connector import browser_session
    from scripts.login_session import is_logged_in
    from scripts.config import LOGIN_PROBE_URLS

    print("=" * 60)
    print("Google 로그인")
    print("=" * 60)

    with browser_session() as page:
        page.goto(LOGIN_PROBE_URLS["google"], timeout=60000)
        if is_logged_in(page, "google"):
            print("✓ 이미 로그인 상태입니다")
        elif sys.stdin.isatty():
            print("\n브라우저에서 Google에 로그인하세요")
            input("👉 로그인 완료 후 Enter를 누르세요: ")
            if is_logged_in(page, "google"):
                print("✓ 로그인 완료")
            else:
                print("⚠  로그인 확인 실패 — 다시 시도하세요")
        else:
            print("\n브라우저에 Google 페이지를 열었습니다")
            print("브라우저에서 직접 로그인 후, 아래 명령으로 세션 확인:")
            print("  python scripts/cdp_client.py google session-check")

    print("=" * 60)

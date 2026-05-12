"""Google 서비스 라우터"""
from __future__ import annotations

from . import calendar, docs, drive, gmail, sheets
from .base import check_session
from scripts.gate import check as gate_check

__status__ = {
    "tasks": {
        "mail list":      "done",
        "mail compose":   "done",
        "mail send":      "done",
        "drive list":     "partial",
        "calendar today": "partial",
        "docs recent":    "partial",
        "sheets recent":  "partial",
        "login":          "done",
        "session-check":  "done",
    },
    "note": "Gmail 완성, Drive/Calendar/Docs/Sheets는 라우터 연결만 완료(기능 검증 필요)",
}


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
            gate_check("wait_login", risk="notify")
            _cmd_login()
        case "mail":
            gate_check("gmail_send" if sub in ("send", "compose") else "goto",
                       risk="approve" if sub in ("send", "compose") else "auto")
            gmail.run(sub or "list", args)
        case "drive":
            gate_check("goto")
            drive.run(sub or "list", args)
        case "calendar":
            gate_check("goto")
            calendar.run(sub or "today", args)
        case "docs":
            gate_check("goto")
            docs.run(sub or "recent", args)
        case "sheets":
            gate_check("goto")
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
    """ID/PW 자동 로그인 (네이버 방식 동일)."""
    from scripts.web_connector import get_page
    from scripts.google.auth import login_google

    print("=" * 60)
    print("Google 자동 로그인 (ID/PW)")
    print("=" * 60)
    page = get_page()
    result = login_google(page, wait_for_user_s=300)
    if result["ok"]:
        print(f"✓ 로그인 성공: {result.get('user')}  ({result.get('reason')})")
    else:
        print(f"✗ 로그인 실패: {result.get('reason')}")
        if result.get("hint"):
            print(f"  힌트: {result['hint']}")
    print("=" * 60)

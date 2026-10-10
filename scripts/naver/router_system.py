"""네이버 시스템/세션/카탈로그/로그인 명령 핸들러"""
from __future__ import annotations

from scripts.common.gate import check as gate_check
from .base import check_session


__status__ = {
    "tasks": {
        "blog write":   "done",
        "blog publish": "done",
        "mail inbox":   "done",
        "mail compose": "done",
        "mail send":    "done",
        "content explore": "done",
        "content actions": "done",
        "company seo": "done",
        "company seo assets": "done",
        "company seo ownership": "done",
        "company seo exposure": "done",
        "company seo submit-plan": "done",
        "company seo monitor": "done",
        "developers entrypoints": "done",
        "shopping competitors": "done",
        "keyword tools": "done",
        "excel report": "done",
        "cafe list": "done",
        "cafe posts": "done",
        "cafe read": "done",
        "cafe write": "done",
        "calendar list/add": "done",
        "mybox list/search/upload": "done",
        "pay orders/points": "done",
        "talk list/send": "done",
        "place list/reviews": "done",
        "smartstore alias": "done",
        "service catalog": "done",
        "login":        "done",
        "session-check":"done",
    },
    "note": "블로그 글쓰기·발행, 메일 수신/발송 자동화 완성",
}


def _cmd_catalog() -> None:
    from scripts.naver.service_catalog import build_catalog, print_catalog_summary, save_catalog

    gate_check("scan_page")
    catalog = build_catalog()
    path = save_catalog(catalog)
    print_catalog_summary(catalog, path)


def _cmd_session_check() -> None:
    print("=" * 60)
    print("네이버 세션 확인")
    print("=" * 60)
    result = check_session()

    if result["error"]:
        print(f"[WARNING] 데몬 연결 실패: {result['error']}")
        print("  python scripts/browser/cdp/cdp_daemon.py start")
    elif result["logged_in"]:
        print("[OK] 로그인 상태 정상")
    else:
        print("[X] 로그인 필요")
        print("  python scripts/entry/cdp_cli.py naver login")

    print("=" * 60)


def _cmd_login() -> None:
    """네이버 로그인 — 브라우저에서 사용자가 로그인하면 자동 감지.

    input() / 터미널 입력 없음. 앱에서 호출 시에도 동일하게 동작.
    CDP 데몬이 꺼져 있으면 자동 시작 후 연결.
    """
    from scripts.browser.page.web_connector import browser_session  # noqa: I001 - 이동 전부터 있던 미정렬 import(동작 변경 없음)
    from scripts.site_engine.login_session import is_logged_in
    from scripts.auth.login_detector import monitor_for_login
    from scripts.naver.browser_gate import require_naver_browser

    print("=" * 60)
    print("네이버 로그인")
    print("=" * 60)

    require_naver_browser()
    with browser_session() as page:
        page.goto("https://www.naver.com/", timeout=60000)

        if is_logged_in(page, "naver"):
            print("[OK] 이미 로그인 상태입니다")
            print("=" * 60)
            return

        print("\n브라우저에서 네이버에 로그인하세요 (최대 5분 대기)")
        print("로그인 완료되면 자동으로 진행됩니다\n")

        # 터미널 input() 없이 로그인 자동 감지
        result = monitor_for_login(page, check_interval=2, timeout_s=300)

        if result.get("detected"):
            print(f"[OK] 로그인 감지 완료 — {result.get('elapsed_s', 0):.0f}초")
        else:
            reason = result.get("aborted_reason", "timeout")
            print(f"[WARNING] 로그인 미감지 — {reason}")
            print("   브라우저에서 로그인 완료 후 다시 시도하세요")

    print("=" * 60)

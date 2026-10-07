"""카카오 서비스 라우터"""

from __future__ import annotations

from scripts.common.gate import check as gate_check

from . import dev_console
from .base import check_session

__status__ = {
    "tasks": {
        "session-check": "done",
        "login": "done",
        "dev console": "partial",
    },
    "note": "로그인·세션 확인 완성, 개발콘솔은 기본 연결만 구현",
}


def run_kakao(task: str, sub: str, args: list[str]) -> None:
    """카카오 서비스 라우팅.

    task: session-check | login | dev
    sub : list | info | register 등
    """
    match task:
        case "session-check":
            _cmd_session_check()
        case "login":
            gate_check("wait_login", risk="notify")
            _cmd_login()
        case "dev":
            gate_check("goto")
            dev_console.run(sub or "list", args)
        case _:
            print(f"  [오류] 알 수 없는 작업: {task}")


def _cmd_session_check() -> None:
    print("=" * 60)
    print("카카오 세션 확인")
    print("=" * 60)
    result = check_session()
    if result["error"]:
        print(f"⚠  데몬 연결 실패: {result['error']}")
    elif result["logged_in"]:
        print("✓ 로그인 상태 정상")
    else:
        print("✗ 로그인 필요")
        print("  python scripts/entry/cdp_cli.py kakao login")
    print("=" * 60)


def _cmd_login() -> None:
    from scripts.kakao.auth import login
    from scripts.browser.page.web_connector import browser_session

    print("=" * 60)
    print("카카오 로그인")
    print("=" * 60)

    with browser_session() as page:
        result = login(page)
        if result.get("ok"):
            print("✓ 이미 로그인 상태입니다")
        else:
            print("\n브라우저에서 카카오 계정으로 로그인하세요 (최대 5분 대기)")
            from scripts.auth.login_detector import monitor_for_login

            detected = monitor_for_login(page, check_interval=2, timeout_s=300)
            if detected.get("detected"):
                print(f"✓ 로그인 감지 완료 — {detected.get('elapsed_s', 0):.0f}초")
            else:
                print(f"⚠  로그인 미감지 — {detected.get('aborted_reason', 'timeout')}")

    print("=" * 60)

"""카카오 서비스 라우터"""
from __future__ import annotations

from . import dev_console
from .base import check_session
from scripts.gate import check as gate_check


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
        print("  python scripts/cdp_client.py kakao login")
    print("=" * 60)


def _cmd_login() -> None:
    from scripts.web_connector import browser_session
    from scripts.login_session import is_logged_in
    from .base import KAKAO_DEV_URL

    print("=" * 60)
    print("카카오 로그인")
    print("=" * 60)

    with browser_session() as page:
        page.goto(KAKAO_DEV_URL, timeout=60000)
        if is_logged_in(page, "kakao"):
            print("✓ 이미 로그인 상태입니다")
        else:
            print("\n브라우저에서 카카오 계정으로 로그인하세요")
            input("👉 로그인 완료 후 Enter를 누르세요: ")
            if is_logged_in(page, "kakao"):
                print("✓ 로그인 완료")
            else:
                print("⚠  로그인 확인 실패 — 다시 시도하세요")

    print("=" * 60)

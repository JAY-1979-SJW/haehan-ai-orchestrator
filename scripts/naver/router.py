"""네이버 서비스 라우터"""
from __future__ import annotations

from . import blog, mail
from .base import check_session
from scripts.gate import check as gate_check

__status__ = {
    "tasks": {
        "blog write":   "done",
        "blog publish": "done",
        "mail inbox":   "done",
        "mail compose": "done",
        "mail send":    "done",
        "login":        "done",
        "session-check":"done",
    },
    "note": "블로그 글쓰기·발행, 메일 수신/발송 자동화 완성",
}


def run_naver(task: str, sub: str, args: list[str]) -> None:
    """네이버 서비스 라우팅.

    task: blog | mail | session-check | login
    sub: write / inbox / compose 등 하위 명령
    """
    match task:
        case "blog":
            _gate_blog(sub)
            blog.run(sub or "write", args)
        case "mail":
            _gate_mail(sub)
            mail.run(sub or "inbox", args)
        case "session-check":
            _cmd_session_check()
        case "login":
            gate_check("wait_login", risk="notify")
            _cmd_login()
        case _:
            print(f"  [오류] 알 수 없는 작업: {task}")


def _gate_blog(sub: str) -> None:
    if sub in ("publish", "send"):
        gate_check("blog_publish")       # APPROVE — 외부 공개
    elif sub in ("write", "draft", None, ""):
        gate_check("write_blog_post")    # APPROVE — 비가역 초안 작성
    else:
        gate_check("goto")               # AUTO — 읽기


def _gate_mail(sub: str) -> None:
    if sub in ("send", "compose"):
        gate_check("naver_mail_send")    # APPROVE — 외부 발송
    else:
        gate_check("goto")               # AUTO — 수신함 조회


def _cmd_session_check() -> None:
    print("=" * 60)
    print("네이버 세션 확인")
    print("=" * 60)
    result = check_session()

    if result["error"]:
        print(f"⚠  데몬 연결 실패: {result['error']}")
        print("  python scripts/cdp_daemon.py start")
    elif result["logged_in"]:
        print("✓ 로그인 상태 정상")
    else:
        print("✗ 로그인 필요")
        print("  python scripts/cdp_client.py naver login")

    print("=" * 60)


def _cmd_login() -> None:
    import sys
    from scripts.web_connector import browser_session
    from scripts.login_session import is_logged_in

    print("=" * 60)
    print("네이버 로그인")
    print("=" * 60)

    with browser_session() as page:
        page.goto("https://www.naver.com/", timeout=60000)

        if is_logged_in(page, "naver"):
            print("✓ 이미 로그인 상태입니다")
        elif sys.stdin.isatty():
            print("\n브라우저에서 네이버에 로그인하세요")
            input("👉 로그인 완료 후 Enter를 누르세요: ")
            if is_logged_in(page, "naver"):
                print("✓ 로그인 완료")
            else:
                print("⚠  로그인 확인 실패 — 다시 시도하세요")
        else:
            print("\n브라우저에 네이버 페이지를 열었습니다")
            print("브라우저에서 직접 로그인 후, 아래 명령으로 세션 확인:")
            print("  python scripts/cdp_client.py naver session-check")

    print("=" * 60)

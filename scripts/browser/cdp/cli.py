"""CDP 데몬 클라이언트 CLI 진입부 — cdp_client.py(라이브러리)에서 분리.

cdp_client.py 는 CDP 제어 라이브러리라 scripts/router.py(최상위 서비스 디스패처,
L5 성격)를 몰라야 한다(기반이 상위를 import하면 역방향 — module_cycles 유발).
이 모듈이 그 반대: router 를 알고, cdp_client 의 명령 핸들러들을 모아 디스패치한다.

사용법은 scripts/browser/cdp/cdp_client.py 의 docstring과 동일 — 명령 처리 로직만
여기로 옮겼다(동작 변경 없음, 2026-10-07 STD-08 후속 리팩터).
"""

from __future__ import annotations

import sys
from collections.abc import Callable

from scripts.browser.cdp.cdp_client import (
    _cmd_analyze,
    _cmd_auto_login,
    _cmd_check_login,
    _cmd_chrome_ui_monitor,
    _cmd_click_button,
    _cmd_click_link,
    _cmd_close_popup,
    _cmd_crawl,
    _cmd_crawl_here,
    _cmd_cred,
    _cmd_detect_popup,
    _cmd_explore,
    _cmd_gabia,
    _cmd_gate,
    _cmd_goto,
    _cmd_handle_draft_popup,
    _cmd_is_ready,
    _cmd_login_watch,
    _cmd_op_log,
    _cmd_open,
    _cmd_paste_image,
    _cmd_popup_auto,
    _cmd_popup_install,
    _cmd_popup_monitor,
    _cmd_popup_poll,
    _cmd_save_session,
    _cmd_scan_links,
    _cmd_scan_page,
    _cmd_session,
    _cmd_snapshot,
    _cmd_type_into,
    _cmd_user_watch,
    _cmd_verify_input,
    _cmd_verify_text,
    _cmd_visits,
    _cmd_wait_login,
    _cmd_write_post,
)

_SITE_ROUTER_CMDS = (
    "naver",
    "google",
    "gmail",
    "youtube",
    "kakao",
    "eum",
    "hiworks",
    "gabia",
    "smartstore",
    "g2b",
    "local",
)


def _cmd_site_router(cmd: str, task: str, sub: str, args: list[str]) -> None:
    # 'explore' 는 신규 통합 사이트 탐색에 양보 (아래 case로 처리)
    from scripts.router import dispatch

    dispatch(cmd, task, sub, args)


def _cmd_services() -> None:
    from scripts.router import list_services

    rows = list_services()
    print(f"{'명령':<14} {'라우터 모듈'}")
    print("-" * 56)
    for r in rows:
        alias = " (alias)" if r.get("alias") else ""
        print(f"{r['cmd']:<14} {r['module']}{alias}")


# cmd 문자열 → 핸들러 매핑. 원래 match cmd: 의 case 순서를 그대로 옮긴 것 — 동작은 동일하다.
# (2026-09-29 STD-08: match 는 case 40개를 mccabe/pylint 가 "분기 40개"로 그대로 세어(각
# 본문이 한 줄 호출이어도) 복잡도를 못 벗어났다 — dict 조회로 바꿔 실제로 해소했다.)
_HANDLERS: dict[str, Callable[[str, str, list[str]], None]] = {
    "check-login": lambda task, sub, args: _cmd_check_login(),
    "goto": lambda task, sub, args: _cmd_goto(task),
    "wait-login": lambda task, sub, args: _cmd_wait_login(task, sub),
    "save-session": lambda task, sub, args: _cmd_save_session(task),
    "write-post": lambda task, sub, args: _cmd_write_post(task, sub, args),
    "paste-image": lambda task, sub, args: _cmd_paste_image(task, sub),
    "handle-draft-popup": lambda task, sub, args: _cmd_handle_draft_popup(),
    "is-ready": lambda task, sub, args: _cmd_is_ready(task, sub, args),
    "verify-input": lambda task, sub, args: _cmd_verify_input(task, sub, args),
    "verify-text": lambda task, sub, args: _cmd_verify_text(task, sub, args),
    "scan-links": lambda task, sub, args: _cmd_scan_links(),
    "scan-page": lambda task, sub, args: _cmd_scan_page(),
    "type-into": lambda task, sub, args: _cmd_type_into(task, sub, args),
    "click-button": lambda task, sub, args: _cmd_click_button(task),
    "click-link": lambda task, sub, args: _cmd_click_link(task),
    "popup-install": lambda task, sub, args: _cmd_popup_install(),
    "detect-popup": lambda task, sub, args: _cmd_detect_popup(),
    "close-popup": lambda task, sub, args: _cmd_close_popup(),
    "popup-poll": lambda task, sub, args: _cmd_popup_poll(),
    "popup-auto": lambda task, sub, args: _cmd_popup_auto(),
    "popup-monitor": lambda task, sub, args: _cmd_popup_monitor(task, sub, args),
    "chrome-ui-monitor": lambda task, sub, args: _cmd_chrome_ui_monitor(task, sub),
    "analyze": lambda task, sub, args: _cmd_analyze(),
    "crawl": lambda task, sub, args: _cmd_crawl(task, sub, args),
    "explore": lambda task, sub, args: _cmd_explore(task, sub, args),
    "crawl-here": lambda task, sub, args: _cmd_crawl_here(task, sub, args),
    "explore-here": lambda task, sub, args: _cmd_crawl_here(task, sub, args),
    "snapshot": lambda task, sub, args: _cmd_snapshot(),
    "snap": lambda task, sub, args: _cmd_snapshot(),
    "visits": lambda task, sub, args: _cmd_visits(task),
    "session": lambda task, sub, args: _cmd_session(task, sub),
    "open": lambda task, sub, args: _cmd_open(task, sub, args),
    "user-watch": lambda task, sub, args: _cmd_user_watch(task, sub),
    "gabia": lambda task, sub, args: _cmd_gabia(task, sub, args),
    "auto-login": lambda task, sub, args: _cmd_auto_login(task, sub),
    "login-watch": lambda task, sub, args: _cmd_login_watch(task, sub),
    "cred": lambda task, sub, args: _cmd_cred(task, sub),
    "credentials": lambda task, sub, args: _cmd_cred(task, sub),
    "services": lambda task, sub, args: _cmd_services(),
    "gate": lambda task, sub, args: _cmd_gate(task, sub),
    "op-log": lambda task, sub, args: _cmd_op_log(task, sub),
}


def _dispatch(cmd: str, task: str, sub: str, args: list[str]) -> None:
    # 원본 match 의 순서를 그대로 보존: _SITE_ROUTER_CMDS 를 _HANDLERS 조회보다 먼저 본다.
    # "gabia" 는 이 튜플에 이미 있어(_cmd_gabia 함수 주석 참고) _HANDLERS["gabia"] 는 원본과
    # 마찬가지로 도달 불가능하다 — 동작을 바꾸지 않기 위해 그대로 둔다.
    if cmd in _SITE_ROUTER_CMDS:
        # 'explore' 는 신규 통합 사이트 탐색에 양보 (아래 _HANDLERS["explore"] 로 처리)
        _cmd_site_router(cmd, task, sub, args)
        return
    handler = _HANDLERS.get(cmd)
    if handler is None:
        print(f"알 수 없는 명령: {cmd}")
        from scripts.browser.cdp.cdp_client import __doc__ as _cdp_client_doc

        print(_cdp_client_doc)
        return
    handler(task, sub, args)


def main() -> None:
    if len(sys.argv) < 2:
        from scripts.browser.cdp.cdp_client import __doc__ as _cdp_client_doc

        print(_cdp_client_doc)
        return

    cmd = sys.argv[1]
    task = sys.argv[2] if len(sys.argv) > 2 else ""
    sub = sys.argv[3] if len(sys.argv) > 3 else ""
    args = sys.argv[4:] if len(sys.argv) > 4 else []

    try:
        _dispatch(cmd, task, sub, args)
    except Exception as e:  # noqa: BLE001 - CDP 브라우저 데몬 제어 CLI - 상태조회/모니터 시작중지/로그인 커맨드 래퍼, 예외시 오류 출력 후 sys.exit(1) 로 실패를 명확히 알림(fail-loud)
        print(f"  [오류] {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

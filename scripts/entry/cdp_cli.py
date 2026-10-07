"""CDP 데몬 클라이언트 CLI 진입부 — cdp_client.py(라이브러리)에서 분리.

cdp_client.py 는 CDP 제어 라이브러리라 scripts/site_engine/command_router.py(최상위 서비스 디스패처,
L5 성격)·scripts/browser/navigator·popup·explorer·gabia(상위 도메인 도구)를
몰라야 한다(기반이 상위를 import하면 역방향 — module_cycles 유발). 이 모듈이
그 반대: 그것들을 알고, cdp_client 의 명령 핸들러들과 함께 모아 디스패치한다.

사용법은 scripts/entry/cdp_cli.py 의 docstring과 동일 — 명령 처리 로직만
여기로 옮겼다(동작 변경 없음, 2026-10-07 STD-08 후속 리팩터, S1-c).
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))  # `python scripts/entry/cdp_cli.py` 로 직접 실행해도 scripts 패키지를 찾는다

from scripts.browser.cdp_client import (  # noqa: E402
    _cmd_analyze,
    _cmd_auto_login,
    _cmd_check_login,
    _cmd_chrome_ui_monitor,
    _cmd_cred,
    _cmd_explore,
    _cmd_gate,
    _cmd_login_watch,
    _cmd_op_log,
    _cmd_open,
    _cmd_session,
    _cmd_user_watch,
)
from scripts.entry import site_login_registry  # noqa: E402

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
    from scripts.site_engine.command_router import dispatch

    dispatch(cmd, task, sub, args)


def _cmd_services() -> None:
    from scripts.site_engine.command_router import list_services

    rows = list_services()
    print(f"{'명령':<14} {'라우터 모듈'}")
    print("-" * 56)
    for r in rows:
        alias = " (alias)" if r.get("alias") else ""
        print(f"{r['cmd']:<14} {r['module']}{alias}")


# ── navigator 를 쓰는 핸들러 (cdp_client.py 에서 이동, S1-c) ─────────────────


def _cmd_goto(task: str) -> None:
    from scripts.browser.navigator.navigator import goto

    if not task:
        print("사용법: python scripts/entry/cdp_cli.py goto <별칭_or_URL>")
        return
    goto(task)


def _cmd_wait_login(task: str, sub: str) -> None:
    from scripts.browser.navigator.navigator import wait_login

    if not task:
        print("사용법: python scripts/entry/cdp_cli.py wait-login <사이트> [타임아웃초]")
        return
    t_out = int(sub) if sub.isdigit() else 300
    ok = wait_login(task, timeout_s=t_out)
    sys.exit(0 if ok else 1)


def _cmd_save_session(task: str) -> None:
    from scripts.browser.navigator.navigator import save_session

    save_session(task or None)


def _cmd_write_post(task: str, sub: str, args: list[str]) -> None:
    from scripts.naver.blog.navigator_blog import write_blog_post

    if not task or not sub:
        print("사용법: python scripts/entry/cdp_cli.py write-post <제목> <본문> [이미지경로]")
        return
    img = args[0] if args else None
    ok = write_blog_post(task, sub, image_path=img)
    sys.exit(0 if ok else 1)


def _cmd_paste_image(task: str, sub: str) -> None:
    from scripts.browser.navigator.navigator import paste_image

    if not task:
        print("사용법: python scripts/entry/cdp_cli.py paste-image <이미지경로> [target]")
        return
    tgt = sub if sub else "body"
    ok = paste_image(task, tgt)
    sys.exit(0 if ok else 1)


def _cmd_handle_draft_popup() -> None:
    from scripts.browser.navigator.navigator import handle_draft_restore_popup

    r = handle_draft_restore_popup()
    mark = (
        "✓ 감지+취소"
        if r["detected"] and r["action"] == "cancel_clicked"
        else ("- 미감지" if not r["detected"] else "✗ 클릭 실패")
    )
    print(f"{mark} ({r['elapsed_ms']}ms)")
    sys.exit(0 if r["action"] != "cancel_failed" else 1)


def _cmd_is_ready(task: str, sub: str, args: list[str]) -> None:
    from scripts.browser.navigator.navigator import is_ready

    check_args = [a for a in [task, sub, *args] if a]
    if not check_args:
        print("사용법: python scripts/entry/cdp_cli.py is-ready <체크1> [체크2 ...]")
        print("  예: is-ready url_contains:naver readystate has_button:발행")
        return
    r = is_ready(check_args, timeout_s=2.0)
    mark = "✓" if r["ok"] else "✗"
    print(f"{mark} ok={r['ok']} elapsed={r['elapsed_ms']}ms")
    for item in r["results"]:
        pmk = "✓" if item["passed"] else "✗"
        print(f"  {pmk} {item['check']:<40} {item['reason']}")
    sys.exit(0 if r["ok"] else 1)


def _cmd_verify_input(task: str, sub: str, args: list[str]) -> None:
    from scripts.browser.navigator.navigator import verify_input

    if not task:
        print("사용법: python scripts/entry/cdp_cli.py verify-input <텍스트>")
        return
    full = " ".join([task, sub, *args]).strip()
    v = verify_input(full)
    mark = "✓" if v["found"] else "✗"
    print(f"{mark} found={v['found']} where={v['where']} ({v['elapsed_ms']}ms)")
    if v["found"]:
        print(f"  실제값: '{v['actual']}'")
    sys.exit(0 if v["found"] else 1)


def _cmd_verify_text(task: str, sub: str, args: list[str]) -> None:
    from scripts.browser.navigator.navigator import verify_text

    if not task:
        print("사용법: python scripts/entry/cdp_cli.py verify-text <텍스트>")
        return
    full = " ".join([task, sub, *args]).strip()
    results = verify_text(full)
    # 매칭 결과 있으면 0, 없으면 1
    found = any(r["data"]["occurrences_in_innerText"] > 0 for r in results)
    sys.exit(0 if found else 1)


def _cmd_scan_links() -> None:
    from scripts.browser.navigator.navigator import scan_links

    scan_links()


def _cmd_scan_page() -> None:
    from scripts.browser.navigator.navigator import scan_page

    scan_page()


def _cmd_type_into(task: str, sub: str, args: list[str]) -> None:
    from scripts.browser.navigator.navigator import type_into

    if not task or not sub:
        print("사용법: python scripts/entry/cdp_cli.py type-into <대상> <텍스트>")
        return
    # 텍스트는 sub + args 전체를 공백 join
    full_text = " ".join([sub, *args])
    ok = type_into(task, full_text)
    sys.exit(0 if ok else 1)


def _cmd_click_button(task: str) -> None:
    from scripts.browser.navigator.navigator import click_button

    if not task:
        print("사용법: python scripts/entry/cdp_cli.py click-button <텍스트>")
        return
    ok = click_button(task)
    sys.exit(0 if ok else 1)


def _cmd_click_link(task: str) -> None:
    from scripts.browser.navigator.navigator import click_link

    if not task:
        print("사용법: python scripts/entry/cdp_cli.py click-link <텍스트>")
        return
    ok = click_link(task)
    sys.exit(0 if ok else 1)


# ── popup 을 쓰는 핸들러 (cdp_client.py 에서 이동, S1-c) ────────────────────


def _cmd_popup_install() -> None:
    from scripts.browser.navigator.popup_watcher import install_watcher

    r = install_watcher()
    print(f"✓ 팝업 감지 설치 완료 (프레임: {r['frame_count']}개)")


def _cmd_detect_popup() -> None:
    from scripts.browser.cdp.connection import get_page
    from scripts.browser.popup.popup_detector import detect_popup

    page = get_page()
    result = detect_popup(page)
    if result["detected"]:
        print(f"\n✓ {result['popup_count']}개 팝업 감지됨")
        print(f"  유형: {', '.join(result['types'])}")
        for i, elem in enumerate(result["elements"]):
            print(f"  - [{i + 1}] {elem.get('text', '')[:50]}")
    else:
        print("\n✓ 팝업 없음")
    sys.exit(0 if result["detected"] else 1)


def _cmd_close_popup() -> None:
    from scripts.browser.cdp.connection import get_page
    from scripts.browser.popup.popup_detector import close_all_popups

    page = get_page()
    result = close_all_popups(page)
    print(f"\n✓ 팝업 처리 완료: {result['total_closed']}개 닫음")
    if result["final_state"]["detected"]:
        print(f"⚠️  {result['final_state']['popup_count']}개 팝업 남아있음")
    sys.exit(0 if not result["final_state"]["detected"] else 1)


def _cmd_popup_poll() -> None:
    import json as _json

    from scripts.browser.navigator.popup_watcher import poll_events

    events = poll_events()
    if not events:
        print("☐ 팝업 이벤트 없음")
    else:
        print(f"✓ 팝업 {len(events)}개 감지:")
        for ev in events:
            print(f"  - {ev['marker']} ({ev['frame_url']})")
            print(f"    스니펫: {ev['snippet'][:100]}")
    print(_json.dumps(events, ensure_ascii=False, indent=2))


def _cmd_popup_auto() -> None:
    from scripts.browser.navigator.popup_watcher import auto_handle

    r = auto_handle()
    print("✓ 자동 처리 완료")
    print(f"  처리됨: {len(r['handled'])}개")
    print(f"  스킵: {len(r['skipped'])}개")
    print(f"  미지의: {len(r['unknown'])}개")
    if r["unknown"]:
        for u in r["unknown"]:
            print(f"    - {u['marker']}")


def _cmd_popup_monitor_start(interval: float) -> None:
    # _cmd_popup_monitor 의 "start" 분기만 분리(2026-09-29 STD-08: C901 12>10, mccabe 가
    # while/try/except 를 추가 분기로 셈 — 로직은 그대로, 함수만 나눔).
    from scripts.browser.navigator import popup_monitor as _pm

    mon = _pm.PopupMonitor(poll_interval_s=interval)
    mon.start()
    print(f"✓ popup-monitor 시작 (poll={interval}s). Ctrl+C로 종료.")
    try:
        while True:
            import time as _time

            _time.sleep(60)
    except KeyboardInterrupt:
        mon.stop()
        print("✓ popup-monitor 종료")


def _cmd_popup_monitor(task: str, sub: str, args: list[str]) -> None:
    import json as _json

    from scripts.browser.navigator import popup_monitor as _pm

    sub_cmd = task or "status"
    if sub_cmd == "start":
        interval = float(sub) if sub else 2.0
        _cmd_popup_monitor_start(interval)
    elif sub_cmd == "status":
        st = _pm.status()
        print(_json.dumps(st, ensure_ascii=False, indent=2))
    elif sub_cmd == "list":
        rows = _pm.list_pending(limit=50)
        if not rows:
            print("☐ pending 이벤트 없음")
        for r in rows:
            print(
                f"[{r['id']:>4}] {r['severity']:<8} {r['category']:<22} "
                f"action={r['action']:<14} target={r['target']!s:<8} "
                f"marker={r['marker'][:40]}"
            )
    elif sub_cmd == "ack":
        if not sub:
            print("사용법: popup-monitor ack <id> [메모]")
            return
        ok = _pm.ack_event(int(sub), note=" ".join(args))
        print("✓ ack 완료" if ok else "✗ id 없음")
    elif sub_cmd == "classify":
        from scripts.browser.popup.popup_classifier import classify

        if not sub:
            print("사용법: popup-monitor classify <marker> [snippet]")
            return
        d = classify(marker=sub, snippet=" ".join(args))
        print(_json.dumps(d, ensure_ascii=False, indent=2))
    else:
        print("사용법: popup-monitor [start|status|list|ack|classify]")


# ── explorer 를 쓰는 핸들러 (cdp_client.py 에서 이동, S1-c) ─────────────────


def _cmd_crawl(task: str, sub: str, args: list[str]) -> None:
    # 홈페이지부터 전체 자동 크롤 + 미설계 페이지 자동 반영
    import os  # noqa: F401 - 원본 그대로 보존(2026-09-29 STD-08 리팩터, 로직 변경 없음)

    from scripts.explorer.site_crawler import crawl_site
    from scripts.site_engine.site_access import LoginError, open_site
    from scripts.site_engine.site_registry import list_sites
    from scripts.site_engine.site_watch import StepFailure

    if not task:
        print("사용법: python scripts/entry/cdp_cli.py crawl <사이트> [depth=3] [max=50]")
        print(f"  지원: {list_sites()}")
        return
    args_all = ([sub] if sub else []) + list(args)
    depth = int(args_all[0]) if args_all and args_all[0].isdigit() else 3
    max_pages = int(args_all[1]) if len(args_all) > 1 and args_all[1].isdigit() else 50
    print(f"\n[작업] {task} 사이트 전체 자동 크롤 (depth={depth}, max={max_pages})")
    try:
        page = open_site(task)
        r = crawl_site(page, depth=depth, max_pages=max_pages)
        print("\n✓ 크롤 완료")
        print(f"  방문: {r['visited_count']} 페이지 / 미설계 반영: {r['discovered_count']}")
        print(f"  타입 분포: {r['type_counts']}")
        print(f"  사이트맵: {r.get('saved_to', '')}")
        if r.get("aborted_reason"):
            print(f"  중단: {r['aborted_reason']}")
    except StepFailure as e:
        print(f"\n✘ 로그인 단계 실패: {e.step} ({e.kind})")
        print(f"   사유: {e.message}")
        print(f"   보고서: {e.report_dir}")
        sys.exit(1)
    except LoginError as e:
        print(f"\n✘ {e}")
        sys.exit(1)
    except Exception as e:  # noqa: BLE001 - CDP 브라우저 데몬 제어 CLI - 상태조회/모니터 시작중지/로그인 커맨드 래퍼, 예외시 오류 출력 후 sys.exit(1) 로 실패를 명확히 알림(fail-loud)
        print(f"\n  [오류] {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def _cmd_crawl_here(task: str, sub: str, args: list[str]) -> None:
    # 로그인 안 거치고 현재 활성 탭부터 BFS 탐색 (사용자 수동 로그인 후 사용)
    from scripts.browser.cdp.connection import get_page
    from scripts.explorer.site_crawler import crawl_site

    args_all = ([task] if task else []) + ([sub] if sub else []) + list(args)
    depth = int(args_all[0]) if args_all and args_all[0].isdigit() else 2
    max_pages = int(args_all[1]) if len(args_all) > 1 and args_all[1].isdigit() else 30
    print(f"\n[작업] 현재 탭부터 탐색 (depth={depth}, max={max_pages}, 로그인 우회)")
    try:
        page = get_page()
        print(f"  시작 탭: {page.url}")
        r = crawl_site(
            page,
            start_url=None,  # 현재 페이지 그대로
            depth=depth,
            max_pages=max_pages,
            from_homepage_root=False,  # 홈으로 안 보냄 (현재 상태 유지)
            handle_popups=True,
            bot_check_each=True,
        )
        print(f"\n✓ 탐색 완료 — 방문 {r['visited_count']} 페이지")
        print(f"  타입 분포: {r['type_counts']}")
        print(f"  미설계 페이지: {r['discovered_count']}")
        if r.get("saved_to"):
            print(f"  사이트맵: {r['saved_to']}")
        if r.get("aborted_reason"):
            print(f"  중단: {r['aborted_reason']}")
    except Exception as e:  # noqa: BLE001 - CDP 브라우저 데몬 제어 CLI - 상태조회/모니터 시작중지/로그인 커맨드 래퍼, 예외시 오류 출력 후 sys.exit(1) 로 실패를 명확히 알림(fail-loud)
        print(f"  [오류] {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def _cmd_snapshot() -> None:
    # 현재 활성 탭을 1회 분석 + 저장 (수동 탐색)
    from scripts.explorer.manual_snapshot import cli_snapshot

    cli_snapshot()


def _cmd_visits(task: str) -> None:
    # 저장된 수동 스냅샷 목록
    from scripts.explorer.manual_snapshot import cli_list

    cli_list(task or "")


# ── gabia 를 쓰는 핸들러 (cdp_client.py 에서 이동, S1-c) ────────────────────


def _cmd_gabia(task: str, sub: str, args: list[str]) -> None:
    # NOTE(2026-09-29 STD-08 리팩터 중 발견, 이번엔 그대로 보존): 아래 _SITE_ROUTER_CMDS
    # 가드에 "gabia" 가 이미 포함돼 있어 원본에서도 이 함수는 도달 불가능한 코드였다(match 는
    # 위에서부터 순서대로 첫 매치를 쓴다). 동작을 바꾸지 않는 것이 이번 작업 범위라 그대로 옮기고,
    # 별도로 사용자에게 보고한다 — 고치는 건 별도 승인 사항.
    match task:
        case "login-watch":
            from scripts.gabia.login_watch import watch_gabia_login

            timeout_s = int(sub) if sub and sub.isdigit() else 300
            no_nav = "--no-navigate" in args
            result = watch_gabia_login(timeout_s=timeout_s, navigate_after=not no_nav)
            sys.exit(0 if result["logged_in"] else 1)
        case _:
            print("가비아 명령:")
            print("  python scripts/entry/cdp_cli.py gabia login-watch [타임아웃초]")
            print("  python scripts/entry/cdp_cli.py gabia login-watch [타임아웃초] --no-navigate")


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
        from scripts.browser.cdp_client import __doc__ as _cdp_client_doc

        print(_cdp_client_doc)
        return
    handler(task, sub, args)


def main() -> None:
    site_login_registry.install()
    if len(sys.argv) < 2:
        from scripts.browser.cdp_client import __doc__ as _cdp_client_doc

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

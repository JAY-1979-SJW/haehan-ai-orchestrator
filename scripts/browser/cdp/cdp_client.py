"""CDP 데몬 클라이언트 — 명령 전달.

용도:
  데몬의 브라우저 세션에 명령 전달

사용법:
  python scripts/browser/cdp/cli.py check-login          # 현재 열려있는 탭 로그인 상태 확인
  python scripts/browser/cdp/cli.py open <사이트> [경로] # 통합 접속 (A방식 자동로그인+B방식 fallback) ★권장
  python scripts/browser/cdp/cli.py explore <site> [path] [depth] [max] # 로그인+자동 사이트탐색 (sitemap 생성)
  python scripts/browser/cdp/cli.py crawl <site> [depth=3] [max=50] # 홈페이지부터 전체 크롤 + 미설계 페이지 자동 반영
  python scripts/browser/cdp/cli.py crawl-here [depth=2] [max=30]  # 현재 탭부터 BFS 탐색 (로그인 우회) ★수동 로그인 후
  python scripts/browser/cdp/cli.py snapshot                  # 현재 활성 탭 1회 분석 + 저장 (수동 탐색)
  python scripts/browser/cdp/cli.py visits [host]             # 저장된 수동 스냅샷 목록 + 타입 통계
  python scripts/browser/cdp/cli.py session save <host>       # 인증 세션 저장 (쿠키+storage 암호화)
  python scripts/browser/cdp/cli.py session load <host>       # 세션 복원
  python scripts/browser/cdp/cli.py user-watch [타임아웃초] [호스트]  # 사용자 수동 조작 실시간 감지 (URL변화/클릭/XHR/DOM)
  python scripts/browser/cdp/cli.py gabia login-watch [초]  # 가비아 로그인 실시간 감지 → 감지 즉시 DNS 관리 화면 이동
  python scripts/browser/cdp/cli.py auto-login <사이트>  # 감지기 전용 (사용자 수동 로그인 대기)
  python scripts/browser/cdp/cli.py login-watch [interval] [timeout] # 모든 탭 로그인 실시간 감지/저장
  python scripts/browser/cdp/cli.py naver login           # 네이버 로그인
  python scripts/browser/cdp/cli.py naver session-check   # 세션 확인
  python scripts/browser/cdp/cli.py naver blog write      # 블로그 작성
  python scripts/browser/cdp/cli.py google mail list      # Gmail 목록
  python scripts/browser/cdp/cli.py google calendar today # 오늘 일정
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

DAEMON_STATE_FILE = ROOT / "data" / "cdp_daemon_state.json"


# ── 명령별 핸들러 ─────────────────────────────────────────────────────────
# 2026-09-29 STD-08(복잡도) 리팩터: 원래 main() 하나(길이 670줄, C901=134)에 있던
# match cmd: 의 각 case 본문을 그대로 옮겼다. 로직·문자열·예외 처리는 한 글자도 바꾸지
# 않았고, 함수로 나눠 담기만 했다 — 아래 _dispatch()의 각 case 는 여기 함수를 호출만 한다.


def _cmd_check_login() -> None:
    from scripts.check_login_status import main as check_login_main

    check_login_main()


def _cmd_goto(task: str) -> None:
    from scripts.navigator import goto

    if not task:
        print("사용법: python scripts/browser/cdp/cli.py goto <별칭_or_URL>")
        return
    goto(task)


def _cmd_wait_login(task: str, sub: str) -> None:
    from scripts.navigator import wait_login

    if not task:
        print("사용법: python scripts/browser/cdp/cli.py wait-login <사이트> [타임아웃초]")
        return
    t_out = int(sub) if sub.isdigit() else 300
    ok = wait_login(task, timeout_s=t_out)
    sys.exit(0 if ok else 1)


def _cmd_save_session(task: str) -> None:
    from scripts.navigator import save_session

    save_session(task or None)


def _cmd_write_post(task: str, sub: str, args: list[str]) -> None:
    from scripts.navigator import write_blog_post

    if not task or not sub:
        print("사용법: python scripts/browser/cdp/cli.py write-post <제목> <본문> [이미지경로]")
        return
    img = args[0] if args else None
    ok = write_blog_post(task, sub, image_path=img)
    sys.exit(0 if ok else 1)


def _cmd_paste_image(task: str, sub: str) -> None:
    from scripts.navigator import paste_image

    if not task:
        print("사용법: python scripts/browser/cdp/cli.py paste-image <이미지경로> [target]")
        return
    tgt = sub if sub else "body"
    ok = paste_image(task, tgt)
    sys.exit(0 if ok else 1)


def _cmd_handle_draft_popup() -> None:
    from scripts.navigator import handle_draft_restore_popup

    r = handle_draft_restore_popup()
    mark = (
        "✓ 감지+취소"
        if r["detected"] and r["action"] == "cancel_clicked"
        else ("- 미감지" if not r["detected"] else "✗ 클릭 실패")
    )
    print(f"{mark} ({r['elapsed_ms']}ms)")
    sys.exit(0 if r["action"] != "cancel_failed" else 1)


def _cmd_is_ready(task: str, sub: str, args: list[str]) -> None:
    from scripts.navigator import is_ready

    check_args = [a for a in [task, sub] + args if a]  # noqa: RUF005
    if not check_args:
        print("사용법: python scripts/browser/cdp/cli.py is-ready <체크1> [체크2 ...]")
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
    from scripts.navigator import verify_input

    if not task:
        print("사용법: python scripts/browser/cdp/cli.py verify-input <텍스트>")
        return
    full = " ".join([task, sub] + args).strip()  # noqa: RUF005
    v = verify_input(full)
    mark = "✓" if v["found"] else "✗"
    print(f"{mark} found={v['found']} where={v['where']} ({v['elapsed_ms']}ms)")
    if v["found"]:
        print(f"  실제값: '{v['actual']}'")
    sys.exit(0 if v["found"] else 1)


def _cmd_verify_text(task: str, sub: str, args: list[str]) -> None:
    from scripts.navigator import verify_text

    if not task:
        print("사용법: python scripts/browser/cdp/cli.py verify-text <텍스트>")
        return
    full = " ".join([task, sub] + args).strip()  # noqa: RUF005
    results = verify_text(full)
    # 매칭 결과 있으면 0, 없으면 1
    found = any(r["data"]["occurrences_in_innerText"] > 0 for r in results)
    sys.exit(0 if found else 1)


def _cmd_scan_links() -> None:
    from scripts.navigator import scan_links

    scan_links()


def _cmd_scan_page() -> None:
    from scripts.navigator import scan_page

    scan_page()


def _cmd_type_into(task: str, sub: str, args: list[str]) -> None:
    from scripts.navigator import type_into

    if not task or not sub:
        print("사용법: python scripts/browser/cdp/cli.py type-into <대상> <텍스트>")
        return
    # 텍스트는 sub + args 전체를 공백 join
    full_text = " ".join([sub] + args)  # noqa: RUF005
    ok = type_into(task, full_text)
    sys.exit(0 if ok else 1)


def _cmd_click_button(task: str) -> None:
    from scripts.navigator import click_button

    if not task:
        print("사용법: python scripts/browser/cdp/cli.py click-button <텍스트>")
        return
    ok = click_button(task)
    sys.exit(0 if ok else 1)


def _cmd_click_link(task: str) -> None:
    from scripts.navigator import click_link

    if not task:
        print("사용법: python scripts/browser/cdp/cli.py click-link <텍스트>")
        return
    ok = click_link(task)
    sys.exit(0 if ok else 1)


def _cmd_popup_install() -> None:
    from scripts.popup_watcher import install_watcher

    r = install_watcher()
    print(f"✓ 팝업 감지 설치 완료 (프레임: {r['frame_count']}개)")


def _cmd_detect_popup() -> None:
    from scripts.popup_detector import detect_popup
    from scripts.web_connector import get_page

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
    from scripts.popup_detector import close_all_popups
    from scripts.web_connector import get_page

    page = get_page()
    result = close_all_popups(page)
    print(f"\n✓ 팝업 처리 완료: {result['total_closed']}개 닫음")
    if result["final_state"]["detected"]:
        print(f"⚠️  {result['final_state']['popup_count']}개 팝업 남아있음")
    sys.exit(0 if not result["final_state"]["detected"] else 1)


def _cmd_popup_poll() -> None:
    import json as _json

    from scripts.popup_watcher import poll_events

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
    from scripts.popup_watcher import auto_handle

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
    from scripts import popup_monitor as _pm

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

    from scripts import popup_monitor as _pm

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
        from scripts.popup_classifier import classify

        if not sub:
            print("사용법: popup-monitor classify <marker> [snippet]")
            return
        d = classify(marker=sub, snippet=" ".join(args))
        print(_json.dumps(d, ensure_ascii=False, indent=2))
    else:
        print("사용법: popup-monitor [start|status|list|ack|classify]")


def _cmd_chrome_ui_monitor(task: str, sub: str) -> None:
    import json as _json
    import subprocess
    from pathlib import Path as _Path

    from scripts.app_paths import repo_root

    STATE_FILE = repo_root() / "data" / "runtime" / "chrome_ui_monitor_state.json"
    sub_cmd = task or "status"

    if sub_cmd == "start":
        interval = float(sub) if sub else 3.0
        script = repo_root() / "scripts" / "archive" / "misc" / "chrome_ui_monitor.py"
        pythonw = _Path(__import__("sys").executable).parent / "pythonw.exe"
        if not pythonw.exists():
            pythonw = _Path(__import__("sys").executable)

        proc = subprocess.Popen(
            [str(pythonw), str(script), str(interval)],
            cwd=str(repo_root()),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            if __import__("sys").platform == "win32"
            else 0,
        )
        print(f"✓ chrome-ui-monitor 시작 (poll={interval}s, PID={proc.pid})")
    elif sub_cmd == "status":
        if STATE_FILE.exists():
            try:
                state = _json.loads(STATE_FILE.read_text(encoding="utf-8"))
                print(_json.dumps(state, ensure_ascii=False, indent=2))
            except Exception as e:  # noqa: BLE001 - CDP 브라우저 데몬 제어 CLI - 상태조회/모니터 시작중지/로그인 커맨드 래퍼, 예외시 오류 출력 후 sys.exit(1) 로 실패를 명확히 알림(fail-loud)
                print(f"✗ 상태 읽기 실패: {e}")
        else:
            print("☐ chrome-ui-monitor 미실행")
    elif sub_cmd == "stop":
        if STATE_FILE.exists():
            try:
                state = _json.loads(STATE_FILE.read_text(encoding="utf-8"))
                import os

                os.kill(int(state.get("pid", 0)), 15)
                print("✓ chrome-ui-monitor 중지 완료")
            except Exception as e:  # noqa: BLE001 - CDP 브라우저 데몬 제어 CLI - 상태조회/모니터 시작중지/로그인 커맨드 래퍼, 예외시 오류 출력 후 sys.exit(1) 로 실패를 명확히 알림(fail-loud)
                print(f"⚠ 종료 시도: {e}")
        else:
            print("☐ chrome-ui-monitor 실행 중이 아님")
    else:
        print("사용법: chrome-ui-monitor [start|status|stop]")


def _cmd_analyze() -> None:
    from scripts.page_analyzer import full_page_analysis
    from scripts.web_connector import get_page

    page = get_page()
    result = full_page_analysis(page, wait_for_load=True)
    print("\n[페이지 분석]")
    print(f"  완성도: {result.get('completeness', {}).get('completeness_score', '?')}%")
    print(f"  메뉴: {result.get('menu', {}).get('structure', {}).get('links_count', 0)}개")
    print(f"  테이블: {result.get('tables', {}).get('total_tables', 0)}개")
    if result.get("recommendations"):
        print(f"  권장사항: {', '.join(result['recommendations'])}")
    print("\n✓ 분석 결과:")
    print(json.dumps(result, ensure_ascii=False, indent=2)[:500])


def _cmd_crawl(task: str, sub: str, args: list[str]) -> None:
    # 홈페이지부터 전체 자동 크롤 + 미설계 페이지 자동 반영
    import os  # noqa: F401 - 원본 그대로 보존(2026-09-29 STD-08 리팩터, 로직 변경 없음)

    from scripts.explorer.site_crawler import crawl_site
    from scripts.site_access import LoginError, open_site
    from scripts.site_registry import list_sites
    from scripts.site_watch import StepFailure

    if not task:
        print("사용법: python scripts/browser/cdp/cli.py crawl <사이트> [depth=3] [max=50]")
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


def _cmd_explore(task: str, sub: str, args: list[str]) -> None:
    # 로그인 후 자동 사이트 탐색
    import os

    from scripts.site_access import LoginError, explore_after_login
    from scripts.site_registry import list_sites
    from scripts.site_watch import StepFailure

    if not task:
        print("사용법: python scripts/browser/cdp/cli.py explore <사이트> [경로] [depth] [max] [--dry-run]")
        print(f"  지원: {list_sites()}")
        return
    args_all = ([sub] if sub else []) + list(args)
    if "--dry-run" in args_all:
        os.environ["SITE_DRY_RUN"] = "1"
        args_all.remove("--dry-run")
    path = args_all[0] if args_all else ""
    depth = int(args_all[1]) if len(args_all) > 1 else 2
    max_pages = int(args_all[2]) if len(args_all) > 2 else 20
    print(f"\n[작업] {task} 로그인 + 자동 사이트 탐색 (depth={depth}, max={max_pages})")
    try:
        r = explore_after_login(task, path, depth=depth, max_pages=max_pages)
        print("\n✓ 탐색 완료")
        print(f"  방문: {r['explore']['visited']} 페이지")
        print(f"  경과: {r['explore']['elapsed_s']}초")
        if r["explore"].get("saved_to"):
            print(f"  저장: {r['explore']['saved_to']}")
        if r["explore"].get("aborted_reason"):
            print(f"  중단: {r['explore']['aborted_reason']}")
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
    from scripts.explorer.site_crawler import crawl_site
    from scripts.web_connector import get_page

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


def _cmd_session(task: str, sub: str) -> None:
    # 인증 세션 저장/복원/관리
    from scripts.auth_session import cli_delete, cli_list, cli_load, cli_save

    sub_cmd = task or "list"
    host = sub or ""
    if sub_cmd == "save":
        if not host:
            print("사용법: session save <host>  예) session save eum.cw.or.kr")
            return
        cli_save(host)
    elif sub_cmd == "load":
        if not host:
            print("사용법: session load <host>")
            return
        cli_load(host)
    elif sub_cmd == "list":
        cli_list()
    elif sub_cmd == "delete":
        if not host:
            print("사용법: session delete <host>")
            return
        cli_delete(host)
    else:
        print(f"알 수 없는 session 명령: {sub_cmd}")


def _print_open_site_result(res: dict[str, Any] | Any, *, dry: bool) -> None:
    if isinstance(res, dict):
        if dry:
            print(
                f"\n✓ [DRY] 흐름 검증 완료 — site={res.get('site')} url={res.get('url')} logged_in={res.get('logged_in')}"
            )
        else:
            print(f"\n✓ 접속 완료 — {res.get('url')}")
    else:
        print(f"\n✓ 접속 완료 — {res.url}")


def _cmd_open(task: str, sub: str, args: list[str]) -> None:
    # 통합 사이트 접속 (A방식 + B방식 fallback + 전 단계 감시)
    import os

    from scripts.site_access import LoginError, open_site
    from scripts.site_registry import list_sites
    from scripts.site_watch import StepFailure

    if not task:
        print("사용법: python scripts/browser/cdp/cli.py open <사이트> [경로] [--dry-run] [--force-login]")
        print(f"  지원: {list_sites()}")
        return
    # --dry-run 플래그 해석
    args_all = [sub] + list(args) if sub else list(args)  # noqa: RUF005
    if "--dry-run" in args_all:
        os.environ["SITE_DRY_RUN"] = "1"
        args_all.remove("--dry-run")
    force_login = False
    if "--force-login" in args_all:
        force_login = True
        args_all.remove("--force-login")
    path = args_all[0] if args_all else ""
    dry = os.environ.get("SITE_DRY_RUN", "") == "1"
    flags = []
    if dry:
        flags.append("DRY-RUN")
    if force_login:
        flags.append("FORCE-LOGIN")
    suffix = f" [{' '.join(flags)}]" if flags else ""
    print(f"\n[작업] {task} 사이트 접속 — 전 단계 감시 (A→B fallback){suffix}")
    try:
        res = open_site(task, path, force_login=force_login)
        _print_open_site_result(res, dry=dry)
    except StepFailure as e:
        print(f"\n✘ 단계 실패: {e.step} ({e.kind})")
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


def _cmd_user_watch(task: str, sub: str) -> None:
    from scripts.user_action_monitor import watch_user_actions

    timeout_s = int(task) if task and task.isdigit() else 0
    host_filter = sub if sub else None
    watch_user_actions(timeout_s=timeout_s, host_filter=host_filter)


def _cmd_gabia(task: str, sub: str, args: list[str]) -> None:
    # NOTE(2026-09-29 STD-08 리팩터 중 발견, 이번엔 그대로 보존): cli.py 의 _SITE_ROUTER_CMDS
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
            print("  python scripts/browser/cdp/cli.py gabia login-watch [타임아웃초]")
            print("  python scripts/browser/cdp/cli.py gabia login-watch [타임아웃초] --no-navigate")


def _cmd_auto_login(task: str, sub: str) -> None:
    from scripts.login_detector import monitor_for_login
    from scripts.web_connector import get_page

    if not task:
        print("사용법: python scripts/browser/cdp/cli.py auto-login <사이트> [URL]")
        return
    url = sub if sub else None
    print(f"\n[작업] {task} 자동 로그인 + 세션 저장")
    print("⏳ 자동 로그인 탐지 중... (1초 간격, 최대 300초)")
    print("   → 브라우저에서 로그인을 진행하세요 (즉시 감지됨)")
    try:
        page = get_page()
        if url:
            page.goto(url, timeout=30000)
        # 1초 간격으로 더 빠르게 감지
        result = monitor_for_login(page, check_interval=1, timeout_s=300)
        if result.get("detected"):
            site = result.get("site") or task
            elapsed = result.get("elapsed_s", 0)
            print(f"\n✓ {site} 로그인 자동 감지됨 ({elapsed}초)")
            print("✓ 세션 자동 저장 완료")
        else:
            print("\n✗ 로그인 감지 타임아웃 (300초 경과)")
            sys.exit(1)
    except Exception as e:  # noqa: BLE001 - CDP 브라우저 데몬 제어 CLI - 상태조회/모니터 시작중지/로그인 커맨드 래퍼, 예외시 오류 출력 후 sys.exit(1) 로 실패를 명확히 알림(fail-loud)
        print(f"  [오류] {e}")
        import traceback

        traceback.print_exc()


def _cmd_login_watch(task: str, sub: str) -> None:
    import json as _json

    from scripts.login_detector import watch_all_logins

    interval = float(task) if task else 1.0
    timeout_s = int(sub) if sub and sub.isdigit() else 0
    result = watch_all_logins(check_interval=interval, timeout_s=timeout_s)
    print(_json.dumps(result, ensure_ascii=False, indent=2))


def _cmd_cred(task: str, sub: str) -> None:
    from scripts.credentials import _cmd_delete, _cmd_get, _cmd_list, _cmd_set

    sub_cmd = task or "list"
    site = sub or ""
    if sub_cmd == "set":
        _cmd_set(site) if site else print("사용법: cred set <사이트>  예) cred set eum")
    elif sub_cmd == "get":
        _cmd_get(site) if site else print("사용법: cred get <사이트>")
    elif sub_cmd == "list":
        _cmd_list()
    elif sub_cmd == "delete":
        _cmd_delete(site) if site else print("사용법: cred delete <사이트>")
    else:
        print("사용법: cred [set|get|list|delete] [사이트]")


def _cmd_gate(task: str, sub: str) -> None:
    from scripts.gate import GateBlocked, check, list_registry

    sub_cmd = task or "list"
    if sub_cmd == "list":
        rows = list_registry()
        print(f"{'작업명':<32} {'등급'}")
        for r in rows:
            icon = {"auto": "✓", "notify": "⚠", "approve": "🔒", "block": "✗"}.get(r["risk"], "?")
            print(f"{r['op_name']:<32} {icon} {r['risk']}")
    elif sub_cmd == "check":
        if not sub:
            print("사용법: gate check <op_name>")
            return
        try:
            result = check(sub, force=True)
            print(f"✓ {sub}: {result.risk.value} → {result.verdict.value}")
        except GateBlocked as e:
            print(f"✗ {e}")
    else:
        print("사용법: gate [list|check <op_name>]")


def _cmd_op_log(task: str, sub: str) -> None:
    from scripts.op_log import query_recent, query_stats

    sub_cmd = task or "list"
    if sub_cmd == "list":
        op_filter = sub or None
        rows = query_recent(op_name=op_filter, limit=50)
        if not rows:
            print("☐ 기록된 작업 없음")
        for r in rows:
            dur = f"[{r['duration_ms']}ms]" if r.get("duration_ms") else ""
            st = "✓" if r["status"] == "ok" else ("…" if r["status"] == "start" else "✗")
            print(f"{st} {r['ts'][:19]}  {r['op_name']:<24} {dur:<10} {(r.get('message') or '')[:60]}")
    elif sub_cmd == "tail":
        rows = query_recent(limit=20)
        for r in reversed(rows):
            dur = f"[{r['duration_ms']}ms]" if r.get("duration_ms") else ""
            st = "✓" if r["status"] == "ok" else ("…" if r["status"] == "start" else "✗")
            print(f"{st} {r['ts'][:19]}  {r['op_name']:<24} {dur:<10} {(r.get('message') or '')[:60]}")
    elif sub_cmd == "stats":
        hours = int(sub) if sub and sub.isdigit() else 24
        rows = query_stats(hours=hours)
        print(f"최근 {hours}시간 작업 통계:")
        print(f"{'작업명':<28} {'총':<6} {'성공':<6} {'실패':<6} {'평균ms'}")
        for r in rows:
            print(f"{r['op_name']:<28} {r['total']:<6} {r['ok']:<6} {r['fail']:<6} {r['avg_ms'] or '-'}")
    else:
        print("사용법: op-log [list|tail|stats] [op_name] [hours]")


# CLI 디스패치(_HANDLERS·_dispatch·main)와 직접 실행 진입점은 scripts/browser/cdp/cli.py
# 로 분리했다(cdp_client 는 라이브러리라 scripts.router 를 몰라야 한다 — 2026-10-07 STD-08
# 후속). 직접 실행하려면 `python scripts/browser/cdp/cli.py ...` 를 쓴다.

"""CDP 데몬 클라이언트 — 명령 전달.

용도:
  데몬의 브라우저 세션에 명령 전달

사용법:
  python scripts/entry/cdp_cli.py check-login          # 현재 열려있는 탭 로그인 상태 확인
  python scripts/entry/cdp_cli.py open <사이트> [경로] # 통합 접속 (A방식 자동로그인+B방식 fallback) ★권장
  python scripts/entry/cdp_cli.py explore <site> [path] [depth] [max] # 로그인+자동 사이트탐색 (sitemap 생성)
  python scripts/entry/cdp_cli.py crawl <site> [depth=3] [max=50] # 홈페이지부터 전체 크롤 + 미설계 페이지 자동 반영
  python scripts/entry/cdp_cli.py crawl-here [depth=2] [max=30]  # 현재 탭부터 BFS 탐색 (로그인 우회) ★수동 로그인 후
  python scripts/entry/cdp_cli.py snapshot                  # 현재 활성 탭 1회 분석 + 저장 (수동 탐색)
  python scripts/entry/cdp_cli.py visits [host]             # 저장된 수동 스냅샷 목록 + 타입 통계
  python scripts/entry/cdp_cli.py session save <host>       # 인증 세션 저장 (쿠키+storage 암호화)
  python scripts/entry/cdp_cli.py session load <host>       # 세션 복원
  python scripts/entry/cdp_cli.py user-watch [타임아웃초] [호스트]  # 사용자 수동 조작 실시간 감지 (URL변화/클릭/XHR/DOM)
  python scripts/entry/cdp_cli.py gabia login-watch [초]  # 가비아 로그인 실시간 감지 → 감지 즉시 DNS 관리 화면 이동
  python scripts/entry/cdp_cli.py auto-login <사이트>  # 감지기 전용 (사용자 수동 로그인 대기)
  python scripts/entry/cdp_cli.py login-watch [interval] [timeout] # 모든 탭 로그인 실시간 감지/저장
  python scripts/entry/cdp_cli.py naver login           # 네이버 로그인
  python scripts/entry/cdp_cli.py naver session-check   # 세션 확인
  python scripts/entry/cdp_cli.py naver blog write      # 블로그 작성
  python scripts/entry/cdp_cli.py google mail list      # Gmail 목록
  python scripts/entry/cdp_cli.py google calendar today # 오늘 일정

명령 핸들러 중 navigator·popup·explorer·gabia(상위 도메인 도구)를 쓰는 것들은
scripts/entry/cdp_cli.py 로 옮겼다(S1-c, 2026-10-07) — 이 파일은 연결(connection.py)·
scripts 최상위 공용 유틸(gate·op_log·credentials·site_access 등)만 쓰는 핸들러만
남는다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

DAEMON_STATE_FILE = ROOT / "data" / "cdp_daemon_state.json"


def _cmd_check_login() -> None:
    from scripts.auth.check_login_status import main as check_login_main

    check_login_main()


def _cmd_chrome_ui_monitor(task: str, sub: str) -> None:
    import json as _json
    import subprocess
    from pathlib import Path as _Path

    from scripts.common.app_paths import repo_root

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
    from scripts.browser.cdp.connection import get_page
    from scripts.browser.page.page_analyzer import full_page_analysis

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


def _cmd_explore(task: str, sub: str, args: list[str]) -> None:
    # 로그인 후 자동 사이트 탐색
    import os

    from scripts.explorer.explore_after_login import explore_after_login
    from scripts.site_engine.site_access import LoginError
    from scripts.site_engine.site_registry import list_sites
    from scripts.site_engine.site_watch import StepFailure

    if not task:
        print("사용법: python scripts/entry/cdp_cli.py explore <사이트> [경로] [depth] [max] [--dry-run]")
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


def _cmd_session(task: str, sub: str) -> None:
    # 인증 세션 저장/복원/관리
    from scripts.auth.auth_session import cli_delete, cli_list, cli_load, cli_save

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

    from scripts.site_engine.site_access import LoginError, open_site
    from scripts.site_engine.site_registry import list_sites
    from scripts.site_engine.site_watch import StepFailure

    if not task:
        print("사용법: python scripts/entry/cdp_cli.py open <사이트> [경로] [--dry-run] [--force-login]")
        print(f"  지원: {list_sites()}")
        return
    # --dry-run 플래그 해석
    args_all = [sub, *args] if sub else list(args)
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
    from scripts.browser.page.user_action_monitor import watch_user_actions

    timeout_s = int(task) if task and task.isdigit() else 0
    host_filter = sub if sub else None
    watch_user_actions(timeout_s=timeout_s, host_filter=host_filter)


def _cmd_auto_login(task: str, sub: str) -> None:
    from scripts.auth.login_detector import monitor_for_login
    from scripts.browser.cdp.connection import get_page

    if not task:
        print("사용법: python scripts/entry/cdp_cli.py auto-login <사이트> [URL]")
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

    from scripts.auth.login_detector import watch_all_logins

    interval = float(task) if task else 1.0
    timeout_s = int(sub) if sub and sub.isdigit() else 0
    result = watch_all_logins(check_interval=interval, timeout_s=timeout_s)
    print(_json.dumps(result, ensure_ascii=False, indent=2))


def _cmd_cred(task: str, sub: str) -> None:
    from scripts.auth.credentials import _cmd_delete, _cmd_get, _cmd_list, _cmd_set

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
    from scripts.common.gate import GateBlocked, check, list_registry

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
    from scripts.common.op_log import query_recent, query_stats

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


# CLI 디스패치(_HANDLERS·_dispatch·main)와 직접 실행 진입점, navigator·popup·explorer·
# gabia 를 쓰는 핸들러는 scripts/entry/cdp_cli.py 로 분리했다(cdp_client 는 라이브러리라
# scripts.site_engine.command_router 와 상위 도메인 도구를 몰라야 한다 — 2026-10-07 STD-08 후속, S1-c).
# 직접 실행하려면 `python scripts/entry/cdp_cli.py ...` 를 쓴다.

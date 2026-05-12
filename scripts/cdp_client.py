"""CDP 데몬 클라이언트 — 명령 전달.

용도:
  데몬의 브라우저 세션에 명령 전달

사용법:
  python scripts/cdp_client.py check-login          # 현재 열려있는 탭 로그인 상태 확인
  python scripts/cdp_client.py auto-login <사이트>  # 자동 로그인 + 세션 저장
  python scripts/cdp_client.py naver login           # 네이버 로그인
  python scripts/cdp_client.py naver session-check   # 세션 확인
  python scripts/cdp_client.py naver blog write      # 블로그 작성
  python scripts/cdp_client.py google mail list      # Gmail 목록
  python scripts/cdp_client.py google calendar today # 오늘 일정
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DAEMON_STATE_FILE = ROOT / "data" / "cdp_daemon_state.json"


def _load_daemon_state() -> dict:
    if not DAEMON_STATE_FILE.exists():
        raise RuntimeError("데몬이 실행 중이지 않습니다. 먼저 'python scripts/cdp_daemon.py start' 실행하세요")
    try:
        return json.loads(DAEMON_STATE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        raise RuntimeError(f"상태 파일 읽기 실패: {e}")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]
    task = sys.argv[2] if len(sys.argv) > 2 else ""
    sub  = sys.argv[3] if len(sys.argv) > 3 else ""
    args = sys.argv[4:] if len(sys.argv) > 4 else []

    try:
        match cmd:
            case "check-login":
                from scripts.check_login_status import main as check_login_main
                check_login_main()
            case "goto":
                from scripts.navigator import goto
                if not task:
                    print("사용법: python scripts/cdp_client.py goto <별칭_or_URL>")
                    return
                goto(task)
            case "wait-login":
                from scripts.navigator import wait_login
                if not task:
                    print("사용법: python scripts/cdp_client.py wait-login <사이트> [타임아웃초]")
                    return
                t_out = int(sub) if sub.isdigit() else 300
                ok = wait_login(task, timeout_s=t_out)
                sys.exit(0 if ok else 1)
            case "save-session":
                from scripts.navigator import save_session
                save_session(task or None)
            case "write-post":
                from scripts.navigator import write_blog_post
                if not task or not sub:
                    print("사용법: python scripts/cdp_client.py write-post <제목> <본문> [이미지경로]")
                    return
                img = args[0] if args else None
                ok = write_blog_post(task, sub, image_path=img)
                sys.exit(0 if ok else 1)
            case "paste-image":
                from scripts.navigator import paste_image
                if not task:
                    print("사용법: python scripts/cdp_client.py paste-image <이미지경로> [target]")
                    return
                tgt = sub if sub else "body"
                ok = paste_image(task, tgt)
                sys.exit(0 if ok else 1)
            case "handle-draft-popup":
                from scripts.navigator import handle_draft_restore_popup
                r = handle_draft_restore_popup()
                mark = "✓ 감지+취소" if r["detected"] and r["action"] == "cancel_clicked" else ("- 미감지" if not r["detected"] else "✗ 클릭 실패")
                print(f"{mark} ({r['elapsed_ms']}ms)")
                sys.exit(0 if r["action"] != "cancel_failed" else 1)
            case "is-ready":
                from scripts.navigator import is_ready
                check_args = [a for a in [task, sub] + args if a]
                if not check_args:
                    print("사용법: python scripts/cdp_client.py is-ready <체크1> [체크2 ...]")
                    print("  예: is-ready url_contains:naver readystate has_button:발행")
                    return
                r = is_ready(check_args, timeout_s=2.0)
                mark = "✓" if r["ok"] else "✗"
                print(f"{mark} ok={r['ok']} elapsed={r['elapsed_ms']}ms")
                for item in r["results"]:
                    pmk = "✓" if item["passed"] else "✗"
                    print(f"  {pmk} {item['check']:<40} {item['reason']}")
                sys.exit(0 if r["ok"] else 1)
            case "verify-input":
                from scripts.navigator import verify_input
                if not task:
                    print("사용법: python scripts/cdp_client.py verify-input <텍스트>")
                    return
                full = " ".join([task, sub] + args).strip()
                v = verify_input(full)
                mark = "✓" if v["found"] else "✗"
                print(f"{mark} found={v['found']} where={v['where']} ({v['elapsed_ms']}ms)")
                if v["found"]:
                    print(f"  실제값: '{v['actual']}'")
                sys.exit(0 if v["found"] else 1)
            case "verify-text":
                from scripts.navigator import verify_text
                if not task:
                    print("사용법: python scripts/cdp_client.py verify-text <텍스트>")
                    return
                full = " ".join([task, sub] + args).strip()
                results = verify_text(full)
                # 매칭 결과 있으면 0, 없으면 1
                found = any(r["data"]["occurrences_in_innerText"] > 0 for r in results)
                sys.exit(0 if found else 1)
            case "scan-links":
                from scripts.navigator import scan_links
                scan_links()
            case "scan-page":
                from scripts.navigator import scan_page
                scan_page()
            case "type-into":
                from scripts.navigator import type_into
                if not task or not sub:
                    print("사용법: python scripts/cdp_client.py type-into <대상> <텍스트>")
                    return
                # 텍스트는 sub + args 전체를 공백 join
                full_text = " ".join([sub] + args)
                ok = type_into(task, full_text)
                sys.exit(0 if ok else 1)
            case "click-button":
                from scripts.navigator import click_button
                if not task:
                    print("사용법: python scripts/cdp_client.py click-button <텍스트>")
                    return
                ok = click_button(task)
                sys.exit(0 if ok else 1)
            case "click-link":
                from scripts.navigator import click_link
                if not task:
                    print("사용법: python scripts/cdp_client.py click-link <텍스트>")
                    return
                ok = click_link(task)
                sys.exit(0 if ok else 1)
            case "popup-install":
                from scripts.popup_watcher import install_watcher
                r = install_watcher()
                print(f"✓ 팝업 감지 설치 완료 (프레임: {r['frame_count']}개)")
            case "detect-popup":
                from scripts.popup_detector import detect_popup
                from scripts.web_connector import get_page
                page = get_page()
                result = detect_popup(page)
                if result["detected"]:
                    print(f"\n✓ {result['popup_count']}개 팝업 감지됨")
                    print(f"  유형: {', '.join(result['types'])}")
                    for i, elem in enumerate(result["elements"]):
                        print(f"  - [{i+1}] {elem.get('text', '')[:50]}")
                else:
                    print("\n✓ 팝업 없음")
                sys.exit(0 if result["detected"] else 1)
            case "close-popup":
                from scripts.popup_detector import close_all_popups
                from scripts.web_connector import get_page
                page = get_page()
                result = close_all_popups(page)
                print(f"\n✓ 팝업 처리 완료: {result['total_closed']}개 닫음")
                if result["final_state"]["detected"]:
                    print(f"⚠️  {result['final_state']['popup_count']}개 팝업 남아있음")
                sys.exit(0 if not result["final_state"]["detected"] else 1)
            case "popup-poll":
                from scripts.popup_watcher import poll_events
                import json as _json
                events = poll_events()
                if not events:
                    print("☐ 팝업 이벤트 없음")
                else:
                    print(f"✓ 팝업 {len(events)}개 감지:")
                    for ev in events:
                        print(f"  - {ev['marker']} ({ev['frame_url']})")
                        print(f"    스니펫: {ev['snippet'][:100]}")
                print(_json.dumps(events, ensure_ascii=False, indent=2))
            case "popup-auto":
                from scripts.popup_watcher import auto_handle
                r = auto_handle()
                print(f"✓ 자동 처리 완료")
                print(f"  처리됨: {len(r['handled'])}개")
                print(f"  스킵: {len(r['skipped'])}개")
                print(f"  미지의: {len(r['unknown'])}개")
                if r["unknown"]:
                    for u in r["unknown"]:
                        print(f"    - {u['marker']}")
            case "popup-monitor":
                import json as _json
                from scripts import popup_monitor as _pm
                sub_cmd = task or "status"
                if sub_cmd == "start":
                    interval = float(sub) if sub else 2.0
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
                elif sub_cmd == "status":
                    st = _pm.status()
                    print(_json.dumps(st, ensure_ascii=False, indent=2))
                elif sub_cmd == "list":
                    rows = _pm.list_pending(limit=50)
                    if not rows:
                        print("☐ pending 이벤트 없음")
                    for r in rows:
                        print(f"[{r['id']:>4}] {r['severity']:<8} {r['category']:<22} "
                              f"action={r['action']:<14} target={r['target']!s:<8} "
                              f"marker={r['marker'][:40]}")
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
            case "chrome-ui":
                import json as _json
                from scripts import chrome_ui_watcher as _cuw
                sub_cmd = task or "scan"
                if sub_cmd == "scan":
                    pairs = _cuw.scan_all()
                    if not pairs:
                        print("☐ 데몬 Chrome 윈도우 없음")
                    for window, events in pairs:
                        print(f"\n[Window] {(window.Name or '')[:80]}")
                        if not events:
                            print("  ☐ 알려진 chrome UI 알림 없음")
                        for ev in events:
                            print(f"  ★ {ev['marker']} → 권장버튼={ev['button_name']!r}")
                            print(f"    snippet: {ev['snippet'][:100]}")
                elif sub_cmd == "status":
                    from scripts.popup_monitor import chrome_ui_status
                    print(_json.dumps(chrome_ui_status(), ensure_ascii=False, indent=2))
                elif sub_cmd == "dismiss":
                    # chrome-ui dismiss <button_name>
                    if not sub:
                        print("사용법: chrome-ui dismiss <버튼 이름>")
                        return
                    btn = " ".join([sub] + args)
                    success = 0
                    for window in _cuw.find_chrome_windows():
                        if _cuw.click_button_in_window(window, btn):
                            success += 1
                    print(f"✓ {success}개 윈도우에서 '{btn}' 클릭됨" if success else f"✗ '{btn}' 못 찾음")
                else:
                    print("사용법: chrome-ui [scan|status|dismiss]")
            case "analyze":
                from scripts.page_analyzer import full_page_analysis
                from scripts.web_connector import get_page
                import json
                page = get_page()
                result = full_page_analysis(page, wait_for_load=True)
                print("\n[페이지 분석]")
                print(f"  완성도: {result.get('completeness', {}).get('completeness_score', '?')}%")
                print(f"  메뉴: {result.get('menu', {}).get('structure', {}).get('links_count', 0)}개")
                print(f"  테이블: {result.get('tables', {}).get('total_tables', 0)}개")
                if result.get('recommendations'):
                    print(f"  권장사항: {', '.join(result['recommendations'])}")
                print(f"\n✓ 분석 결과:")
                print(json.dumps(result, ensure_ascii=False, indent=2)[:500])
            case "explore":
                from scripts.explorer import run as run_explore
                run_explore(task, [sub] + args if sub else args)
            case "naver":
                from scripts.naver.router import run_naver
                run_naver(task, sub, args)
            case "google" | "gmail":
                from scripts.google.router import run_google
                run_google(cmd, task, sub, args)
            case "kakao":
                from scripts.kakao.router import run_kakao
                run_kakao(task, sub, args)
            case "auto-login":
                from scripts.login_detector import monitor_for_login
                from scripts.web_connector import get_page
                if not task:
                    print("사용법: python scripts/cdp_client.py auto-login <사이트> [URL]")
                    return
                url = sub if sub else None
                print(f"\n[작업] {task} 자동 로그인 + 세션 저장")
                print(f"⏳ 자동 로그인 탐지 중... (1초 간격, 최대 300초)")
                print(f"   → 브라우저에서 로그인을 진행하세요 (즉시 감지됨)")
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
                        print(f"✓ 세션 자동 저장 완료")
                    else:
                        print(f"\n✗ 로그인 감지 타임아웃 (300초 경과)")
                        sys.exit(1)
                except Exception as e:
                    print(f"  [오류] {e}")
                    import traceback
                    traceback.print_exc()
            case "gate":
                from scripts.gate import check, list_registry, GateBlocked
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
            case "op-log":
                import json as _json
                from scripts.op_log import query_recent, query_stats
                sub_cmd = task or "list"
                if sub_cmd == "list":
                    op_filter = sub or None
                    rows = query_recent(op_name=op_filter, limit=50)
                    if not rows:
                        print("☐ 기록된 작업 없음")
                    for r in rows:
                        dur = f"[{r['duration_ms']}ms]" if r.get('duration_ms') else ""
                        st = "✓" if r["status"] == "ok" else ("…" if r["status"] == "start" else "✗")
                        print(f"{st} {r['ts'][:19]}  {r['op_name']:<24} {dur:<10} {(r.get('message') or '')[:60]}")
                elif sub_cmd == "tail":
                    rows = query_recent(limit=20)
                    for r in reversed(rows):
                        dur = f"[{r['duration_ms']}ms]" if r.get('duration_ms') else ""
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
            case _:
                print(f"알 수 없는 명령: {cmd}")
                print(__doc__)
    except Exception as e:
        print(f"  [오류] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

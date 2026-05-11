"""CDP 데몬 클라이언트 — 명령 전달.

용도:
  데몬의 브라우저 세션에 명령 전달

사용법:
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
            case _:
                print(f"알 수 없는 명령: {cmd}")
                print(__doc__)
    except Exception as e:
        print(f"  [오류] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

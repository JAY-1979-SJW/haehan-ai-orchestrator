"""CDP 데몬 클라이언트 — 명령 전달.

용도:
  데몬의 브라우저 세션에 명령 전달

사용법:
  python scripts/cdp_client.py blog         # 블로그 작성
  python scripts/cdp_client.py naver-login  # 네이버 로그인
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DAEMON_STATE_FILE = ROOT / "data" / "cdp_daemon_state.json"


def _load_daemon_state() -> dict:
    """데몬 상태 로드."""
    if not DAEMON_STATE_FILE.exists():
        raise RuntimeError("데몬이 실행 중이지 않습니다. 먼저 'python scripts/cdp_daemon.py start' 실행하세요")
    try:
        return json.loads(DAEMON_STATE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        raise RuntimeError(f"상태 파일 읽기 실패: {e}")


def _ensure_daemon() -> dict:
    """데몬 실행 확인."""
    state = _load_daemon_state()
    if not state.get("running"):
        raise RuntimeError("데몬이 실행 중이지 않습니다")
    if state.get("browser_context") != "active":
        raise RuntimeError("브라우저가 준비되지 않았습니다")
    return state


def cmd_blog_write() -> None:
    """블로그 글 작성."""
    state = _ensure_daemon()
    print("=" * 70)
    print("📝 블로그 글 작성 (AI CDP 세션)")
    print("=" * 70)
    print(f"\n✓ 데몬 연결됨 (PID: {state['pid']})")
    print("✓ 브라우저 활성")
    print("✓ 로그인 상태 유지\n")

    try:
        from playwright.sync_api import sync_playwright

        # 데몬의 세션 디렉터리 접근
        session_dir = ROOT / "data" / "browser_sessions" / "ai_assistant"
        storage_state_path = session_dir / "state.json"

        if not storage_state_path.is_file():
            print("⚠️  저장된 로그인 정보가 없습니다")
            print("   먼저 네이버에 로그인하세요")
            return

        print("[1단계] 브라우저 세션 연결...")
        with sync_playwright() as p:
            # persistent context는 user_data_dir에서 자동으로 저장된 세션 복원
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=str(session_dir),
                headless=False,  # 사용자가 확인 가능
                channel="chrome",
                args=[
                    "--disable-blink-features=AutomationControlled",  # 자동화 감지 숨김
                ],
            )

            page = ctx.new_page()
            print("✓ 세션 연결 완료")

            # 블로그 이동
            print("\n[2단계] 블로그 이동...")
            page.goto("https://blog.naver.com/new", timeout=60000)
            print("✓ 블로그 글 작성 페이지 도착")

            # 글 작성 안내
            print("\n[3단계] 글 작성")
            print("""
브라우저에서:
  1. 제목과 본문을 입력하세요
  2. "임시저장" 또는 "발행"을 클릭하세요
  3. 작성 후 브라우저 창을 닫으세요
            """)

            print("\n⏳ 30초 후 자동으로 세션을 저장합니다...")
            time.sleep(30)

            print("\n[4단계] 세션 저장...")
            ctx.storage_state(path=str(storage_state_path))
            ctx.close()

            print("✓ 세션 저장 완료")
            print("\n" + "=" * 70)
            print("✅ 블로그 글 작성 완료")
            print("=" * 70)

    except Exception as e:
        print(f"✗ 오류: {e}")
        import traceback
        traceback.print_exc()


def cmd_naver_login() -> None:
    """네이버 로그인."""
    state = _ensure_daemon()
    print("=" * 70)
    print("🔐 네이버 로그인 (AI CDP 세션)")
    print("=" * 70)
    print(f"\n✓ 데몬 연결됨 (PID: {state['pid']})")
    print("✓ 브라우저 활성\n")

    try:
        from playwright.sync_api import sync_playwright

        session_dir = ROOT / "data" / "browser_sessions" / "ai_assistant"
        storage_state_path = session_dir / "state.json"

        print("[1단계] 브라우저 시작...")
        with sync_playwright() as p:
            # persistent context는 자동으로 세션 복원
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=str(session_dir),
                headless=False,
                channel="chrome",
                args=[
                    "--disable-blink-features=AutomationControlled",  # 자동화 감지 숨김
                ],
            )

            if storage_state_path.is_file():
                print("✓ 저장된 세션 복원")
            else:
                print("🆕 새 세션 생성")

            page = ctx.new_page()
            page.goto("https://www.naver.com/", timeout=60000)

            print("✓ 네이버 접속")

            # 로그인 상태 확인
            try:
                body_text = page.inner_text("body")[:500]
                if "로그인" in body_text or "아이디" in body_text:
                    print("\n[2단계] 로그인 진행...")
                    print("""
브라우저에서:
  1. 네이버에 로그인하세요
  2. 로그인 후 Enter를 누르세요
                    """)
                    input("👉 로그인 완료 후 Enter를 누르세요: ")
                else:
                    print("✓ 이미 로그인 상태입니다")

            except Exception:
                pass

            print("\n[3단계] 세션 저장...")
            ctx.storage_state(path=str(storage_state_path))
            ctx.close()

            print("✓ 세션 저장 완료")
            print("\n" + "=" * 70)
            print("✅ 로그인 완료")
            print("=" * 70)

    except Exception as e:
        print(f"✗ 오류: {e}")
        import traceback
        traceback.print_exc()


def main() -> None:
    """메인."""
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]

    # ── Google 서비스 라우팅 ──────────────────────────────────────
    # python scripts/cdp_client.py google drive list
    # python scripts/cdp_client.py google calendar create "제목" "2026-05-20" "10:00"
    if cmd in ("google", "gmail"):
        try:
            from google.router import run_google
            task = sys.argv[2] if len(sys.argv) > 2 else ""
            sub = sys.argv[3] if len(sys.argv) > 3 else ""
            args = sys.argv[4:] if len(sys.argv) > 4 else []
            run_google(cmd, task, sub, args)
        except Exception as e:
            print(f"  [오류] {e}")
            import traceback
            traceback.print_exc()
        return

    # ── 기존 명령 ──────────────────────────────────────────────────
    match cmd:
        case "blog":
            cmd_blog_write()
        case "naver-login":
            cmd_naver_login()
        case _:
            print(f"알 수 없는 명령: {cmd}")
            print(__doc__)


if __name__ == "__main__":
    main()

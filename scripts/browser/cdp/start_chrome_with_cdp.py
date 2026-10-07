"""Chrome 원격 디버깅 모드 시작 스크립트.

사용법
======
  python scripts/browser/cdp/start_chrome_with_cdp.py
  python scripts/browser/cdp/start_chrome_with_cdp.py --port 9222
  python scripts/browser/cdp/start_chrome_with_cdp.py --port 9222 --url https://www.gov.kr

이 스크립트는 Chrome을 --remote-debugging-port 플래그로 실행한다.
이미 실행 중이면 알림 후 종료한다.

AI 브라우저 자동화를 사용하려면 Chrome이 CDP 모드로 실행 중이어야 한다.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from scripts.browser.agent.cdp import (  # noqa: E402
    DEFAULT_CDP_PORT,
    get_chrome_start_command,
    is_cdp_available,
)
from scripts.browser.session.browser_paths import find_chrome  # noqa: E402
from scripts.browser.session.browser_sandbox_gate import assert_browser_launch_allowed  # noqa: E402


def _find_chrome_exe() -> str | None:
    return find_chrome()


def main() -> None:
    parser = argparse.ArgumentParser(description="CDP 모드 Chrome 시작")
    parser.add_argument(
        "--port", type=int, default=DEFAULT_CDP_PORT, help=f"원격 디버깅 포트 (기본 {DEFAULT_CDP_PORT})"
    )
    parser.add_argument("--url", default="about:blank", help="시작 URL")
    parser.add_argument("--profile", default="cdp_session", help="Chrome 프로필 이름 (data/browser_sessions/<name>)")
    parser.add_argument("--wait", type=int, default=3, help="Chrome 시작 후 대기 초")
    args = parser.parse_args()

    print(f"[CDP] 포트 {args.port} 확인 중...")
    result = is_cdp_available(port=args.port, timeout=1.5)
    if result["available"]:
        print(f"[CDP] 이미 실행 중 → http://localhost:{args.port}")
        print("      연결하려면: python scripts/local_agent/connect_user_browser.py")
        return

    chrome_exe = _find_chrome_exe()
    if not chrome_exe:
        print("[오류] Chrome 실행 파일을 찾을 수 없습니다.")
        print("       Chrome이 설치되어 있는지 확인하세요.")
        sys.exit(1)

    assert_browser_launch_allowed(component="scripts.browser.cdp.start_chrome_with_cdp", action="chrome_cdp_launch")

    profile_dir = str(_ROOT / "data" / "browser_sessions" / args.profile)
    cmd = get_chrome_start_command(
        chrome_path=chrome_exe,
        user_data_dir=profile_dir,
        port=args.port,
    )

    if args.url and args.url != "about:blank":
        cmd += f" {args.url}"

    print("[CDP] Chrome 시작 중...")
    print(f"      포트: {args.port}")
    print(f"      프로필: {profile_dir}")
    print(f"      URL: {args.url}")
    print(f"      명령: {cmd}")
    print()

    # 로컬 CLI 도구 — cmd는 이 스크립트가 조립하고, 유일한 외부입력(args.url)도
    # 실행한 사용자 본인이 커맨드라인으로 직접 넘긴 값이라 권한 경계를 넘는
    # 주입 경로가 아님(scripts/** 는 S 카테고리 자체가 이미 완화돼 있어 noqa 불필요).
    subprocess.Popen(cmd, shell=True)  # nosec B602 - 로컬 CLI: 실행한 사용자 본인이 넘긴 인자만 사용(권한 경계 없음)

    print(f"[CDP] Chrome 기동 대기 중 ({args.wait}초)...")
    for i in range(args.wait * 2):
        time.sleep(0.5)
        chk = is_cdp_available(port=args.port, timeout=0.5)
        if chk["available"]:
            print(f"[CDP] ✓ Chrome CDP 준비 완료 → http://localhost:{args.port}")
            print()
            print("      AI 브라우저 자동화 사용 가능합니다.")
            print("      예: python scripts/local_agent/connect_user_browser.py")
            return

    print("[CDP] 타임아웃: Chrome이 아직 응답하지 않습니다.")
    print(f"      수동 확인: http://localhost:{args.port}/json")


if __name__ == "__main__":
    main()

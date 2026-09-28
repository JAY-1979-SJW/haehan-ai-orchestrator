"""
Playwright 설치 상태 진단 스크립트

로컬 에이전트 실행 전 Playwright 환경을 점검한다.
사용: python scripts/local_agent/check_playwright_bootstrap.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# repo root를 sys.path에 추가
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ai_orchestrator.local_agent.playwright_bootstrap import (
    PLAYWRIGHT_BROWSER_MISSING,
    PLAYWRIGHT_PACKAGE_MISSING,
    PLAYWRIGHT_READY,
    check_playwright_status,
    ensure_playwright_ready,
)


def main() -> int:
    print("=== Playwright 설치 상태 진단 ===\n")

    result = check_playwright_status()
    status = result["status"]
    version = result.get("package_version")
    browser_ok = result.get("browser_available", False)
    message = result.get("message_ko", "")
    install_cmd = result.get("install_command")

    print(f"상태     : {status}")
    print(f"버전     : {version or '미설치'}")
    print(f"브라우저 : {'사용 가능' if browser_ok else '사용 불가'}")
    print(f"메시지   : {message}")

    if status == PLAYWRIGHT_READY:
        print("\n✓ Playwright 준비 완료. 로컬 에이전트를 실행할 수 있습니다.")
        return 0

    print()
    if install_cmd:
        print(f"설치 명령: {install_cmd}")

    if status == PLAYWRIGHT_BROWSER_MISSING:
        print("\nChromium 자동 설치를 시도하려면:")
        print("  python scripts/local_agent/check_playwright_bootstrap.py --install")
        if "--install" in sys.argv:
            print("\nChromium 설치 중...")
            install_result = ensure_playwright_ready(auto_install=True)
            if install_result["status"] == PLAYWRIGHT_READY:
                print("✓ Chromium 설치 완료.")
                return 0
            else:
                print(f"✗ 설치 실패: {install_result.get('message_ko', '')}")
                return 2

    if status == PLAYWRIGHT_PACKAGE_MISSING:
        print("\npip install playwright 후 다시 실행하세요.")

    return 1


if __name__ == "__main__":
    sys.exit(main())

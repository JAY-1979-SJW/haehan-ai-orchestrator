#!/usr/bin/env python
"""로그인 감지 대기 재시작 — 수동 실행 스크립트(pytest 수집 대상 아님).

최상단에 있던 실행 코드가 `if __name__ == "__main__":` 가드 없이 그대로 있어서,
pytest 가 이 파일을 "test_*.py" 로 보고 수집(import)하는 순간 `sys.exit()` 가
실행돼 그 xdist 워커 프로세스가 죽었다(INTERNALERROR, 2026-10-10 run38015451820·
run38009465088 재발 — 결정론적, 이 파일이 수집될 때마다 재현됨). 가드를 씌워
수동 실행(`python tests/integration/manual/test_wait_login.py`) 동작은 그대로
유지하면서 수집 시엔 아무 일도 안 하게 한다.
"""
import sys
from scripts.browser.agent.cdp_session_manager import wait_for_login


def _main() -> int:
    print("로그인 감지 대기 시작 (타임아웃 5분)...")
    print("Chrome 창에서 수동으로 로그인하면 자동 감지됩니다.")
    print("-" * 60)

    ok = wait_for_login("naver.com", timeout=300)

    if ok:
        print("\n✓ 로그인 감지됨!")
        return 0
    print("\n✗ 로그인 타임아웃 (5분)")
    return 1


if __name__ == "__main__":
    sys.exit(_main())

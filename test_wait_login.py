#!/usr/bin/env python
"""로그인 감지 대기 재시작."""
import sys
from ai_orchestrator.local_agent.browser.cdp_session_manager import wait_for_login

print("로그인 감지 대기 시작 (타임아웃 5분)...")
print("Chrome 창에서 수동으로 로그인하면 자동 감지됩니다.")
print("-" * 60)

ok = wait_for_login("naver.com", timeout=300)

if ok:
    print("\n✓ 로그인 감지됨!")
    sys.exit(0)
else:
    print("\n✗ 로그인 타임아웃 (5분)")
    sys.exit(1)

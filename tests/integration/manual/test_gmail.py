#!/usr/bin/env python
"""Gmail 모듈 테스트 (직렬 순서 - list_inbox → send)."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scripts.google import Google
from scripts.browser.cdp.connection import get_page


def test_list_inbox():
    """받은편지함 목록 조회."""
    print("\n[TEST] Gmail.list_inbox() 시작...")
    page = get_page()
    try:
        g = Google(page)

        # 로그인 확인
        page.goto("https://mail.google.com", timeout=20000)
        time.sleep(2)
        if "accounts.google.com" in page.url or "signin" in page.url.lower():
            print("  미로그인 감지, 자동 로그인...")
            g.ensure_login()

        # 받은편지함 목록 조회
        result = g.gmail.list_inbox(limit=10)
        print(f"  결과: {len(result)}개 메일 조회됨")
        for i, mail in enumerate(result[:3], 1):
            print(f"    [{i}] 발신자: {mail.get('from', '?')}")
            print(f"        제목: {mail.get('subject', '(제목 없음)')[:60]}")
            print(f"        읽음: {not mail.get('unread', False)}")

        return result
    except Exception as e:  # noqa: BLE001 - 수동 Gmail 읽기전용 통합 테스트 — 조회 실패 시 오류를 출력하고 빈 리스트를 반환, 쓰기 동작 없음.
        print(f"  ❌ 실패: {e}")
        import traceback

        traceback.print_exc()
        return []
    finally:
        page.close()


if __name__ == "__main__":
    result = test_list_inbox()
    if result:
        print(f"\n✅ Gmail.list_inbox() 성공 - {len(result)}개 메일")
    else:
        print("\n⚠️ Gmail.list_inbox() 실패 또는 메일 없음")

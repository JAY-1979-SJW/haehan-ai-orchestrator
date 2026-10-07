#!/usr/bin/env python
"""Gmail 테스트 — CDP 브라우저 (사용자 개인 세션) 사용."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scripts.google import Google
from scripts.browser.cdp.connection import get_page


def test_gmail_serial():
    print("\n[TEST 1] Gmail.list_inbox() — 받은편지함 조회")
    print("=" * 60)

    page = get_page()
    try:
        g = Google(page)

        inbox = g.gmail.list_inbox(limit=5)
        print(f"✅ 받은편지함: {len(inbox)}개 메일 조회")
        for i, mail in enumerate(inbox[:3], 1):
            print(f"  [{i}] {mail.get('from', '?')} | {mail.get('subject', '')[:50]}")

        print("\n[TEST 2] Gmail.send() — 메일 발송")
        print("=" * 60)
        result = g.gmail.send(
            to="skyjwshin@kakao.com",
            subject="[테스트] Gmail 자동화 모듈 검증",
            body="Gmail 자동화 모듈이 정상 작동합니다.\n\n발송 시간: " + time.strftime("%Y-%m-%d %H:%M:%S"),
        )

        if result.get("ok"):
            print(f"✅ 메일 발송 성공 → {result.get('to')}")
        else:
            print(f"❌ 발송 실패: {result.get('error')}")

        return result

    except Exception as e:  # noqa: BLE001 - 수동 Gmail 발송 테스트 — 실패 시 오류를 출력하고 ok=False 결과를 반환하는 진단용 except, 결과를 숨기지 않음.
        print(f"❌ 오류: {e}")
        import traceback

        traceback.print_exc()
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    result = test_gmail_serial()
    status = "✅ 완료" if result.get("ok") else "⚠️ 실패"
    print(f"\n{status}")

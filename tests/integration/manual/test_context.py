#!/usr/bin/env python3
"""현재 context와 page 상태 진단."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))



def main() -> None:
    """수동 진단 스크립트 — `python tests/integration/manual/test_context.py` 로만 실행한다.

    2026-10-05: 이 코드가 모듈 최상위에 있어 pytest 가 파일을 수집(import)하기만 해도 사용자 9222 브라우저에 붙고 마지막 탭을 닫았다.
    """
    from scripts.browser.cdp.connection import get_page

    print("=" * 60)
    print("Context & Page 상태 진단")
    print("=" * 60)

    # 1. 첫 번째 get_page() 호출
    page1 = get_page()
    ctx1_id = id(page1.context)
    page1_id = id(page1)
    pages1_count = len(page1.context.pages)

    print("\n[1차 호출]")
    print(f"  Page ID: {page1_id}")
    print(f"  Context ID: {ctx1_id}")
    print(f"  Pages in context: {pages1_count}개")
    print(f"  Current URL: {page1.url}")

    # 2. 두 번째 get_page() 호출
    page2 = get_page()
    ctx2_id = id(page2.context)
    page2_id = id(page2)
    pages2_count = len(page2.context.pages)

    print("\n[2차 호출]")
    print(f"  Page ID: {page2_id}")
    print(f"  Context ID: {ctx2_id}")
    print(f"  Pages in context: {pages2_count}개")
    print(f"  Current URL: {page2.url}")

    # 3. 비교
    print("\n[비교 분석]")
    print(f"  같은 Page인가? {page1_id == page2_id}")
    print(f"  같은 Context인가? {ctx1_id == ctx2_id}")

    # 4. 탭 목록
    print("\n[현재 탭 목록]")
    for i, p in enumerate(page1.context.pages, 1):
        print(f"  [{i}] {p.url[:50]}...")

    # 5. page.close() 테스트
    print("\n[탭 닫기 테스트]")
    try:
        test_pages = page1.context.pages[:]
        if len(test_pages) > 1:
            target_page = test_pages[-1]
            print(f"  닫기 대상: {target_page.url[:50]}...")
            target_page.close()
            print("  ✓ page.close() 실행됨")

            # 닫기 후 확인
            import time

            time.sleep(0.5)
            remaining = len(page1.context.pages)
            print(f"  닫기 후 탭 개수: {remaining}개 (이전: {pages1_count}개)")
    except Exception as e:  # noqa: BLE001 - 수동 통합 테스트 스크립트 — 예외 발생 시 오류 메시지와 traceback을 출력하는 진단용 except, 결과를 숨기지 않음.
        print(f"  ✗ 오류: {e}")

    print("=" * 60)


if __name__ == "__main__":
    main()

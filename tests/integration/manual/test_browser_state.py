#!/usr/bin/env python
"""현재 브라우저 상태 진단 — 수동 실행 스크립트(pytest 수집 대상 아님).

최상단 실행 코드에 `if __name__ == "__main__":` 가드가 없어서, pytest 가 이
파일을 "test_*.py" 로 보고 수집(import)하는 순간 실제 CDP 에 연결해 BrowserAgent()
를 띄웠다(2026-10-10, test_wait_login.py 와 같은 결함 패턴 — W1 전수조사로 발견).
가드를 씌워 수동 실행 동작은 그대로 유지하면서 수집 시엔 아무 일도 안 하게 한다.
"""

from scripts.browser.agent.agent import BrowserAgent
from scripts.browser.agent.cdp_session_manager import get_cdp_cookies, get_logged_in_sites, is_logged_in


def _main() -> None:
    print("=" * 60)
    print("1. 로그인 상태 확인")
    print("=" * 60)
    print(f"Naver logged in: {is_logged_in('naver.com')}")
    print(f"Logged sites: {get_logged_in_sites()}")

    print("\n" + "=" * 60)
    print("2. CDP 쿠키 목록")
    print("=" * 60)
    cookies = get_cdp_cookies()
    print(f"Total cookies: {len(cookies)}")
    for c in cookies[:5]:  # 처음 5개만 표시
        print(f"  {c.get('name', 'N/A')} (domain={c.get('domain', 'N/A')})")
    if len(cookies) > 5:
        print(f"  ... and {len(cookies) - 5} more")

    print("\n" + "=" * 60)
    print("3. BrowserAgent 세션 상태")
    print("=" * 60)
    try:
        with BrowserAgent() as agent:
            print(f"Session ID: {agent._session_id}")
            print(f"Browser: {agent._browser is not None}")
            if agent._browser:
                ctx_count = len(agent._browser.contexts)
                print(f"Contexts: {ctx_count}")
                if ctx_count > 0:
                    ctx = agent._browser.contexts[0]
                    pages = ctx.pages
                    print(f"Pages in context 0: {len(pages)}")
                    for i, page in enumerate(pages):
                        print(f"  Page {i}: {page.url}")
    except Exception as e:  # noqa: BLE001 - 수동 통합 테스트 스크립트 — 예외 발생 시 오류 메시지와 traceback을 출력하는 진단용 except, 결과를 숨기지 않음.
        import traceback

        print(f"Error: {e}")
        traceback.print_exc()

    print("\n" + "=" * 60)


if __name__ == "__main__":
    _main()

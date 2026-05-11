#!/usr/bin/env python
"""현재 브라우저 상태 진단."""
from ai_orchestrator.local_agent.browser.agent import BrowserAgent
from ai_orchestrator.local_agent.browser.cdp_session_manager import (
    is_logged_in, get_logged_in_sites, get_cdp_cookies
)

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
except Exception as e:
    import traceback
    print(f"Error: {e}")
    traceback.print_exc()

print("\n" + "=" * 60)

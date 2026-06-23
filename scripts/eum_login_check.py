import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ai_orchestrator.local_agent.browser.agent import BrowserAgent

agent = BrowserAgent()
agent.connect()
agent.go("https://eum.cw.or.kr/web/man/WEBMAN370M00")
time.sleep(3)

print("현재 URL:", agent._page.url)
html = agent._page.content()

# 신규현장 목록 페이지 접근 가능 여부
if "WEBMAN370M00" in agent._page.url:
    print("신규현장 목록 접근: ✅ 로그인됨")
elif "login" in agent._page.url.lower() or "WEBCOM010" in agent._page.url:
    print("신규현장 목록 접근: ❌ 로그인 필요 → 리다이렉트됨")
else:
    print("현재 URL 확인 필요:", agent._page.url)

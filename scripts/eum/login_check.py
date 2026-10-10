import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.browser.agent.agent import BrowserAgent

agent = BrowserAgent()
agent.connect()
agent.go("https://eum.cw.or.kr/web/man/WEBMAN370M00")
time.sleep(3)

page = agent._page
assert page is not None, (
    "브라우저 페이지가 없습니다(connect 실패)"
)  # 타입 좁히기 — 이동 전에는 None 이면 AttributeError 로 같은 곳에서 멈췄다
print("현재 URL:", page.url)
html = page.content()

# 신규현장 목록 페이지 접근 가능 여부
if "WEBMAN370M00" in page.url:
    print("신규현장 목록 접근: ✅ 로그인됨")
elif "login" in page.url.lower() or "WEBCOM010" in page.url:
    print("신규현장 목록 접근: ❌ 로그인 필요 → 리다이렉트됨")
else:
    print("현재 URL 확인 필요:", page.url)

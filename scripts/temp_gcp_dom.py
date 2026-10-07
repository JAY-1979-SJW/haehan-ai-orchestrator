"""GCP frame_locator로 드롭다운 접근."""

import sys
import time

sys.path.insert(0, ".")

from dotenv import load_dotenv

from scripts.browser.agent.agent import BrowserAgent

load_dotenv()

agent = BrowserAgent()
agent.connect()
page = agent.page

# frame_locator로 iframe 접근
iframes = [
    'iframe[src*="clients/create"]',
    "iframe:nth-child(1)",
    "iframe:nth-child(2)",
    "iframe:nth-child(3)",
]

for sel in iframes:
    try:
        fl = page.frame_locator(sel)
        inputs = fl.locator("input, select, [role=combobox]").all()
        if inputs:
            print(f"{sel}: {len(inputs)}개 요소")
            for el in inputs[:5]:
                print(f"  {el.inner_text()[:30]}")
    except Exception:  # noqa: BLE001 - 임시 DOM 탐색/디버깅용 수동 스크립트 — 셀렉터 조회 실패를 무시하고 나머지 mouse 클릭 등 탐색을 계속하는 read-only 디버그 코드.
        pass

# mouse 직접 클릭
page.mouse.click(504, 230)
time.sleep(2)
page.screenshot(path="data/gcp_mouse.png", full_page=True)

# 화면에 새 요소 나타났는지
all_text = page.evaluate("() => document.body.innerText")
if "데스크톱" in all_text or "Desktop" in all_text:
    print("데스크톱 옵션 발견!")
    print(all_text[all_text.find("데스크톱") - 50 : all_text.find("데스크톱") + 100])
else:
    print("데스크톱 없음, innerText 길이:", len(all_text))
    # 키보드로 시도
    page.keyboard.press("Tab")
    page.keyboard.press("Space")
    time.sleep(1)
    page.screenshot(path="data/gcp_keyboard.png", full_page=True)
    all_text2 = page.evaluate("() => document.body.innerText")
    if "데스크톱" in all_text2:
        print("키보드로 데스크톱 발견!")

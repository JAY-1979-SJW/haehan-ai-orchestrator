"""GCP 클라이언트 생성 - 메인 내 드롭다운 클릭."""

import sys
import time

sys.path.insert(0, ".")
from pathlib import Path

from dotenv import load_dotenv

from scripts.browser.agent.agent import BrowserAgent

load_dotenv()

agent = BrowserAgent()
agent.connect()
page = agent.page

page.goto("https://console.cloud.google.com/auth/clients/create?project=haehan-ai")
time.sleep(4)

# main 내 combobox 클릭
dd = page.locator("main [role=combobox]").first
if dd.count():
    dd.click()
    print("드롭다운 클릭")
    time.sleep(2)

# 나타난 옵션 목록 (main 외부에 나타날 수 있음)
options = page.locator("[role=option]").all()
print(f"옵션 {len(options)}개")
for opt in options:
    t = opt.inner_text().strip()
    print(f"  [{t[:50]}]")

# 데스크톱 앱 선택
for opt in options:
    t = opt.inner_text().strip()
    if "데스크톱" in t:
        opt.click()
        print(f"선택: {t}")
        time.sleep(1)
        break

# 이름 입력
page.screenshot(path="data/gcp_after_type.png", full_page=True)
inputs = page.locator("main input").all()
print(f"입력란 {len(inputs)}개")
for inp in inputs:
    print(f"  placeholder={inp.get_attribute('placeholder') or ''}, aria-label={inp.get_attribute('aria-label') or ''}")

# 이름 입력
for inp in inputs:
    lbl = inp.get_attribute("aria-label") or inp.get_attribute("placeholder") or ""
    if "이름" in lbl or "name" in lbl.lower():
        inp.fill("haehan-youtube-desktop")
        print("이름 입력")
        break
else:
    if inputs:
        inputs[0].fill("haehan-youtube-desktop")
        print("첫 번째 input에 이름 입력")

time.sleep(1)

# 만들기 버튼
create_btn = page.locator('button:has-text("만들기"), button:has-text("Create")').last
create_btn.click()
print("만들기 클릭")
time.sleep(5)

print("URL:", page.url[:80])
content = page.inner_text("body")
print(content[:2000])

# JSON 다운로드
dl_btn = page.locator('button:has-text("JSON"), a:has-text("JSON")').first
if dl_btn.count():
    dest = Path("ai_orchestrator/storage/secrets/youtube_desktop_oauth_client.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with page.expect_download() as dl_info:
        dl_btn.click()
    dl_info.value.save_as(str(dest))
    print(f"저장: {dest}")

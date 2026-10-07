import sys
import time

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[2]))
from scripts.browser.cdp.connection import get_page
from scripts.browser.page.page_helper import page_goto

page = get_page()

page_goto(page, 'https://developers.kakao.com/console/app/1413624/config')
page.wait_for_load_state('networkidle', timeout=10000)

# "앱 영구 삭제" 버튼 클릭
page.locator("button:has-text('앱 영구 삭제')").click()
time.sleep(2)

# 모달 내 구조 확인
modal = page.evaluate("""() => {
    // 모든 input 확인
    const inps = [...document.querySelectorAll('input')].map(i=>({
        type:i.type, ph:i.placeholder.slice(0,40), val:i.value.slice(0,30),
        disabled:i.disabled, parent:i.parentElement?.className?.slice(0,50)||''
    }));
    // 모든 버튼
    const btns = [...document.querySelectorAll('button')].map(b=>({
        text:b.innerText.trim().slice(0,20), disabled:b.disabled,
        cls:b.className.slice(0,50)
    })).filter(b=>b.text);
    // 모달 컨테이너
    const modals = [...document.querySelectorAll('[role=dialog],[class*=modal],[class*=Modal]')]
        .map(m=>({tag:m.tagName, cls:m.className.slice(0,60), id:m.id}));
    return {inps, btns, modals};
}""")

print('=== 모달 내 input ===')
for i in modal['inps']: print(' -', i)
print('\n=== 버튼 ===')
for b in modal['btns']: print(' -', b)
print('\n=== 모달 컨테이너 ===')
for m in modal['modals']: print(' -', m)

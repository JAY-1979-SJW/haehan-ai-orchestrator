"""캘린더 폼 구조 확인"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

port = 9222

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(f"http://localhost:{port}")
    ctx = browser.contexts[0]
    page = ctx.new_page()

    page.goto("https://calendar.google.com/calendar/u/0/r", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(5000)

    # 만들기 버튼 클릭
    page.evaluate("""() => {
        const btn = document.querySelector('button[aria-label*="만들"]');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(3000)

    print("[1] 폼 구조:")
    form_info = page.evaluate("""() => {
        const inputs = [];
        for (const inp of document.querySelectorAll('input')) {
            inputs.push({
                type: inp.type,
                placeholder: inp.placeholder,
                ariaLabel: inp.getAttribute('aria-label'),
                name: inp.name,
                id: inp.id,
                visible: inp.offsetParent !== null
            });
        }
        return inputs;
    }""")

    for i, inp in enumerate(form_info):
        print(f"  [{i}] type={inp['type']}, placeholder={inp['placeholder']}, aria={inp['ariaLabel']}, visible={inp['visible']}")

    print("\n[2] 제목 입력창 찾기 및 입력:")
    page.evaluate("""() => {
        // 제목 입력창 찾기 (여러 선택자 시도)
        let titleInput = document.querySelector('input[placeholder*="제목"]')
            || document.querySelector('input[placeholder*="title"]')
            || document.querySelector('input[aria-label*="제목"]')
            || document.querySelector('input[type="text"]');

        if (titleInput) {
            titleInput.focus();
            titleInput.value = '테스트 이벤트';
            titleInput.dispatchEvent(new Event('input', { bubbles: true }));
            console.log('Title filled:', titleInput.value);
        }
    }""")
    page.wait_for_timeout(1000)

    print("\n[3] 날짜/시간 입력창 구조:")
    date_info = page.evaluate("""() => {
        const dateInputs = document.querySelectorAll('input[type="date"], input[type="time"]');
        const dateFields = [];
        for (const inp of dateInputs) {
            dateFields.push({
                type: inp.type,
                placeholder: inp.placeholder,
                ariaLabel: inp.getAttribute('aria-label'),
                visible: inp.offsetParent !== null
            });
        }
        return {
            dateInputCount: dateInputs.length,
            dateFields: dateFields
        };
    }""")

    print(f"  Date/Time input 개수: {date_info['dateInputCount']}")
    for field in date_info['dateFields']:
        print(f"    - type={field['type']}, aria={field['ariaLabel']}, visible={field['visible']}")

    print("\n[4] 저장 버튼 찾기:")
    save_btn = page.evaluate("""() => {
        const buttons = [];
        for (const btn of document.querySelectorAll('button')) {
            const text = btn.textContent.toLowerCase();
            const aria = btn.getAttribute('aria-label')?.toLowerCase() || '';
            if (text.includes('저장') || text.includes('save') || aria.includes('저장') || aria.includes('save')) {
                buttons.push({
                    text: btn.textContent.trim().substring(0,20),
                    aria: btn.getAttribute('aria-label'),
                    visible: btn.offsetParent !== null
                });
            }
        }
        return buttons;
    }""")
    print(f"  저장 버튼: {save_btn}")

    page.close()

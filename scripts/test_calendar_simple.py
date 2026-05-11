"""캘린더 페이지 간단한 검사"""
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

    print("[1] 캘린더 페이지 열기...")
    page.goto("https://calendar.google.com/calendar/u/0/r", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(5000)

    print("[2] JavaScript로 버튼 찾기...")
    result = page.evaluate("""() => {
        const buttons = [];
        for (const btn of document.querySelectorAll('button')) {
            const ariaLabel = btn.getAttribute('aria-label');
            const text = btn.textContent.trim();
            if (ariaLabel && ariaLabel.includes('만들')) {
                buttons.push({label: ariaLabel, text: text.substring(0,20)});
            }
        }
        return {
            allButtons: document.querySelectorAll('button').length,
            createButtons: buttons,
            url: window.location.href
        };
    }""")

    print(f"  URL: {result['url']}")
    print(f"  총 버튼: {result['allButtons']}개")
    print(f"  만들기 버튼: {result['createButtons']}")

    if result['createButtons']:
        print("[3] 만들기 버튼 클릭 시도...")
        page.evaluate("""() => {
            const btn = document.querySelector('button[aria-label*="만들"]');
            if (btn) {
                console.log('Found button:', btn.getAttribute('aria-label'));
                btn.click();
            }
        }""")
        page.wait_for_timeout(2000)

        print("[4] 팝업/폼 확인...")
        form_result = page.evaluate("""() => {
            return {
                inputs: document.querySelectorAll('input').length,
                dialogs: document.querySelectorAll('[role="dialog"]').length,
                forms: document.querySelectorAll('form').length
            };
        }""")
        print(f"  Input 필드: {form_result['inputs']}")
        print(f"  Dialog: {form_result['dialogs']}")
        print(f"  Form: {form_result['forms']}")

    page.close()

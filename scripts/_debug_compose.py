"""Gmail 작성창 팝업 내부 DOM 확인."""
import sys, json
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parents[1]))
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://localhost:9222")
    ctx = browser.contexts[0]
    page = ctx.new_page()

    page.goto("https://mail.google.com/mail/u/0/#inbox", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    try:
        page.locator("div.T-I.T-I-KE.L3").first.click()
    except Exception:
        page.keyboard.press("c")
    page.wait_for_timeout(2000)
    print(f"URL: {page.url}")

    # 작성창 팝업 컨테이너 찾기
    result = page.evaluate("""() => {
        // 작성창 관련 클래스/역할 찾기
        const compose = document.querySelector('.nH.Hd[role=dialog], .dw.UC, [data-tooltip="닫기"]');
        if (compose) return {found: true, html: compose.outerHTML.substring(0, 500)};

        // aria-label로 입력 필드 찾기
        const inputs = document.querySelectorAll('[aria-label], [placeholder]');
        const visible = Array.from(inputs).filter(e => e.offsetWidth > 0).map(e => ({
            tag: e.tagName,
            ariaLabel: e.getAttribute('aria-label') || '',
            placeholder: e.placeholder || '',
            role: e.getAttribute('role') || '',
            contenteditable: e.getAttribute('contenteditable') || '',
        }));
        return {found: false, visible_inputs: visible.slice(0, 20)};
    }""")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    page.close()
print("완료")

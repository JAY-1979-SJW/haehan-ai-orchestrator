"""Gmail 작성창 필드 확인 (URL 방식, 충분한 대기)."""
import sys, json
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parents[1]))
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://localhost:9222")
    ctx = browser.contexts[0]
    page = ctx.new_page()

    page.goto("https://mail.google.com/mail/u/0/?view=cm&fs=1&to=test@test.com&su=테스트제목",
              timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    print(f"URL: {page.url}")

    result = page.evaluate("""() => {
        // 모든 input, textarea, contenteditable 요소
        const all = Array.from(document.querySelectorAll('input,textarea,[contenteditable],[role=textbox],[aria-label]'))
            .filter(e => e.offsetWidth > 0)
            .map(e => ({
                tag: e.tagName,
                ariaLabel: e.getAttribute('aria-label') || '',
                name: e.name || '',
                role: e.getAttribute('role') || '',
                contenteditable: e.getAttribute('contenteditable') || '',
                placeholder: e.placeholder || '',
                value: (e.value||e.innerText||'').substring(0,30),
                class: e.className.substring(0,60),
            }));

        // 전송 버튼 후보
        const sendBtns = Array.from(document.querySelectorAll('[data-tooltip],[aria-label]'))
            .filter(e => {
                const t = (e.getAttribute('data-tooltip')||e.getAttribute('aria-label')||'');
                return t.includes('보내') || t.includes('Send');
            })
            .map(e => ({tag: e.tagName, tooltip: e.getAttribute('data-tooltip')||'', label: e.getAttribute('aria-label')||''}));

        return {inputs: all.slice(0,30), send_btns: sendBtns};
    }""")
    print("입력 필드:")
    for r in result['inputs']:
        print(f"  [{r['tag']}] aria={r['ariaLabel']!r} name={r['name']!r} val={r['value']!r}")
    print("\n전송 버튼:")
    for r in result['send_btns']:
        print(f"  [{r['tag']}] tooltip={r['tooltip']!r} label={r['label']!r}")

    page.close()
print("\n완료")

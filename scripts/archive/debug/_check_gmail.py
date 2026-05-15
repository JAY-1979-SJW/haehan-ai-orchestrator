import sys, time
sys.path.insert(0, '.')
from scripts.web_connector import get_page
page = get_page()
page.goto('https://mail.google.com/mail/u/0/', timeout=30000, wait_until='domcontentloaded')
time.sleep(3)
print('URL:', page.url)
btns = page.evaluate("""() => {
    return [...document.querySelectorAll('div[role="button"]')]
        .map(b => b.innerText.trim()).filter(t => t).slice(0, 15);
}""")
print('버튼들:', btns)

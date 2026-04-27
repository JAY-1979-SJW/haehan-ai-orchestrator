"""임시 탐색 스크립트 — 플랫폼/로그인 페이지 HTML 구조 파악용. 삭제 예정."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai_orchestrator.sites import secrets_policy as _sp
from playwright.sync_api import sync_playwright
from local_agent.browser_reader import _safe_close

_APP_ID = "1413624"
_PAGES = {
    "platform": f"https://developers.kakao.com/console/app/{_APP_ID}/config/platform",
    "login": f"https://developers.kakao.com/console/app/{_APP_ID}/product/login",
}

state_path = _sp.session_state_path("kakao_developers")
storage = {"storage_state": str(state_path)} if state_path.is_file() else {}

results = {}
with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(**storage)
    page = ctx.new_page()
    for name, url in _PAGES.items():
        try:
            page.goto(url, wait_until="networkidle", timeout=20000)
        except Exception:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
        html = page.content()
        # input/button/textarea 셀렉터 추출
        inputs = page.query_selector_all("input, textarea, button[type='submit'], button[type='button']")
        selectors = []
        for el in inputs[:40]:
            try:
                tag = el.evaluate("e => e.tagName")
                tp = el.get_attribute("type") or ""
                placeholder = el.get_attribute("placeholder") or ""
                text = (el.text_content() or "").strip()[:30]
                cls = (el.get_attribute("class") or "")[:60]
                aria = el.get_attribute("aria-label") or ""
                selectors.append({"tag": tag, "type": tp, "placeholder": placeholder, "text": text, "class": cls, "aria": aria})
            except Exception:
                pass
        results[name] = {"url": url, "input_buttons": selectors, "html_len": len(html)}
    _safe_close(page); _safe_close(ctx); _safe_close(browser)

print(json.dumps(results, ensure_ascii=False, indent=2))

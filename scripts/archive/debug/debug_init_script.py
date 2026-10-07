"""add_init_script으로 XHR/fetch 후킹 → 실제 API 탐지."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.browser.agent.agent import BrowserAgent

HOOK_JS = """
window.__cap = [];
const _xhrOpen = XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open = function(m, url, ...r) {
    this._capUrl = url;
    return _xhrOpen.apply(this, [m, url, ...r]);
};
const _xhrSend = XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.send = function(...a) {
    this.addEventListener('load', function() {
        window.__cap.push({ via: 'xhr', url: this._capUrl, status: this.status, body: this.responseText?.slice(0, 1000) });
    });
    return _xhrSend.apply(this, a);
};
const _fetch = window.fetch;
window.fetch = async function(...a) {
    const url = typeof a[0] === 'string' ? a[0] : (a[0]?.url || '');
    try {
        const resp = await _fetch(...a);
        const clone = resp.clone();
        clone.text().then(b => {
            window.__cap.push({ via: 'fetch', url, status: resp.status, body: b.slice(0, 1000) });
        }).catch(() => {});
        return resp;
    } catch(e) {
        window.__cap.push({ via: 'fetch', url, error: String(e) });
        throw e;
    }
};
"""

SEP = "─" * 60


def section(title):
    print(f"\n{SEP}\n  {title}\n{SEP}")


with BrowserAgent() as a:
    # add_init_script 주입 — 이후 모든 go()에서 유지됨
    a._page.add_init_script(HOOK_JS)

    # ── 캘린더 ────────────────────────────────────────────────────
    section("캘린더 XHR/Fetch 캡처")
    a.go("https://calendar.naver.com/")
    time.sleep(6)

    cap = a._page.evaluate("() => window.__cap || []")
    print(f"  캡처 총: {len(cap)}개")
    for x in cap:
        url = x.get("url", "")
        if any(k in url for k in ("schedule", "Schedule", "ajax", "event", "calendar.naver.com/a")):
            print(f"  [{x.get('status', 'ERR')}][{x['via']}] {url[:120]}")
            b = x.get("body", "")
            if b and not b.startswith("<!"):
                print(f"    {b[:300]!r}")

    # ── MyBox ─────────────────────────────────────────────────────
    section("MyBox XHR/Fetch 캡처")
    # 초기화
    a._page.evaluate("() => { window.__cap = []; }")
    a.go("https://mybox.naver.com/main/web/my")
    time.sleep(6)

    cap2 = a._page.evaluate("() => window.__cap || []")
    print(f"  캡처 총: {len(cap2)}개")
    for x in cap2:
        url = x.get("url", "")
        # 모든 API 호출 출력
        if "/api/" in url or "mybox" in url.lower():
            print(f"  [{x.get('status', 'ERR')}][{x['via']}] {url[:120]}")
            b = x.get("body", "")
            if b and not b.startswith("<!") and not b.startswith("/*") and len(b) > 5:
                print(f"    {b[:300]!r}")

    # ── mail search ───────────────────────────────────────────────
    section("mail search XHR/Fetch 캡처")
    from urllib.parse import quote

    a._page.evaluate("() => { window.__cap = []; }")
    a.go(f"https://mail.naver.com/v2/search?q={quote('네이버')}")
    time.sleep(6)

    cap3 = a._page.evaluate("() => window.__cap || []")
    print(f"  캡처 총: {len(cap3)}개")
    for x in cap3:
        url = x.get("url", "")
        if any(k in url for k in ("json", "search", "list", "mail.naver.com")):
            print(f"  [{x.get('status', 'ERR')}][{x['via']}] {url[:120]}")
            b = x.get("body", "")
            if b and not b.startswith("<!") and len(b) > 2:
                print(f"    {b[:400]!r}")

print(f"\n{SEP}\n  완료\n{SEP}\n")

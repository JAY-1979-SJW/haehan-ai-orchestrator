"""브라우저 컨텍스트 fetch() 방식으로 API 탐지."""
import sys
import time
import json
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ai_orchestrator.local_agent.browser.agent import BrowserAgent

SEP = "─" * 60

def section(title):
    print(f"\n{SEP}\n  {title}\n{SEP}")

with BrowserAgent() as a:

    # ── 1. 캘린더 API — 브라우저 fetch ────────────────────────────
    section("1. 캘린더 — 브라우저 내부 fetch")
    a.go("https://calendar.naver.com/")
    time.sleep(4)

    result = a._page.evaluate("""async () => {
        const ts = Date.now();
        const today = new Date();
        const y = today.getFullYear();
        const m = String(today.getMonth() + 1).padStart(2, '0');
        const urls = [
            `/ajax/GetScheduleList?ts=${ts}&startDt=${y}${m}01&endDt=${y}${m}31`,
            `/ajax/getScheduleList?ts=${ts}&startDt=${y}${m}01&endDt=${y}${m}31`,
            `/CalDav/GetScheduleList?startDt=${y}${m}01&endDt=${y}${m}31`,
        ];
        const results = [];
        for (const path of urls) {
            try {
                const resp = await fetch('https://calendar.naver.com' + path, { credentials: 'include' });
                const text = await resp.text();
                results.push({ url: path, status: resp.status, body: text.slice(0, 500) });
            } catch(e) {
                results.push({ url: path, error: String(e) });
            }
        }
        return results;
    }""")

    for r in (result or []):
        print(f"  [{r.get('status','ERR')}] {r.get('url','')}")
        print(f"    {r.get('body', r.get('error', ''))[:200]!r}")

    # ── 2. 캘린더 — 실제 사용 API 탐지 ──────────────────────────
    section("2. 캘린더 — XHR 후킹으로 실제 API 캡처")
    # 페이지에 XHR 후킹 주입
    a._page.evaluate("""() => {
        window.__xhrLog = [];
        const orig = XMLHttpRequest.prototype.open;
        XMLHttpRequest.prototype.open = function(method, url, ...rest) {
            this.__url = url;
            return orig.apply(this, [method, url, ...rest]);
        };
        const origSend = XMLHttpRequest.prototype.send;
        XMLHttpRequest.prototype.send = function(...args) {
            this.addEventListener('load', function() {
                window.__xhrLog.push({ url: this.__url, status: this.status, body: this.responseText?.slice(0,300) });
            });
            return origSend.apply(this, args);
        };
        // fetch 후킹
        window.__fetchLog = [];
        const origFetch = window.fetch;
        window.fetch = async function(...args) {
            const url = typeof args[0] === 'string' ? args[0] : (args[0]?.url || '');
            try {
                const resp = await origFetch(...args);
                const clone = resp.clone();
                const body = await clone.text();
                window.__fetchLog.push({ url, status: resp.status, body: body.slice(0, 300) });
                return resp;
            } catch(e) {
                window.__fetchLog.push({ url, error: String(e) });
                throw e;
            }
        };
    }""")

    # 월 이동하여 API 호출 유발
    a._page.evaluate("""() => {
        // 다음달 버튼 클릭 시도
        const btn = document.querySelector('[class*="next"], [class*="Next"], button[aria-label*="다음"]');
        if (btn) btn.click();
    }""")
    time.sleep(3)

    xhr_log = a._page.evaluate("() => window.__xhrLog || []")
    fetch_log = a._page.evaluate("() => window.__fetchLog || []")
    print(f"  XHR 로그: {len(xhr_log)}개")
    for x in xhr_log:
        if any(k in x.get('url','') for k in ('schedule','Schedule','ajax','event')):
            print(f"  [{x.get('status')}] {x.get('url','')[:100]}")
            print(f"    {x.get('body','')[:200]!r}")

    print(f"  Fetch 로그: {len(fetch_log)}개")
    for x in fetch_log:
        if any(k in x.get('url','') for k in ('schedule','Schedule','ajax','event','calendar')):
            print(f"  [{x.get('status')}] {x.get('url','')[:100]}")
            print(f"    {x.get('body','')[:200]!r}")

    # ── 3. MyBox — 브라우저 fetch로 API 탐지 ─────────────────────
    section("3. MyBox — 브라우저 내부 fetch + XHR 후킹")
    a._page.evaluate("""() => {
        window.__xhrLog = [];
        window.__fetchLog = [];
        const origXhrOpen = XMLHttpRequest.prototype.open;
        XMLHttpRequest.prototype.open = function(method, url, ...rest) {
            this.__url = url;
            return origXhrOpen.apply(this, [method, url, ...rest]);
        };
        const origXhrSend = XMLHttpRequest.prototype.send;
        XMLHttpRequest.prototype.send = function(...args) {
            this.addEventListener('load', function() {
                window.__xhrLog.push({ url: this.__url, status: this.status, body: this.responseText?.slice(0,300) });
            });
            return origXhrSend.apply(this, args);
        };
        const origFetch2 = window.fetch;
        window.fetch = async function(...args) {
            const url = typeof args[0] === 'string' ? args[0] : (args[0]?.url || '');
            try {
                const resp = await origFetch2(...args);
                const clone = resp.clone();
                const body = await clone.text();
                window.__fetchLog.push({ url, status: resp.status, body: body.slice(0, 500) });
                return resp;
            } catch(e) {
                window.__fetchLog.push({ url, error: String(e) });
                throw e;
            }
        };
    }""")

    a.go("https://mybox.naver.com/main/web/my")
    time.sleep(6)

    xhr_log2 = a._page.evaluate("() => window.__xhrLog || []")
    fetch_log2 = a._page.evaluate("() => window.__fetchLog || []")

    print(f"  XHR: {len(xhr_log2)}개, Fetch: {len(fetch_log2)}개")
    print("  --- XHR ---")
    for x in xhr_log2[:20]:
        print(f"  [{x.get('status')}] {x.get('url','')[:120]}")
        if x.get('body') and len(x['body']) > 10:
            print(f"    body: {x['body'][:200]!r}")

    print("  --- Fetch ---")
    for x in fetch_log2[:30]:
        print(f"  [{x.get('status')}] {x.get('url','')[:120]}")
        if x.get('body') and len(x['body']) > 10 and "html" not in x['body'][:50]:
            print(f"    body: {x['body'][:200]!r}")

    # ── 4. mail search — JSON API 직접 호출 ─────────────────────
    section("4. mail search — 브라우저 fetch")
    a.go("https://mail.naver.com/")
    time.sleep(3)

    result4 = a._page.evaluate("""async () => {
        const q = encodeURIComponent('네이버');
        const urls = [
            `/json/list?type=search&q=${q}&count=5`,
            `/json/search?q=${q}&count=5`,
            `/v2/search?q=${q}`,
        ];
        const results = [];
        for (const path of urls) {
            try {
                const resp = await fetch('https://mail.naver.com' + path, { credentials: 'include' });
                const text = await resp.text();
                results.push({ url: path, status: resp.status, body: text.slice(0, 500) });
            } catch(e) {
                results.push({ url: path, error: String(e) });
            }
        }
        return results;
    }""")

    for r in (result4 or []):
        print(f"  [{r.get('status','ERR')}] {r.get('url','')}")
        print(f"    {r.get('body', r.get('error', ''))[:300]!r}")

    # ── 5. mail folder JSON API ───────────────────────────────────
    section("5. mail folder/list JSON API")
    result5 = a._page.evaluate("""async () => {
        try {
            const resp = await fetch('https://mail.naver.com/json/folder/list?vipMailBox=true', { credentials: 'include' });
            const text = await resp.text();
            return { status: resp.status, body: text.slice(0, 1000) };
        } catch(e) { return { error: String(e) }; }
    }""")
    print(f"  {result5}")

print(f"\n{SEP}\n  완료\n{SEP}\n")

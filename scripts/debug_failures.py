"""실패 항목 디버그 스크립트 — 네트워크 캡처 및 DOM 탐지."""
import sys
import time
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ai_orchestrator.local_agent.browser.agent import BrowserAgent

SEP = "─" * 60

def section(title):
    print(f"\n{SEP}\n  {title}\n{SEP}")

with BrowserAgent() as a:

    # ── 1. 캘린더 응답 캡처 디버그 ─────────────────────────────────
    section("1. 캘린더 — 응답 URL 캡처")
    captured_urls = []

    def _cap(r):
        captured_urls.append((r.status, r.url[:120]))

    a._page.on("response", _cap)
    a.go("https://calendar.naver.com/")
    time.sleep(5)
    a._page.remove_listener("response", _cap)

    print(f"  캡처된 응답 수: {len(captured_urls)}")
    for st, url in captured_urls:
        if any(k in url for k in ("schedule", "Schedule", "ajax", "calendar.naver.com/a")):
            print(f"  [{st}] {url}")

    # GetScheduleList 직접 시도
    import time as _time
    ts = int(_time.time() * 1000)
    test_urls = [
        f"https://calendar.naver.com/ajax/GetScheduleList?ts={ts}&startDt=20260501&endDt=20260531",
        f"https://calendar.naver.com/CalDav/GetScheduleList?startDt=20260501&endDt=20260531",
    ]
    for url in test_urls:
        try:
            res = a._page.request.get(url)
            text = res.text()[:200]
            print(f"  직접 GET [{res.status}] {url[:80]}")
            print(f"    응답: {text!r}")
        except Exception as e:
            print(f"  직접 GET 오류: {e}")

    # ── 2. MyBox 응답 캡처 디버그 ─────────────────────────────────
    section("2. MyBox — 응답 URL 캡처")
    mybox_urls = []

    def _mybox_cap(r):
        mybox_urls.append((r.status, r.url))

    a._page.on("response", _mybox_cap)
    a.go("https://mybox.naver.com/main/web/my")
    time.sleep(5)
    a._page.remove_listener("response", _mybox_cap)

    print(f"  캡처된 응답 수: {len(mybox_urls)}")
    for st, url in mybox_urls:
        if "api" in url or "file" in url or "vault" in url or "list" in url or "mybox" in url.lower():
            print(f"  [{st}] {url[:120]}")

    # ── 3. MyBox quota DOM 탐지 ───────────────────────────────────
    section("3. MyBox — quota DOM 탐지")
    try:
        # 현재 페이지가 mybox
        raw = a._page.evaluate("""() => {
            const sels = ['[class*="quota"]','[class*="storage"]','[class*="capacity"]',
                          '[class*="usage"]','[class*="disk"]','[class*="space"]',
                          '[class*="total"]'];
            const results = [];
            for (const sel of sels) {
                const els = document.querySelectorAll(sel);
                els.forEach(el => {
                    const t = el.innerText?.trim();
                    if (t) results.push({ sel, text: t.slice(0, 80) });
                });
            }
            return results;
        }""")
        print(f"  탐지된 요소 수: {len(raw or [])}")
        for item in (raw or []):
            print(f"  [{item['sel']}] {item['text']!r}")
    except Exception as e:
        print(f"  오류: {e}")

    # ── 4. mail_unread_count — folders 상세 ──────────────────────
    section("4. mail_folders — count 상세")
    try:
        folders = a.mail_folders()
        print(f"  폴더 수: {len(folders)}")
        for f in folders[:10]:
            print(f"  {f}")
    except Exception as e:
        print(f"  오류: {e}")

    # ── 5. mail_search — 응답 캡처 ────────────────────────────────
    section("5. mail_search — 응답 URL 캡처")
    search_urls = []

    def _search_cap(r):
        search_urls.append((r.status, r.url))

    a._page.on("response", _search_cap)
    a.go(f"https://mail.naver.com/v2/search?q={quote('네이버')}")
    time.sleep(5)
    a._page.remove_listener("response", _search_cap)

    print(f"  캡처된 응답 수: {len(search_urls)}")
    for st, url in search_urls:
        if "json" in url or "search" in url or "list" in url:
            print(f"  [{st}] {url[:120]}")
            try:
                res = a._page.request.get(url)
                if res.ok:
                    data = res.json()
                    print(f"    JSON 키: {list(data.keys())[:6]}")
            except Exception as e:
                print(f"    파싱 오류: {e}")

print(f"\n{SEP}\n  디버그 완료\n{SEP}\n")

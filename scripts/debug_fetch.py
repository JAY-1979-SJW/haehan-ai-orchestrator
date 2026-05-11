"""각 fetch 호출 상태 상세 디버그."""
import sys
from pathlib import Path
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ai_orchestrator.local_agent.browser.agent import BrowserAgent

with BrowserAgent() as a:
    print("=" * 70)
    print("  mail_folders fetch 디버그")
    print("=" * 70)
    a.go("https://mail.naver.com/")
    time.sleep(2)

    result = a._page.evaluate("""async () => {
        try {
            console.log('fetch 시작:', new Date().toISOString());
            const resp = await fetch('/json/folder/list?vipMailBox=true', { credentials: 'include' });
            console.log('fetch 응답:', resp.status, resp.statusText);
            const text = await resp.text();
            console.log('응답 길이:', text.length, '바이트');
            console.log('응답 처음 500자:', text.slice(0, 500));
            if (!resp.ok) return { error: `${resp.status} ${resp.statusText}`, text: text.slice(0, 200) };
            try {
                const json = JSON.parse(text);
                return { ok: true, status: resp.status, hasData: !!json, keys: Object.keys(json).slice(0, 5) };
            } catch(e) {
                return { ok: true, status: resp.status, parseError: String(e) };
            }
        } catch(e) {
            return { error: String(e) };
        }
    }""")
    print(f"결과: {result}")

    print("\n" + "=" * 70)
    print("  calendar_events fetch 디버그")
    print("=" * 70)
    a.go("https://calendar.naver.com/")
    time.sleep(3)

    result2 = a._page.evaluate("""async () => {
        try {
            const ts = Date.now();
            const url = `/ajax/GetScheduleList?ts=${ts}&startDt=20260501&endDt=20260531`;
            console.log('fetch URL:', url);
            const resp = await fetch(url, { credentials: 'include' });
            console.log('응답 상태:', resp.status);
            const text = await resp.text();
            console.log('응답 길이:', text.length);
            console.log('응답 처음 300자:', text.slice(0, 300));
            if (!resp.ok) return { error: `${resp.status} ${resp.statusText}` };
            try {
                const json = JSON.parse(text);
                return { ok: true, status: resp.status, keys: Object.keys(json).slice(0, 5) };
            } catch(e) {
                return { ok: true, status: resp.status, parseError: String(e) };
            }
        } catch(e) {
            return { error: String(e) };
        }
    }""")
    print(f"결과: {result2}")

    print("\n" + "=" * 70)
    print("  mybox_quota fetch 디버그")
    print("=" * 70)
    a.go("https://mybox.naver.com/main/web/my")
    time.sleep(3)

    result3 = a._page.evaluate("""async () => {
        try {
            const url = 'https://api.mybox.naver.com/service/quota/get';
            console.log('fetch URL:', url);
            const resp = await fetch(url, { credentials: 'include' });
            console.log('응답 상태:', resp.status);
            const text = await resp.text();
            console.log('응답 길이:', text.length);
            console.log('응답 처음 300자:', text.slice(0, 300));
            if (!resp.ok) return { error: `${resp.status} ${resp.statusText}` };
            try {
                const json = JSON.parse(text);
                return { ok: true, status: resp.status, keys: Object.keys(json).slice(0, 5) };
            } catch(e) {
                return { ok: true, status: resp.status, parseError: String(e) };
            }
        } catch(e) {
            return { error: String(e) };
        }
    }""")
    print(f"결과: {result3}")

print("\n" + "=" * 70)
print("  완료")
print("=" * 70)

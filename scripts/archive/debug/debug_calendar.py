"""캘린더 메서드 디버그."""
import sys
import time
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ai_orchestrator.local_agent.browser.agent import BrowserAgent

with BrowserAgent() as a:
    print("=" * 70)
    print("  캘린더 메서드 디버그")
    print("=" * 70)

    # 1. calendar_events 호출 후 window.__calendarRaw 상태 확인
    print("\n[1] calendar_events 호출")
    result = a.calendar_events("2026-05-01", "2026-05-31")
    print(f"  결과: {result}")

    # 페이지의 window 상태 확인
    cal_raw = a._page.evaluate("() => window.__calendarRaw")
    print(f"  window.__calendarRaw: {cal_raw}")

    # hook이 제대로 설정되었는지 확인
    hook_added = hasattr(a._page, '_calendar_hook_added')
    print(f"  _calendar_hook_added flag: {hook_added}")

    # 전체 window 변수 확인
    window_keys = a._page.evaluate("() => Object.keys(window).filter(k => k.startsWith('__'))")
    print(f"  __로 시작하는 window 변수들: {window_keys}")

    print("\n[2] 직접 HOOK 재설정 후 재시도")
    # 기존 flag 제거
    if hasattr(a._page, '_calendar_hook_added'):
        delattr(a._page, '_calendar_hook_added')

    # 같은 방식으로 호출
    result2 = a.calendar_events("2026-05-01", "2026-05-31")
    print(f"  결과: {result2}")

    cal_raw2 = a._page.evaluate("() => window.__calendarRaw")
    print(f"  window.__calendarRaw: {type(cal_raw2)} = {str(cal_raw2)[:500]}")

    print("\n[3] 수동 HOOK 테스트")
    a._page.add_init_script("""
    window.__testRaw = null;
    const origXhrOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(m, u, ...r) {
        this._hookUrl = u;
        return origXhrOpen.apply(this, [m, u, ...r]);
    };
    const origXhrSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.send = function(...a) {
        this.addEventListener('load', function() {
            if (this._hookUrl && this._hookUrl.includes('GetScheduleList')) {
                try {
                    window.__testRaw = JSON.parse(this.responseText);
                } catch(e) {}
            }
        });
        return origXhrSend.apply(this, a);
    };
    """)

    a.go("https://calendar.naver.com/")
    time.sleep(5)

    test_raw = a._page.evaluate("() => window.__testRaw")
    print(f"  window.__testRaw: {type(test_raw)} = {str(test_raw)[:500]}")

    print("\n" + "=" * 70)

"""네이버 캘린더 Mixin — auto_structure_builder 자동 생성."""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any


def _js(name: str) -> str:
    from scripts.common.browser_js_dir import JS_DIR

    return (JS_DIR / name).read_text(encoding="utf-8")


class CalendarMixin:
    """네이버 캘린더 기능.

    실제 캡처된 API: ['/data/variables', '/localeMessageForJs', '/data/colors', '/data/stickers', '/ajax/GetScheduleList']
    """

    if TYPE_CHECKING:
        # 다른 믹스인의 메서드·속성(go, _page …)을 self(MRO)로 쓴다 — 정적 검사기에는 합쳐진 클래스가 보이지 않으므로 알려 준다(런타임 영향 없음).
        def __getattr__(self, name: str) -> Any: ...

    def calendar_events(self, start: str, end: str) -> list[dict]:
        """일정 목록 조회 — XHR 후킹 방식. 응답 구조 v2 반영.

        Args:
            start: "YYYY-MM-DD"
            end: "YYYY-MM-DD"
        반환: [{id, title, start, end, location}]
        """
        HOOK = """
        window.__calendarRaw = null;
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
                        window.__calendarRaw = JSON.parse(this.responseText);
                    } catch(e) {}
                }
            });
            return origXhrSend.apply(this, a);
        };
        """
        if not hasattr(self._page, '_calendar_hook_added'):
            self._page.add_init_script(HOOK)
            self._page._calendar_hook_added = True

        self.go("https://calendar.naver.com/")
        time.sleep(4)

        raw = self._page.evaluate("() => window.__calendarRaw")
        if not raw:
            return []

        # 응답 구조: retScheduleList.returnValue.scheduleList (배열)
        return_value = (raw.get("retScheduleList") or {}).get("returnValue") or {}
        if not isinstance(return_value, dict):
            return []
        schedule_list = return_value.get("scheduleList") or []
        if not isinstance(schedule_list, list):
            return []

        s_filter = start.replace("-", "")
        e_filter = end.replace("-", "")
        result = []
        for ev in schedule_list:
            ev_start = str(ev.get("startDt", ""))
            ev_end   = str(ev.get("endDt", ""))
            # 날짜 범위 필터 (빈 문자열은 제외)
            if ev_start and (ev_start <= e_filter and ev_end >= s_filter):
                result.append({
                    "id":       str(ev.get("scheduleId", ev.get("id", ""))),
                    "title":    ev.get("subject", ev.get("title", "")),
                    "start":    ev_start,
                    "end":      ev_end,
                    "location": ev.get("location", ""),
                })
        return result

    def calendar_today(self) -> list[dict]:
        """오늘 일정 조회."""
        from datetime import date
        today = date.today().isoformat()
        return self.calendar_events(today, today)

    def calendar_create(self, title: str, start: str, end: str) -> dict:
        """일정 생성 준비 (사용자 승인 필수).

        반환: {ok, draft_url}
        """
        from scripts.common.cdp_audit import L2
        self.go("https://calendar.naver.com/")
        time.sleep(2)
        L2("CALENDAR_WRITE_PREPARED", "calendar_mixin", title=title, start=start, end=end)
        return {"ok": True, "draft_url": self._page.url}

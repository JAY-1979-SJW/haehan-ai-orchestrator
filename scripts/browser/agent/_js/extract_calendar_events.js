// 네이버 캘린더 일정 추출 — /ajax/GetScheduleList API 직접 호출
// args: { start: "YYYYMMDD", end: "YYYYMMDD" }
(async function (args) {
  const start = (args && args.start) || new Date().toISOString().slice(0,10).replace(/-/g,'');
  const end   = (args && args.end)   || start;

  try {
    const url = `/ajax/GetScheduleList?startDt=${start}&endDt=${end}&_=${Date.now()}`;
    const res = await fetch(url, { credentials: 'include' });
    if (!res.ok) return [];
    const data = await res.json();

    // 응답 구조: { result: { scheduleList: [...] } } 또는 { scheduleList: [...] }
    const list = data?.result?.scheduleList || data?.scheduleList || data?.result || [];
    if (!Array.isArray(list)) return [];

    return list.map(s => ({
      id:       String(s.scheduleId || s.id || ''),
      title:    s.subject || s.title || '',
      start:    s.startDt || s.startDate || start,
      end:      s.endDt   || s.endDate   || end,
      location: s.location || '',
      allDay:   Boolean(s.allDayYn === 'Y' || s.isAllDay),
    }));
  } catch (e) {
    return [];
  }
})(args);

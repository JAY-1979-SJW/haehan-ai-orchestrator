"""실시간 팝업 감지 — popup_watcher v1.0

MutationObserver를 주입해 DOM 변화 감시하고,
알려진 팝업이면 자동 처리, 모르는 팝업이면 보고.
"""
from __future__ import annotations

import json
import time as _t
from typing import TypedDict

POPUP_MARKERS = {
    "작성 중인 글": {"action": "click_button", "target": "취소"},
    "이어서 작성": {"action": "click_button", "target": "취소"},
    "임시저장": {"action": None},
}


class PopupEvent(TypedDict):
    ts_ms: int
    marker: str
    snippet: str
    frame_url: str


def build_watcher_js(markers: dict) -> str:
    """마커 카탈로그를 JS 코드 문자열로 변환."""
    marker_list = json.dumps([{"key": k} for k in markers.keys()])

    js_template = f"""(() => {{
  if (window.__hh_popup_state && window.__hh_popup_state.installed) return;
  const MARKERS = {marker_list};
  window.__hh_popup_state = {{ events: [], installed: true, lastSeen: {{}} }};
  const COOLDOWN_MS = 5000;
  const detect = () => {{
    const text = (document.body && document.body.innerText) || '';
    const nowMs = Date.now();
    for (const m of MARKERS) {{
      if (!text.includes(m.key)) continue;
      const last = window.__hh_popup_state.lastSeen[m.key] || 0;
      if (nowMs - last < COOLDOWN_MS) continue;
      window.__hh_popup_state.lastSeen[m.key] = nowMs;
      window.__hh_popup_state.events.push({{
        ts_ms: nowMs,
        marker: m.key,
        snippet: text.slice(0, 200),
        frame_url: location.href,
      }});
    }}
  }};
  const obs = new MutationObserver(detect);
  obs.observe(document.body, {{ childList: true, subtree: true }});
  setTimeout(detect, 100);
}})();"""
    return js_template


def install_watcher(page=None) -> dict:
    """페이지에 MutationObserver JS 코드를 주입한다."""
    if page is None:
        from scripts.navigator import get_page
        page = get_page()

    js = build_watcher_js(POPUP_MARKERS)
    frame_count = 0
    for frame in page.frames:
        try:
            frame.evaluate(js)
            frame_count += 1
        except Exception:
            continue

    return {"installed": True, "frame_count": frame_count}


def poll_events(page=None, since_ms: int = 0) -> list[PopupEvent]:
    """window.__hh_popup_state.events에서 since_ms 이후 이벤트를 읽어온다."""
    if page is None:
        from scripts.navigator import get_page
        page = get_page()

    for frame in page.frames:
        try:
            events = frame.evaluate(
                "(s) => (window.__hh_popup_state?.events||[]).filter(e => e.ts_ms > s)",
                since_ms
            )
            if events:
                return events
        except Exception:
            continue
    return []


def clear_events(page=None) -> None:
    """window.__hh_popup_state.events를 초기화한다."""
    if page is None:
        from scripts.navigator import get_page
        page = get_page()

    for frame in page.frames:
        try:
            frame.evaluate("() => { window.__hh_popup_state.events = []; }")
        except Exception:
            continue


def auto_handle(page=None) -> dict:
    """poll_events → 각 이벤트 처리 → clear_events."""
    if page is None:
        from scripts.navigator import get_page
        page = get_page()

    handled = []
    skipped = []
    unknown = []

    events = poll_events(page=page)
    for ev in events:
        spec = POPUP_MARKERS.get(ev["marker"])
        if spec is None:
            unknown.append(ev)
            continue
        if spec["action"] is None:
            skipped.append(ev)
            continue
        if spec["action"] == "click_button":
            from scripts.navigator import click_button
            ok = click_button(spec["target"])
            handled.append({"event": ev, "clicked": ok})

    if events:
        clear_events(page=page)

    return {"handled": handled, "skipped": skipped, "unknown": unknown}

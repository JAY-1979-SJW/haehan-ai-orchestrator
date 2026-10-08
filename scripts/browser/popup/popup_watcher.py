"""실시간 팝업 감지 — popup_watcher v1.0

MutationObserver를 주입해 DOM 변화 감시하고,
알려진 팝업이면 자동 처리, 모르는 팝업이면 보고.
"""

from __future__ import annotations

import json
from typing import Any, TypedDict

from scripts.common.logger import get_logger

_log = get_logger(__name__)

POPUP_MARKERS: dict[str, dict[str, Any]] = {
    "작성 중인 글": {"action": "click_button", "target": "취소"},
    "이어서 작성": {"action": "click_button", "target": "취소"},
    "임시저장": {"action": None},
    # ── 비정상 접근 감지 마커 ──────────────────────────
    "비정상적인 접근": {"action": "detect", "severity": "critical"},
    "자동화 프로그램": {"action": "detect", "severity": "critical"},
    "자동 프로그램": {"action": "detect", "severity": "critical"},
    "봇으로 판단": {"action": "detect", "severity": "critical"},
    "접근 차단": {"action": "detect", "severity": "high"},
    "이용이 제한": {"action": "detect", "severity": "high"},
    "서비스 차단": {"action": "detect", "severity": "high"},
    "Abnormal access": {"action": "detect", "severity": "critical"},
    "bot detected": {"action": "detect", "severity": "critical"},
}


class PopupEvent(TypedDict):
    ts_ms: int
    marker: str
    snippet: str
    frame_url: str


def build_watcher_js(markers: dict) -> str:
    """마커 카탈로그를 JS 코드 문자열로 변환."""
    marker_list = json.dumps([{"key": k} for k in markers])

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
        from scripts.browser.cdp.connection import (
            get_page,  # 2026-09-29 defect_index #39: scripts.browser.navigator.navigator 에는 get_page 가 없음(실제 정의는 web_connector, navigator_nav.py 가 이미 이렇게 씀)
        )

        page = get_page()

    js = build_watcher_js(POPUP_MARKERS)
    frame_count = 0
    for frame in page.frames:
        try:
            frame.evaluate(js)
            frame_count += 1
        except Exception as e:  # noqa: BLE001 - 브라우저 팝업 감지기 설치/조회/초기화 유틸(읽기전용) — 개별 프레임 주입/조회 실패는 로그 남기고 continue, 쓰기 없음
            _log.debug("[popup_watcher] 프레임 주입 실패: %s", e)
            continue

    _log.info("[popup_watcher] 감지기 설치 완료: %d프레임", frame_count)
    return {"installed": True, "frame_count": frame_count}


def poll_events(page=None, since_ms: int = 0) -> list[PopupEvent]:
    """window.__hh_popup_state.events에서 since_ms 이후 이벤트를 읽어온다."""
    if page is None:
        from scripts.browser.cdp.connection import (
            get_page,  # 2026-09-29 defect_index #39: scripts.browser.navigator.navigator 에는 get_page 가 없음(실제 정의는 web_connector, navigator_nav.py 가 이미 이렇게 씀)
        )

        page = get_page()

    for frame in page.frames:
        try:
            events = frame.evaluate("(s) => (window.__hh_popup_state?.events||[]).filter(e => e.ts_ms > s)", since_ms)
            if events:
                _log.debug("[popup_watcher] %d개 팝업 감지", len(events))
                return events
        except Exception as e:  # noqa: BLE001 - 브라우저 팝업 감지기 설치/조회/초기화 유틸(읽기전용) — 개별 프레임 주입/조회 실패는 로그 남기고 continue, 쓰기 없음
            _log.debug("[popup_watcher] 이벤트 조회 실패: %s", e)
            continue
    return []


def clear_events(page=None) -> None:
    """window.__hh_popup_state.events를 초기화한다."""
    if page is None:
        from scripts.browser.cdp.connection import (
            get_page,  # 2026-09-29 defect_index #39: scripts.browser.navigator.navigator 에는 get_page 가 없음(실제 정의는 web_connector, navigator_nav.py 가 이미 이렇게 씀)
        )

        page = get_page()

    for frame in page.frames:
        try:
            frame.evaluate("() => { window.__hh_popup_state.events = []; }")
        except Exception:  # noqa: BLE001 - 브라우저 팝업 감지기 설치/조회/초기화 유틸(읽기전용) — 개별 프레임 주입/조회 실패는 로그 남기고 continue, 쓰기 없음
            continue


def auto_handle(page=None) -> dict:
    """poll_events → 각 이벤트 처리 → clear_events."""
    if page is None:
        from scripts.browser.cdp.connection import (
            get_page,  # 2026-09-29 defect_index #39: scripts.browser.navigator.navigator 에는 get_page 가 없음(실제 정의는 web_connector, navigator_nav.py 가 이미 이렇게 씀)
        )

        page = get_page()

    handled = []
    skipped = []
    unknown = []

    events = poll_events(page=page)
    _log.info("[popup_watcher] 자동 처리 시작: %d개 이벤트", len(events))

    for ev in events:
        spec = POPUP_MARKERS.get(ev["marker"])
        if spec is None:
            unknown.append(ev)
            _log.warning("[popup_watcher] 미지의 팝업: %s", ev["marker"])
            continue
        if spec["action"] is None:
            skipped.append(ev)
            _log.debug("[popup_watcher] 팝업 스킵: %s", ev["marker"])
            continue
        if spec["action"] == "click_button":
            from scripts.browser.navigator.navigator import click_button

            _log.debug("[popup_watcher] 버튼 클릭 시도: %s", spec["target"])
            ok = click_button(spec["target"])
            handled.append({"event": ev, "clicked": ok})
            if ok:
                _log.info("[popup_watcher] 팝업 처리 완료: %s", ev["marker"])
            else:
                _log.warning("[popup_watcher] 팝업 처리 실패: %s", ev["marker"])

    if events:
        clear_events(page=page)

    _log.info("[popup_watcher] 처리 완료: 처리=%d, 스킵=%d, 미지=%d", len(handled), len(skipped), len(unknown))
    return {"handled": handled, "skipped": skipped, "unknown": unknown}

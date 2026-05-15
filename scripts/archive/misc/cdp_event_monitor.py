"""CDP 이벤트 상시 감시 — cdp_event_monitor v1.0

CDP WebSocket을 통해 모든 탭의 브라우저 이벤트를 실시간 구독하고
op_log / critical_logger 에 기록한다.

구독 이벤트:
  Page.frameNavigated        — 탭 URL 이동
  Page.loadEventFired        — 페이지 완전 로드
  Network.requestWillBeSent  — HTTP 요청 (문서 레벨만)
  Target.targetCreated       — 새 탭 생성
  Target.targetDestroyed     — 탭 닫힘
  Target.targetInfoChanged   — 탭 URL/타이틀 변경

통합 방법:
  from scripts.cdp_event_monitor import start_monitor, stop_monitor
  start_monitor()   # 백그라운드 스레드 시작
  stop_monitor()    # 중지
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]

from scripts.logger import get_logger
from scripts.op_log import log_op

_log = get_logger(__name__)

# ── 설정 ─────────────────────────────────────────────────────────────
POLL_TABS_INTERVAL = 5.0       # 새 탭 감지 주기(초)
RECONNECT_DELAY    = 3.0       # 연결 실패 후 재시도 대기(초)

# 노이즈 필터: 이 URL 패턴은 Network 요청 기록에서 제외
_SKIP_URL_PATTERNS = (
    "favicon.ico", "favicon.png",
    "google-analytics", "googletagmanager",
    "doubleclick.net", "googlesyndication",
    ".woff", ".woff2", ".ttf", ".eot",
    "chrome-extension://",
)

# 탭 URL 이 이것이면 기록 생략
_SKIP_TAB_URLS = {"about:blank", "chrome://newtab/", ""}

# 민감 도메인 → critical_logger 로도 기록
_CRITICAL_DOMAINS = {
    "mail.google.com", "mail.naver.com",
    "hanabank.com", "kbstar.com", "shinhan.com", "wooribank.com",
    "eum.cw.or.kr",
    "nts.go.kr", "hometax.go.kr",
    "4insure.or.kr", "nhis.or.kr",
}

_stop_event = threading.Event()
_monitor_thread: threading.Thread | None = None


# ── 헬퍼 ─────────────────────────────────────────────────────────────

def _get_cdp_port() -> int:
    try:
        from scripts.config import CDP_PORT as _p
    except Exception:
        _p = 9222
    try:
        state = json.loads((ROOT / "data" / "cdp_daemon_state.json").read_text())
        return int(state.get("cdp_port", _p))
    except Exception:
        return _p


def _get_cdp_host() -> str:
    try:
        from scripts.config import CDP_HOST as _host
        return _host
    except Exception:
        return "127.0.0.1"


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc
    except Exception:
        return ""


def _should_skip_network(url: str) -> bool:
    low = url.lower()
    return any(p in low for p in _SKIP_URL_PATTERNS)


def _is_critical_domain(url: str) -> bool:
    d = _domain(url)
    return any(d == cd or d.endswith("." + cd) for cd in _CRITICAL_DOMAINS)


# ── 탭별 WebSocket 핸들러 ─────────────────────────────────────────────

async def _handle_tab(ws_url: str, tab_id: str, tab_url: str) -> None:
    """단일 탭의 CDP 이벤트 구독 루프."""
    import websockets

    try:
        async with websockets.connect(ws_url, open_timeout=5,
                                      ping_interval=20, ping_timeout=10) as ws:
            _log.debug("[cdp_event] 탭 연결: %s", tab_url[:60])

            # 이벤트 활성화
            for cmd in [
                {"id": 1, "method": "Page.enable"},
                {"id": 2, "method": "Network.enable",
                 "params": {"maxResourceBufferSize": 0, "maxTotalBufferSize": 0}},
            ]:
                await ws.send(json.dumps(cmd))

            async for raw in ws:
                if _stop_event.is_set():
                    break
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue

                method = msg.get("method", "")
                params = msg.get("params", {})

                if method == "Page.frameNavigated":
                    frame = params.get("frame", {})
                    url = frame.get("url", "")
                    frame_type = frame.get("type", "")
                    if frame_type != "outermost_frame" or url in _SKIP_TAB_URLS:
                        continue
                    _log.info("[nav] %s", url[:100])
                    log_op("cdp_nav", ok=True, url=url[:200], tab_id=tab_id[:16])
                    if _is_critical_domain(url):
                        try:
                            from scripts.critical_logger import log_critical
                            log_critical("PORTAL_VISIT", f"페이지 이동: {url[:80]}",
                                         url=url[:200], domain=_domain(url))
                        except Exception:
                            pass

                elif method == "Page.loadEventFired":
                    pass  # frameNavigated 로 충분

                elif method == "Network.requestWillBeSent":
                    req = params.get("request", {})
                    req_url = req.get("url", "")
                    resource_type = params.get("type", "")
                    # 문서 레벨 요청만 (Document, XHR, Fetch)
                    if resource_type not in ("Document", "XHR", "Fetch"):
                        continue
                    if _should_skip_network(req_url):
                        continue
                    method_http = req.get("method", "GET")
                    _log.debug("[req] %s %s", method_http, req_url[:80])
                    if resource_type == "Document":
                        log_op("cdp_request", ok=True,
                               method=method_http, url=req_url[:200],
                               type=resource_type, tab_id=tab_id[:16])

    except Exception as e:
        if not _stop_event.is_set():
            _log.debug("[cdp_event] 탭 연결 종료 (%s): %s", tab_url[:40], e)


# ── 탭 목록 관리 ─────────────────────────────────────────────────────

async def _monitor_loop() -> None:
    """모든 탭 감시 루프 — 탭 추가/제거를 감지해 핸들러 태스크를 관리."""
    import requests as _req

    port = _get_cdp_port()
    active: dict[str, asyncio.Task] = {}  # tab_id → Task

    _log.info("[cdp_event_monitor] 시작 (port=%d)", port)
    log_op("cdp_event_monitor", ok=True, message="시작", port=port)

    while not _stop_event.is_set():
        try:
            resp = _req.get(f"http://{_get_cdp_host()}:{port}/json", timeout=3)
            tabs = resp.json()
        except Exception as e:
            _log.debug("[cdp_event_monitor] 탭 조회 실패: %s", e)
            await asyncio.sleep(RECONNECT_DELAY)
            continue

        current_ids = {
            t["id"]: t for t in tabs
            if t.get("type") == "page" and t.get("webSocketDebuggerUrl")
        }

        # 종료된 탭 정리
        for tid in list(active):
            if tid not in current_ids:
                task = active.pop(tid)
                task.cancel()
                _log.debug("[cdp_event_monitor] 탭 제거: %s", tid[:16])

        # 신규 탭 추가
        for tid, tab in current_ids.items():
            if tid not in active or active[tid].done():
                task = asyncio.create_task(
                    _handle_tab(tab["webSocketDebuggerUrl"], tid, tab.get("url", ""))
                )
                active[tid] = task
                _log.debug("[cdp_event_monitor] 탭 추가: %s", tab.get("url", "")[:60])

        await asyncio.sleep(POLL_TABS_INTERVAL)

    # 정리
    for task in active.values():
        task.cancel()
    _log.info("[cdp_event_monitor] 종료")
    log_op("cdp_event_monitor", ok=True, message="종료")


def _thread_target() -> None:
    """백그라운드 스레드 진입점 — 독립 이벤트 루프 실행."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_monitor_loop())
    finally:
        loop.close()


# ── 공개 API ─────────────────────────────────────────────────────────

def start_monitor() -> None:
    """CDP 이벤트 모니터 백그라운드 스레드 시작."""
    global _monitor_thread
    if _monitor_thread and _monitor_thread.is_alive():
        _log.debug("[cdp_event_monitor] 이미 실행 중")
        return
    _stop_event.clear()
    _monitor_thread = threading.Thread(
        target=_thread_target, name="cdp_event_monitor", daemon=True
    )
    _monitor_thread.start()
    _log.info("[cdp_event_monitor] 스레드 시작 완료")


def stop_monitor(timeout: float = 5.0) -> None:
    """CDP 이벤트 모니터 중지."""
    _stop_event.set()
    if _monitor_thread:
        _monitor_thread.join(timeout=timeout)
    _log.info("[cdp_event_monitor] 중지 완료")


if __name__ == "__main__":
    # 단독 실행 테스트
    start_monitor()
    try:
        print("CDP 이벤트 모니터 실행 중... Ctrl+C로 종료")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_monitor()

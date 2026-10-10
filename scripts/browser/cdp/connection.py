"""CDP 공유 연결 계층 — 연결/페이지 획득 전담(데몬·브라우저는 기동하지 않는다).

web_connector.py(scripts/browser/page/)에서 분리(S1-b, 2026-10-07). cdp_client.py
등 CDP 라이브러리가 "페이지 조작"(web_connector.py의 나머지)이 아니라 "연결"만
필요할 때 이 모듈을 쓴다 — cdp_client 가 scripts/browser/page 를 몰라도 되게
하기 위한 경계.

공개 API: run_on_browser_thread, get_context, open_page, get_page, close_page,
fit_viewport, get_screen_size.
"""

from __future__ import annotations

import concurrent.futures
import json
import sys
import threading
import time
from contextlib import suppress
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from ai_orchestrator.paths.runtime import data_dir
from scripts.browser.session.browser_task_session import BrowserTaskPolicy, mark_task_owned
from scripts.common.config import CDP_HOST as _DEFAULT_CDP_HOST
from scripts.common.config import CDP_PORT as _DEFAULT_CDP_PORT
from scripts.common.logger import get_logger

log = get_logger(__name__)

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
_DAEMON_STATE = data_dir() / "cdp_daemon_state.json"

# ── 브라우저 context 캐싱 ────────────────────────────────────────────
_BROWSER_CONTEXT_CACHE = None
_BROWSER_CACHE = None
_PLAYWRIGHT_INSTANCE = None  # sync_playwright()를 전역 보관 — GC 수거 방지

# get_page()가 매번 "마지막 탭"을 다시 고르면, 작업 도중 다른 탭이 새로 열릴 때마다
# (오글링크 미리보기, 영상 업로더 팝업, 글감 검색 패널 등) 그 새 탭으로 갈아타 버려서
# 사용자 눈에는 "다른 창이 갑자기 열린 것"처럼 보이는 문제가 있었다(2026-08-14).
# 한 번 고른 탭을 핀 고정해 재사용하고, 그 탭이 닫혔을 때만 다시 고른다.
_PINNED_PAGE = None

# ── Playwright(sync) 전용 단일 스레드 ─────────────────────────────────
# Playwright sync API 는 생성 스레드에서만 접근 가능. FastAPI sync 엔드포인트는
# 스레드풀(여러 스레드)에서 돌기 때문에, 모든 브라우저 작업을 단일 전용 스레드에서
# 실행해 "Cannot switch to a different thread" 를 방지한다.
_BROWSER_EXECUTOR = None
_BROWSER_EXECUTOR_LOCK = threading.Lock()


def run_on_browser_thread(fn, *args, timeout: float = 300, **kwargs):
    """Playwright(sync) 작업을 단일 전용 스레드에서 실행하고 결과를 반환.

    오케스트레이터/라우터(스레드풀)에서 브라우저를 만질 때 반드시 이 헬퍼를 통한다.
    fn 내부에서 get_page()/open_page() 등 playwright 호출을 수행하면, 항상 같은
    스레드에서 연결·사용되어 스레드 친화성 문제가 사라진다.
    """
    global _BROWSER_EXECUTOR
    with _BROWSER_EXECUTOR_LOCK:
        if _BROWSER_EXECUTOR is None:
            _BROWSER_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="browser")
    fut = _BROWSER_EXECUTOR.submit(fn, *args, **kwargs)
    return fut.result(timeout=timeout)


def _is_cdp_live(port: int) -> bool:
    """해당 포트에 CDP 브라우저가 이미 떠 있는지 빠르게 확인."""
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://{_DEFAULT_CDP_HOST}:{port}/json/version", timeout=2) as resp:
            return resp.status == 200
    except Exception:  # noqa: BLE001 - CDP 공유 연결 계층 — 연결 실패는 캐시 초기화 후 재시도, 종료 처리는 이미 닫히는 중이라 무시해도 안전(2026-09-28 검토)
        return False


class CdpNotRunningError(RuntimeError):
    """CDP 브라우저가 떠 있지 않다 — 라이브러리는 브라우저·데몬을 스스로 띄우지 않는다."""


def _get_cdp_port() -> int:
    """CDP 포트 결정. 이 함수는 어떤 프로세스도 기동하지 않는다(2026-10-08 대표님 지시: 자동 기동 제거).

    1순위: 기본 포트(9222)에 CDP 브라우저가 떠 있으면 그대로 사용.
    2순위: cdp_daemon_state.json 에 기록된 포트가 실제로 응답하면 사용.
    둘 다 아니면 CdpNotRunningError — 호출자가 명시적으로 기동한 뒤 다시 시도해야 한다.
    """
    if _is_cdp_live(_DEFAULT_CDP_PORT):
        return _DEFAULT_CDP_PORT
    try:
        state = json.loads(_DAEMON_STATE.read_text(encoding="utf-8"))
        port = int(state.get("cdp_port", _DEFAULT_CDP_PORT))
    except Exception:  # noqa: BLE001 - 상태 파일이 없거나 깨졌으면 "데몬 없음"과 같다 — 아래에서 명확한 오류로 알린다
        port = _DEFAULT_CDP_PORT
    if port != _DEFAULT_CDP_PORT and _is_cdp_live(port):
        return port
    raise CdpNotRunningError(
        f"CDP 브라우저가 실행 중이 아닙니다(포트 {_DEFAULT_CDP_PORT}). 자동으로 기동하지 않습니다 — "
        "'python scripts/browser/cdp/cdp_daemon.py start' 로 직접 시작하거나 Haehan AI 앱을 실행하세요."
    )


def _connect_browser():
    """CDP 브라우저에 연결해 (browser, context) 반환.

    context를 캐싱해서 여러 번 호출해도 같은 context를 반환합니다.
    """
    global _BROWSER_CONTEXT_CACHE, _BROWSER_CACHE

    # 캐시된 context가 있으면 살아있는지 확인 후 재사용
    if _BROWSER_CONTEXT_CACHE is not None:
        try:
            if _BROWSER_CACHE and _BROWSER_CACHE.is_connected():
                return _BROWSER_CACHE, _BROWSER_CONTEXT_CACHE
        except Exception:  # noqa: BLE001 - 탭 상태 확인/뷰포트 계산 등 보조 동작 — 실패해도 계속 진행(2026-09-28 검토)
            pass
        log.warning("[connection] 캐시된 브라우저 컨텍스트 스테일 — 재연결")
        # 이전 Playwright 인스턴스를 멈추지 않고 버리면, 그 내부 이벤트루프가 이 전용 스레드에 "실행 중"으로 남아
        # 이후의 모든 sync_playwright().start() 가 "Sync API inside the asyncio loop" 로 영구 실패한다
        # (2026-10-04 실측: 서버 시작 직후 연결이 낡아 재연결 → 사이트 지도 실행 500. 연결 실패 경로는 아래에서 이미 stop 한다).
        stale = _PLAYWRIGHT_INSTANCE
        if stale is not None:
            with suppress(Exception):
                stale.stop()
        globals()["_BROWSER_CACHE"] = None
        globals()["_BROWSER_CONTEXT_CACHE"] = None
        globals()["_PLAYWRIGHT_INSTANCE"] = None
    port = _get_cdp_port()
    log.debug("CDP 연결 시도: port=%s", port)

    p = sync_playwright().start()
    try:
        browser = p.chromium.connect_over_cdp(f"http://{_DEFAULT_CDP_HOST}:{port}")

        ctx = None
        for _ in range(10):
            if browser.contexts:
                ctx = browser.contexts[0]
                break
            time.sleep(1)

        if not ctx:
            log.error("CDP 브라우저 컨텍스트 생성 실패")
            raise RuntimeError("CDP 브라우저 컨텍스트 생성 실패")
    except Exception:
        # 2026-09-29 실측 확인한 심각한 버그 수정(defect_index 신규 항목): 여기서 p.stop()을
        # 안 하고 그냥 raise만 하면, sync_playwright().start()가 이미 만들어 둔 내부
        # 이벤트루프+그린렛 펌프가 이 전용 브라우저 스레드에 "실행 중"으로 영구히 남는다
        # (Playwright sync API는 asyncio.get_running_loop()가 성공하면 즉시
        # "Sync API inside the asyncio loop" 에러를 던짐 — 공식 소스 playwright/sync_api/
        # _context_manager.py PlaywrightContextManager.__enter__ 확인). CDP 브라우저가
        # 아주 잠깐이라도 안 떠 있던 순간에 이 경로를 한 번만 타면, 그 이후 이 스레드의
        # 모든 sync_playwright().start() 호출이 CDP 브라우저 상태와 무관하게 영구 실패한다
        # (실측: 최초 1회 clean → connect_over_cdp ECONNREFUSED → 이후 전부 오염 재현).
        with suppress(Exception):
            p.stop()
        globals()["_PLAYWRIGHT_INSTANCE"] = None
        raise

    globals()["_PLAYWRIGHT_INSTANCE"] = p  # GC 수거 방지 — 전역 보관 (연결 성공 후에만)

    # 캐싱 (전역 변수 업데이트)
    globals()["_BROWSER_CACHE"] = browser
    globals()["_BROWSER_CONTEXT_CACHE"] = ctx
    log.debug("브라우저 context 캐싱 완료")

    return browser, ctx


def get_screen_size() -> tuple[int, int]:
    """모니터 CSS 픽셀 해상도 감지 (DPI 스케일 적용).

    Windows DPI 스케일 팩터(예: 150% = 1.5)를 물리 해상도에 나눠
    로컬 Chrome과 동일한 CSS 픽셀 크기를 반환한다.
    반환값을 Playwright set_viewport_size()에 그대로 사용 가능.
    """
    try:
        import ctypes

        # DPI 인식 없이 GetSystemMetrics → 물리 픽셀
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        gdi32 = ctypes.windll.gdi32  # type: ignore[attr-defined]
        phys_w = user32.GetSystemMetrics(0)
        phys_h = user32.GetSystemMetrics(1)
        # 시스템 DPI → CSS 픽셀 스케일 계산 (96 dpi = 100%)
        hdc = user32.GetDC(0)
        dpi = gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
        user32.ReleaseDC(0, hdc)
        scale = dpi / 96.0
        css_w = int(phys_w / scale)
        css_h = int(phys_h / scale)
        if css_w > 0 and css_h > 0:
            log.debug("[viewport] 물리=%dx%d DPI=%d scale=%.2f CSS=%dx%d", phys_w, phys_h, dpi, scale, css_w, css_h)
            return css_w, css_h
    except Exception:  # noqa: BLE001 - 탭 상태 확인/뷰포트 계산 등 보조 동작 — 실패해도 계속 진행(2026-09-28 검토)
        pass
    import os

    try:
        w = int(os.environ.get("SCREEN_WIDTH", "0"))
        h = int(os.environ.get("SCREEN_HEIGHT", "0"))
        if w > 0 and h > 0:
            return w, h
    except ValueError:
        pass
    log.debug("[viewport] 화면 크기 감지 실패 — 기본값 1920x1080 사용")
    return 1920, 1080


def fit_viewport(page: Page) -> None:
    """페이지 뷰포트를 실제 모니터 해상도에 맞추고 창을 최대화 복원.

    CDP 연결 시 Playwright가 뷰포트를 설정하지 않는 문제 +
    AI Chrome 창이 최소화 상태일 때 렌더링이 달라지는 문제를 동시에 해결.
    get_page() / open_page() 호출 직후 자동 적용.
    """
    w, h = get_screen_size()
    try:
        page.set_viewport_size({"width": w, "height": h})
        log.debug("[viewport] 뷰포트 설정: %dx%d", w, h)
    except Exception as e:  # noqa: BLE001 - CDP 공유 연결 계층 — 뷰포트/창위치 설정 실패는 비치명적이라 로그만(2026-09-28 검토)
        log.warning("[viewport] set_viewport_size 실패: %s", e)

    # 창 위치·크기 고정 (매번 일정한 위치로 강제)
    # Chrome은 마지막 위치를 Preferences에 기억하고 재시작 시 복원하므로
    # setWindowBounds 로 연결마다 덮어써서 위치 고정.
    _FIX_LEFT, _FIX_TOP, _FIX_W, _FIX_H = 100, 50, 1440, 900
    try:
        cdp = page.context.new_cdp_session(page)
        win = cdp.send("Browser.getWindowForTarget", {})
        wid = win["windowId"]
        bounds = win.get("bounds", {})
        state = bounds.get("windowState", "normal")

        # 2026-09-29 실측 확인한 크래시 원인 수정(defect_index 신규 항목): fit_viewport()는
        # get_page()/open_page() 호출마다(하루 세션 내내 수백 회) 매번 새 CDP 세션으로
        # Browser.setWindowBounds(내부적으로 Windows SetWindowPos/USER32 호출)를 무조건
        # 재실행했다. Windows Application 이벤트 로그로 Chrome이 오늘 같은 날 반복 크래시
        # (Exception 0xc0000409 STATUS_STACK_BUFFER_OVERRUN, Faulting module USER32.dll,
        # 매번 동일 오프셋 0x8c3c1)한 걸 확인 — 이미 목표 위치/크기인데도 반복 호출하는 게
        # 유력한 유발 요인으로 추정돼, 이미 정확하면 호출 자체를 스킵한다(크래시 재현
        # 빈도로 검증 예정 — 100% 확증은 아니고 강한 정황 근거 기반의 완화 조치).
        if (
            state == "normal"
            and bounds.get("left") == _FIX_LEFT
            and bounds.get("top") == _FIX_TOP
            and bounds.get("width") == _FIX_W
            and bounds.get("height") == _FIX_H
        ):
            log.debug("[viewport] 창 위치 이미 정확함 — setWindowBounds 스킵")
            return

        # minimized 상태면 먼저 normal로 복귀 (minimized → 다른 상태 직접 전환 불가)
        if state == "minimized":
            cdp.send("Browser.setWindowBounds", {"windowId": wid, "bounds": {"windowState": "normal"}})
            time.sleep(0.2)

        # 항상 고정 위치·크기로 설정 (off-screen·위치 어긋남 방지)
        cdp.send(
            "Browser.setWindowBounds",
            {
                "windowId": wid,
                "bounds": {
                    "windowState": "normal",
                    "left": _FIX_LEFT,
                    "top": _FIX_TOP,
                    "width": _FIX_W,
                    "height": _FIX_H,
                },
            },
        )
        log.debug("[viewport] 창 위치 고정: %dx%d@%d,%d (이전 상태: %s)", _FIX_W, _FIX_H, _FIX_LEFT, _FIX_TOP, state)
    except Exception as e:  # noqa: BLE001 - CDP 공유 연결 계층 — 창위치 설정 실패는 비치명적이라 로그만, 종료 처리는 이미 닫히는 중이라 무시해도 안전(2026-09-28 검토)
        log.debug("[viewport] 창 위치 고정 생략: %s", e)


def get_context():
    """공유 CDP 연결의 BrowserContext를 반환(여러 탭을 동시에 다뤄야 하는 호출자용).

    2026-09-30 추가 — 팝업 관리처럼 ctx.pages 전체를 훑어 URL 패턴으로 활성 탭을
    고르는 코드(예: smartstore/popup.py)가 매 호출마다 독자적으로 sync_playwright()를
    새로 맺던 걸 이 공유 연결로 옮기기 위한 공개 진입점. open_page()/get_page()와
    동일한 캐시된 연결을 재사용 — 별도 연결을 새로 맺지 않는다.
    """
    _, ctx = _connect_browser()
    return ctx


def open_page(*, allow_new_tab: bool = False, reason: str | None = None) -> Page:
    """CDP 브라우저에 연결해 새 페이지 반환."""
    _, ctx = _connect_browser()
    if not allow_new_tab:
        active = [p for p in ctx.pages if p.url not in ("about:blank", "")]
        if active:
            page = active[-1]
            mark_task_owned(page, BrowserTaskPolicy(task_id="legacy-open-page"), owned=False)
            fit_viewport(page)
            log.debug("reused existing page: %s", page.url)
            return page
    if allow_new_tab and not reason:
        raise ValueError("allow_new_tab requires a reason")
    page = ctx.new_page()
    mark_task_owned(page, BrowserTaskPolicy(task_id=reason or "legacy-open-page"), owned=True)
    fit_viewport(page)
    log.debug("새 페이지 생성 완료")
    return page


def get_page() -> Page:
    """CDP 브라우저의 기존 탭을 재사용. 없으면 새 탭 생성.

    open_page()와 달리 매번 새 탭을 만들지 않는다.
    여러 단계에 걸쳐 같은 탭을 유지해야 할 때 사용.

    한 번 고른 탭을 _PINNED_PAGE로 고정해 재사용한다 — 매번 "마지막 탭"을
    다시 고르면 작업 도중 다른 탭이 새로 열릴 때(팝업/미리보기 등) 그쪽으로
    갈아타 버려서 "다른 창이 열렸다"고 오인되는 문제가 있었다(2026-08-14).
    """
    global _PINNED_PAGE
    for _attempt in range(2):
        try:
            _, ctx = _connect_browser()

            # 고정된 탭이 아직 살아있으면 그대로 재사용 (다른 탭이 새로 열려도 안 흔들림)
            if _PINNED_PAGE is not None:
                try:
                    still_open = _PINNED_PAGE in ctx.pages
                    _ = _PINNED_PAGE.url  # 닫힌 탭이면 여기서 예외
                except Exception:  # noqa: BLE001 - CDP 공유 연결 계층 — 연결 실패는 캐시 초기화 후 재시도(2026-09-28 검토)
                    still_open = False
                if still_open:
                    mark_task_owned(_PINNED_PAGE, BrowserTaskPolicy(task_id="get-page"), owned=False)
                    fit_viewport(_PINNED_PAGE)
                    log.debug("고정 탭 재사용: %s", _PINNED_PAGE.url)
                    return _PINNED_PAGE
                _PINNED_PAGE = None  # 닫혔음 — 아래에서 다시 고른다

            pages = ctx.pages
            # about:blank 가 아닌 기존 탭 우선 재사용
            active = [p for p in pages if p.url not in ("about:blank", "")]
            if active:
                page = active[-1]
                mark_task_owned(page, BrowserTaskPolicy(task_id="get-page"), owned=False)
                fit_viewport(page)
                log.debug("기존 탭 재사용: %s", page.url)
                _PINNED_PAGE = page
                return page
            # 탭이 없거나 모두 blank면 새 탭 생성
            page = ctx.new_page()
            mark_task_owned(page, BrowserTaskPolicy(task_id="get-page-fallback"), owned=True)
            fit_viewport(page)
            log.debug("새 페이지 생성 완료")
            _PINNED_PAGE = page
            return page
        except Exception as _e:
            if _attempt == 0:
                log.warning("[connection] get_page 실패 — 캐시 초기화 후 재시도: %s", _e)
                globals()["_BROWSER_CACHE"] = None
                globals()["_BROWSER_CONTEXT_CACHE"] = None
                _PINNED_PAGE = None
            else:
                raise
    raise AssertionError("get_page: range(2) 루프는 항상 return 하거나 raise 한다(도달 불가)")


def close_page(page: Page) -> None:
    """Close only pages owned by the current helper."""
    if not bool(getattr(page, "_haehan_task_owned_page", True)):
        log.debug("skip closing reused page: %s", getattr(page, "url", ""))
        return
    try:
        page.close()
        log.debug("page closed")
    except Exception as e:  # noqa: BLE001 - CDP 공유 연결 계층 — 종료 처리는 이미 닫히는 중이라 무시해도 안전(2026-09-28 검토)
        log.debug("ignore page close failure: %s", e)

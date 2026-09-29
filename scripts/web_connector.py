"""웹 접속 모듈 — CDP 브라우저 연결 전담.

모든 웹 자동화 스크립트의 브라우저 연결 진입점.

사용법:
    from scripts.web_connector import open_page, close_page, browser_session

    # 단건
    page = open_page(allow_new_tab=True, reason="manual-single")
    ...
    close_page(page)

    # 컨텍스트 매니저
    with browser_session() as page:
        page_goto(page, "https://...")
"""

from __future__ import annotations

import json
import time
from collections.abc import Generator
from contextlib import contextmanager, suppress
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
_DAEMON_STATE = ROOT / "data" / "cdp_daemon_state.json"

import sys  # noqa: E402

sys.path.insert(0, str(ROOT))
from scripts.browser_sandbox_gate import assert_browser_launch_allowed  # noqa: E402
from scripts.browser_task_session import (  # noqa: E402
    BrowserTaskPolicy,
    cleanup_task_pages,
    close_all_pages,
    get_or_create_task_page,
    mark_task_owned,
)
from scripts.config import CDP_HOST as _DEFAULT_CDP_HOST  # noqa: E402
from scripts.config import CDP_PORT as _DEFAULT_CDP_PORT  # noqa: E402
from scripts.logger import get_logger  # noqa: E402

log = get_logger(__name__)

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
import concurrent.futures  # noqa: E402
import threading  # noqa: E402

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


def _ensure_cdp_daemon() -> None:
    """CDP 데몬이 꺼져 있으면 앱 요청 시점에 자동 기동.

    PC 부팅 자동 시작 아님 — 앱/기능이 브라우저를 필요로 할 때만 실행.
    """
    if _DAEMON_STATE.exists():
        try:
            state = json.loads(_DAEMON_STATE.read_text(encoding="utf-8"))
            if state.get("running"):
                return  # 이미 실행 중
        except Exception:  # noqa: BLE001 - 탭 상태 확인/뷰포트 계산 등 보조 동작 — 실패해도 계속 진행(2026-09-28 검토)
            pass

    log.info("[web_connector] CDP 데몬 미실행 — 앱 요청으로 자동 기동")
    assert_browser_launch_allowed(component="scripts.web_connector", action="cdp_daemon_autostart")
    daemon_script = ROOT / "scripts" / "cdp_daemon.py"
    import subprocess
    import sys

    subprocess.Popen(
        [sys.executable, str(daemon_script), "start"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )
    # 데몬 준비 대기 (최대 15초)
    for _ in range(15):
        time.sleep(1)
        if _DAEMON_STATE.exists():
            try:
                state = json.loads(_DAEMON_STATE.read_text(encoding="utf-8"))
                if state.get("running"):
                    log.info("[web_connector] CDP 데몬 기동 완료")
                    return
            except Exception:  # noqa: BLE001 - 탭 상태 확인/뷰포트 계산 등 보조 동작 — 실패해도 계속 진행(2026-09-28 검토)
                pass
    raise RuntimeError("CDP 데몬 자동 기동 실패 — 수동으로 'python scripts/cdp_daemon.py start' 실행하세요")


def _is_cdp_live(port: int) -> bool:
    """해당 포트에 CDP 브라우저가 이미 떠 있는지 빠르게 확인."""
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://{_DEFAULT_CDP_HOST}:{port}/json/version", timeout=2) as resp:
            return resp.status == 200
    except Exception:  # noqa: BLE001 - CDP 브라우저 연결/탭 관리 공용 커넥터 — 연결 실패는 캐시 초기화 후 재시도, 뷰포트/창위치 설정 실패는 비치명적이라 로그만, 종료 처리는 이미 닫히는 중이라 무시해도 안전(2026-09-28 검토)
        return False


def _get_cdp_port() -> int:
    """CDP 포트 결정.

    1순위: 기본 포트(9222)에 앱 watchdog 브라우저가 이미 떠 있으면 그대로 사용
            (블로그·스마트스토어 도구와 동일 경로 — 데몬 불필요).
    2순위: cdp_daemon_state.json 기반 데몬 포트 (없으면 자동 기동).
    """
    if _is_cdp_live(_DEFAULT_CDP_PORT):
        log.debug("[web_connector] 기본 포트 %s CDP 활성 — 데몬 생략", _DEFAULT_CDP_PORT)
        return _DEFAULT_CDP_PORT
    _ensure_cdp_daemon()
    state = json.loads(_DAEMON_STATE.read_text(encoding="utf-8"))
    return state.get("cdp_port", _DEFAULT_CDP_PORT)


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
        log.warning("[web_connector] 캐시된 브라우저 컨텍스트 스테일 — 재연결")
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
    except Exception as e:  # noqa: BLE001 - CDP 브라우저 연결/탭 관리 공용 커넥터 — 연결 실패는 캐시 초기화 후 재시도, 뷰포트/창위치 설정 실패는 비치명적이라 로그만, 종료 처리는 이미 닫히는 중이라 무시해도 안전(2026-09-28 검토)
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
    except Exception as e:  # noqa: BLE001 - CDP 브라우저 연결/탭 관리 공용 커넥터 — 연결 실패는 캐시 초기화 후 재시도, 뷰포트/창위치 설정 실패는 비치명적이라 로그만, 종료 처리는 이미 닫히는 중이라 무시해도 안전(2026-09-28 검토)
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
                except Exception:  # noqa: BLE001 - CDP 브라우저 연결/탭 관리 공용 커넥터 — 연결 실패는 캐시 초기화 후 재시도, 뷰포트/창위치 설정 실패는 비치명적이라 로그만, 종료 처리는 이미 닫히는 중이라 무시해도 안전(2026-09-28 검토)
                    still_open = False
                if still_open:
                    mark_task_owned(_PINNED_PAGE, BrowserTaskPolicy(task_id="get-page"), owned=False)
                    fit_viewport(_PINNED_PAGE)
                    log.debug("고정 탭 재사용: %s", _PINNED_PAGE.url)
                    return _PINNED_PAGE
                _PINNED_PAGE = None  # 닫혔음 — 아래에서 새로 고른다

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
                log.warning("[web_connector] get_page 실패 — 캐시 초기화 후 재시도: %s", _e)
                globals()["_BROWSER_CACHE"] = None
                globals()["_BROWSER_CONTEXT_CACHE"] = None
                _PINNED_PAGE = None
            else:
                raise


def get_page_by_url(*patterns: str, create_url: str | None = None) -> Page:
    """Return an existing CDP page whose URL contains one of the patterns.

    This avoids mixing independent tabs such as EUM and Hiworks when both are
    open in the same browser context.
    """
    _, ctx = _connect_browser()
    needles = [p for p in patterns if p]
    for page in reversed(ctx.pages):
        url = page.url or ""
        if needles and any(needle in url for needle in needles):
            log.debug("URL matched page: %s", url)
            return page
    if create_url:
        page = ctx.new_page()
        mark_task_owned(page, BrowserTaskPolicy(task_id="get-page-by-url", start_url=create_url), owned=True)
        page.goto(create_url, timeout=30000)
        return page
    return get_page()


def _host_key(url: str) -> str:
    """URL에서 도메인 키 추출(www. 정규화). 예: https://www.naver.com/x → naver.com"""
    from urllib.parse import urlparse

    try:
        host = (urlparse(url).netloc or "").lower()
    except Exception:  # noqa: BLE001 - CDP 브라우저 연결/탭 관리 공용 커넥터 — 연결 실패는 캐시 초기화 후 재시도, 뷰포트/창위치 설정 실패는 비치명적이라 로그만, 종료 처리는 이미 닫히는 중이라 무시해도 안전(2026-09-28 검토)
        host = ""
    return host[4:] if host.startswith("www.") else host


def get_domain_page(url: str) -> Page:
    """동일 도메인은 하나의 탭만 — 같은 호스트 탭이 있으면 재사용, 없으면 새 탭.

    AI 브라우저 작업이 사이트를 열 때 같은 도메인 탭이 중복 생성되지 않게 한다.
    (예: 네이버를 두 번 열어도 네이버 탭은 1개. 스토어/EUM 등 다른 도메인은 각자 탭.)
    """
    _, ctx = _connect_browser()
    key = _host_key(url)
    if key:
        for page in ctx.pages:
            try:
                if _host_key(page.url or "") == key:
                    mark_task_owned(page, BrowserTaskPolicy(task_id="get-domain-page"), owned=False)
                    fit_viewport(page)
                    log.debug("동일 도메인 탭 재사용: %s", page.url)
                    return page
            except Exception:  # noqa: BLE001 - CDP 브라우저 연결/탭 관리 공용 커넥터 — 연결 실패는 캐시 초기화 후 재시도, 뷰포트/창위치 설정 실패는 비치명적이라 로그만, 종료 처리는 이미 닫히는 중이라 무시해도 안전(2026-09-28 검토)
                continue
    # 같은 도메인 탭 없음 → 새 탭(단, 빈 about:blank 탭이 있으면 그것을 사용)
    blank = next((p for p in ctx.pages if (p.url or "") in ("about:blank", "")), None)
    page = blank or ctx.new_page()
    mark_task_owned(page, BrowserTaskPolicy(task_id="get-domain-page", start_url=url), owned=True)
    fit_viewport(page)
    log.debug("동일 도메인 탭 없음 → 새 탭: %s", url)
    return page


def get_task_page(
    *,
    task_id: str,
    allowed_hosts: tuple[str, ...] = (),
    url_patterns: tuple[str, ...] = (),
    start_url: str | None = None,
    max_tabs: int = 1,
) -> Page:
    """Return the bounded tab for a task, creating at most one when needed."""
    _, ctx = _connect_browser()
    policy = BrowserTaskPolicy(
        task_id=task_id,
        allowed_hosts=allowed_hosts,
        url_patterns=url_patterns,
        start_url=start_url,
        max_tabs=max_tabs,
    )
    page = get_or_create_task_page(ctx, policy)
    fit_viewport(page)
    return page


def cleanup_task_tabs(
    *,
    task_id: str,
    allowed_hosts: tuple[str, ...] = (),
    url_patterns: tuple[str, ...] = (),
    keep_page: Page | None = None,
    max_tabs: int = 1,
) -> dict[str, int]:
    """Clean task-owned, duplicate, and blank tabs after a CDP task."""
    _, ctx = _connect_browser()
    policy = BrowserTaskPolicy(
        task_id=task_id,
        allowed_hosts=allowed_hosts,
        url_patterns=url_patterns,
        max_tabs=max_tabs,
    )
    return cleanup_task_pages(ctx, policy, keep_page=keep_page)


def close_page(page: Page) -> None:
    """Close only pages owned by the current helper."""
    if not bool(getattr(page, "_haehan_task_owned_page", True)):
        log.debug("skip closing reused page: %s", getattr(page, "url", ""))
        return
    try:
        page.close()
        log.debug("page closed")
    except Exception as e:  # noqa: BLE001 - CDP 브라우저 연결/탭 관리 공용 커넥터 — 연결 실패는 캐시 초기화 후 재시도, 뷰포트/창위치 설정 실패는 비치명적이라 로그만, 종료 처리는 이미 닫히는 중이라 무시해도 안전(2026-09-28 검토)
        log.debug("ignore page close failure: %s", e)


@contextmanager
def browser_session() -> Generator[Page, None, None]:
    """CDP 페이지를 컨텍스트 매니저로 제공.

    with browser_session() as page:
        page_goto(page, url)
    """
    page = open_page(allow_new_tab=True, reason="browser-session")
    try:
        yield page
    finally:
        close_page(page)


# ── Persistent Context (세션 저장/복원) ──────────────────────────────


@contextmanager
def browser_task_session(
    *,
    task_id: str,
    allowed_hosts: tuple[str, ...] = (),
    url_patterns: tuple[str, ...] = (),
    start_url: str | None = None,
    max_tabs: int = 1,
) -> Generator[Page, None, None]:
    """Yield one bounded task tab and clean task-owned tabs on exit."""
    page = get_task_page(
        task_id=task_id,
        allowed_hosts=allowed_hosts,
        url_patterns=url_patterns,
        start_url=start_url,
        max_tabs=max_tabs,
    )
    try:
        yield page
    finally:
        cleanup_task_tabs(
            task_id=task_id,
            allowed_hosts=allowed_hosts,
            url_patterns=url_patterns,
            keep_page=page,
            max_tabs=max_tabs,
        )


def shutdown_browser_session(*, close_browser: bool = False) -> dict[str, int | bool]:
    """Close every tab, and optionally close the cached CDP browser object."""
    global _BROWSER_CONTEXT_CACHE, _BROWSER_CACHE
    browser, ctx = _connect_browser()
    closed = close_all_pages(ctx)
    if close_browser:
        # 브라우저 종료 실패해도 계속 진행(2026-09-28 검토)
        with suppress(Exception):
            browser.close()
        _BROWSER_CONTEXT_CACHE = None
        _BROWSER_CACHE = None
    return {"closed_tabs": closed, "browser_closed": close_browser}


SESSION_BASE_DIR = ROOT / "data" / "browser_sessions"


def session_dir(name: str) -> Path:
    """세션 디렉터리 경로 반환."""
    return SESSION_BASE_DIR / name


@contextmanager
def persistent_session(
    name: str,
    headless: bool = False,
) -> Generator[tuple, None, None]:
    """세션을 유지하는 Playwright persistent context 제공.

    with persistent_session("ai_assistant") as (ctx, page):
        page.goto("https://www.naver.com/")

    - user_data_dir 기반으로 쿠키/세션 자동 저장/복원
    - 종료 시 storage_state 자동 저장
    """
    from playwright.sync_api import sync_playwright

    s_dir = session_dir(name)
    s_dir.mkdir(parents=True, exist_ok=True)
    storage_path = s_dir / "state.json"

    with sync_playwright() as p:
        assert_browser_launch_allowed(component="scripts.web_connector", action="playwright_persistent_context")
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(s_dir),
            headless=headless,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.new_page()
        log.debug("persistent_session 시작: name=%s headless=%s", name, headless)
        try:
            yield ctx, page
        finally:
            try:
                ctx.storage_state(path=str(storage_path))
                log.debug("세션 저장 완료: %s", storage_path)
            except Exception as e:  # noqa: BLE001 - CDP 브라우저 연결/탭 관리 공용 커넥터 — 연결 실패는 캐시 초기화 후 재시도, 뷰포트/창위치 설정 실패는 비치명적이라 로그만, 종료 처리는 이미 닫히는 중이라 무시해도 안전(2026-09-28 검토)
                log.debug("세션 저장 실패: %s", e)
            ctx.close()

"""시험 중 로컬 CDP 포트(9222) 접속 차단 가드 — 사용자의 로그인된 Chrome 보호.

127.0.0.1 / localhost / ::1 / 0.0.0.0 의 9222 로 가는 소켓 연결과 Playwright ``connect_over_cdp``
(endpoint 에 9222 포함) 를 기본으로 ``ConnectionRefusedError`` 로 막는다.
우회: 환경변수 ``HAEHAN_ALLOW_REAL_CDP=1``. 다른 포트(임시 가짜 서버)·외부 호스트는 원래 함수로 위임한다.
루트 ``conftest.py`` 의 autouse fixture 가 ``install_guard`` 를 부른다(tests/ 와 ai_orchestrator/tests/ 공통).
"""

from __future__ import annotations

import ipaddress
import os
import socket
from typing import Any

GUARDED_PORT = 9222
_INSTALLED_CONNECTS: list[Any] = []  # 이미 설치된 가드 래퍼(중복 설치 방지)
ALLOW_ENV = "HAEHAN_ALLOW_REAL_CDP"
_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0", "::ffff:127.0.0.1", "[::1]"})


def guard_enabled(environ: Any = None) -> bool:
    """우회 환경변수가 1 이 아니면 가드 활성."""
    env = os.environ if environ is None else environ
    return str(env.get(ALLOW_ENV, "")).strip() != "1"


def blocked_message(host: str = "127.0.0.1", port: int = GUARDED_PORT) -> str:
    return f"test guard: blocked connect to {host}:{port} (set {ALLOW_ENV}=1 to allow)"


def is_blocked_address(address: Any) -> bool:
    """(host, port[, ...]) 튜플이 로컬 9222 이면 True. 예상과 다른 타입은 False(위임)."""
    if not isinstance(address, tuple) or len(address) < 2:
        return False
    host, port = address[0], address[1]
    if isinstance(host, bytes):
        try:
            host = host.decode("ascii")
        except UnicodeDecodeError:
            return False
    if not isinstance(host, str):
        return False
    try:
        port_num = int(port)
    except (TypeError, ValueError):
        return False
    if port_num != GUARDED_PORT:
        return False
    name = host.strip().lower().split("%", 1)[0].strip("[]")
    if name in _LOCAL_HOSTS:
        return True
    try:  # asyncio 가 이름을 풀어 넘기는 127.x.x.x / ::1 / 0.0.0.0 형태
        ip = ipaddress.ip_address(name)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_unspecified


def is_blocked_endpoint(endpoint: Any) -> bool:
    return isinstance(endpoint, str) and str(GUARDED_PORT) in endpoint


def install_guard(monkeypatch: Any) -> None:
    """소켓·Playwright 가드를 monkeypatch 로 설치(시험이 끝나면 자동 원복)."""
    if not guard_enabled() or socket.socket.connect in _INSTALLED_CONNECTS:
        return
    orig_connect = socket.socket.connect
    orig_connect_ex = socket.socket.connect_ex
    orig_create = socket.create_connection

    def connect(self, address):
        if guard_enabled() and is_blocked_address(address):
            raise ConnectionRefusedError(blocked_message(address[0], GUARDED_PORT))
        return orig_connect(self, address)

    def connect_ex(self, address):
        if guard_enabled() and is_blocked_address(address):
            raise ConnectionRefusedError(blocked_message(address[0], GUARDED_PORT))
        return orig_connect_ex(self, address)

    def create_connection(address, *args, **kwargs):
        if guard_enabled() and is_blocked_address(address):
            raise ConnectionRefusedError(blocked_message(address[0], GUARDED_PORT))
        return orig_create(address, *args, **kwargs)

    _INSTALLED_CONNECTS.append(connect)
    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "create_connection", create_connection)
    _install_asyncio_guard(monkeypatch)
    _install_playwright_guard(monkeypatch)


def _install_asyncio_guard(monkeypatch: Any) -> None:
    """asyncio 는 Windows ProactorEventLoop 에서 ``socket.connect`` 대신 ConnectEx 를 써서 소켓 가드를 우회한다.

    (CPython Lib/asyncio/windows_events.py ``IocpProactor.connect`` → ``ov.ConnectEx``,
    proactor_events.py ``sock_connect`` → ``self._proactor.connect``). 그래서 ``sock_connect`` 와
    ``IocpProactor.connect`` 에서 주소를 직접 검사한다(``create_connection``/``open_connection`` 은 모두 ``sock_connect`` 를 거친다).
    """
    from asyncio import proactor_events, selector_events

    def wrap_async(orig):
        async def sock_connect(self, sock, address):
            if guard_enabled() and is_blocked_address(address):
                raise ConnectionRefusedError(blocked_message(address[0], GUARDED_PORT))
            return await orig(self, sock, address)

        return sock_connect

    for cls in (selector_events.BaseSelectorEventLoop, proactor_events.BaseProactorEventLoop):
        monkeypatch.setattr(cls, "sock_connect", wrap_async(cls.sock_connect))

    try:
        from asyncio import windows_events
    except ImportError:  # Windows 가 아닌 환경
        return
    iocp = windows_events.IocpProactor
    orig_iocp = iocp.connect

    def iocp_connect(self, conn, address):
        if guard_enabled() and is_blocked_address(address):
            raise ConnectionRefusedError(blocked_message(address[0], GUARDED_PORT))
        return orig_iocp(self, conn, address)

    monkeypatch.setattr(iocp, "connect", iocp_connect)


# 실제 9222 Chrome 에 접속/조작하는 시험(2026-10-05 정적 조사) — 기본 skip, HAEHAN_ALLOW_REAL_CDP=1 일 때만 실행.
# 키는 폴더 무관 "파일명::시험명"(tests/<기능>/ 이동 후에도 계속 매칭되도록 — B0-a).
SKIP_REASON = "실제 9222 Chrome 접속 시험 — HAEHAN_ALLOW_REAL_CDP=1 일 때만 실행(사용자 로그인 세션 보호)"
REAL_CDP_TESTS: dict[str, str] = {
    "test_cdp_playwright_smoke_20260607.py::test_playwright_connects_to_cdp": "connect_over_cdp(9222)",
    "test_cdp_playwright_smoke_20260607.py::test_cdp_status_endpoint_matches_reality": "urlopen 9222/json/version",
    "test_cdp_playwright_smoke_20260607.py::test_blog_tab_open_smoke": "connect_over_cdp + 새 탭 열기/닫기(blog.naver.com)",
    "test_naver_cafe_list_collector.py::test_create_isolated_cafe_target_creates_new_tab": "discover_sessions 9222-9233 /json",
    "test_naver_cafe_list_collector.py::test_background_runner_main_mode_returns_sections": "discover_sessions 9222-9233 /json",
    "test_naver_cafe_list_collector.py::test_background_runner_topic_search_mode_returns_attach_only_report": "discover_sessions 9222-9233 /json",
    "test_naver_cafe_list_collector.py::test_background_runner_joined_cafe_collect_returns_payload": "discover_sessions 9222-9233 /json",
    "test_naver_cafe_list_collector.py::test_background_runner_join_request_returns_payload": "discover_sessions 9222-9233 /json",
    "test_google_youtube_search.py::test_market_research_run_writes_json_and_markdown": "패치 대상 오류 -> 실제 search_videos 가 브라우저로 YouTube 검색",
    "test_gmail.py::test_list_inbox": "get_page() + mail.google.com 접속, page.close()",
    "test_gmail_direct.py::test_gmail_serial": "get_page() 실접속",
    "test_blog_agent.py::test_blog_exploration": "수동 시험(실브라우저)",
}


def _basename_key(nodeid: str) -> str:
    """nodeid(`<경로>/<파일>.py::<시험명>`)에서 폴더를 뺀 `<파일>.py::<시험명>` 키를 만든다."""
    path_part, _, rest = nodeid.partition("::")
    filename = path_part.rsplit("/", 1)[-1]
    return f"{filename}::{rest}" if rest else filename


def apply_real_cdp_skips(items: list, skip_marker: Any) -> int:
    """수집된 시험 중 REAL_CDP_TESTS 에 해당하는 것에 skip 마커를 붙이고 건수를 반환(우회 env 면 0)."""
    if not guard_enabled():
        return 0
    count = 0
    for item in items:
        nodeid = str(getattr(item, "nodeid", "")).replace("\\", "/")
        if _basename_key(nodeid) in REAL_CDP_TESTS:
            item.add_marker(skip_marker)
            count += 1
    return count


def _endpoint_from(args: tuple, kwargs: dict) -> Any:
    if args:
        return args[0]
    return kwargs.get("endpoint_url", kwargs.get("endpointURL"))


def _install_playwright_guard(monkeypatch: Any) -> None:
    try:
        from playwright.sync_api import BrowserType as SyncBrowserType
    except Exception:  # noqa: BLE001 - playwright 미설치 환경은 가드 생략
        SyncBrowserType = None
    try:
        from playwright.async_api import BrowserType as AsyncBrowserType
    except Exception:  # noqa: BLE001 - playwright 미설치 환경은 가드 생략
        AsyncBrowserType = None

    if SyncBrowserType is not None:
        orig_sync = SyncBrowserType.connect_over_cdp

        def sync_connect_over_cdp(self, *args, **kwargs):
            endpoint = _endpoint_from(args, kwargs)
            if guard_enabled() and is_blocked_endpoint(endpoint):
                raise ConnectionRefusedError(blocked_message())
            return orig_sync(self, *args, **kwargs)

        monkeypatch.setattr(SyncBrowserType, "connect_over_cdp", sync_connect_over_cdp)

    if AsyncBrowserType is not None:
        orig_async = AsyncBrowserType.connect_over_cdp

        async def async_connect_over_cdp(self, *args, **kwargs):
            endpoint = _endpoint_from(args, kwargs)
            if guard_enabled() and is_blocked_endpoint(endpoint):
                raise ConnectionRefusedError(blocked_message())
            return await orig_async(self, *args, **kwargs)

        monkeypatch.setattr(AsyncBrowserType, "connect_over_cdp", async_connect_over_cdp)

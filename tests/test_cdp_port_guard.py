"""tests/cdp_port_guard.py 가드 시험 — 실제 소켓은 한 번도 열지 않는다.

모든 시험은 가드를 설치하기 *전에* 접속 함수의 원본(socket·asyncio·Playwright)을 호출 기록만 하는 가짜로 먼저 교체한다.
가드가 막으면 가짜가 호출되지 않고(호출 기록 비어 있음), 위임되면 가짜가 호출된다. 그래서 가드가 고장나도 9222 에는 닿지 않는다.
"""

from __future__ import annotations

import socket
import sys
from asyncio import proactor_events, selector_events

import pytest

from tests import cdp_port_guard as guard


def _drive(coro):
    """이벤트 루프(=윈도우 socketpair 의 소켓 접속)를 만들지 않고 코루틴을 직접 끝까지 돌린다(가짜 원본은 중단되지 않음)."""
    try:
        coro.send(None)
    except StopIteration:
        return
    raise AssertionError("코루틴이 중단됨")


def _fake_sockets(monkeypatch, rec):
    def fake_connect(self, address):
        rec.append(("connect", address))

    def fake_connect_ex(self, address):
        rec.append(("connect_ex", address))
        return 0

    def fake_create(address, *a, **k):
        rec.append(("create_connection", address))

    monkeypatch.setattr(socket.socket, "connect", fake_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", fake_connect_ex)
    monkeypatch.setattr(socket, "create_connection", fake_create)


def _fake_asyncio(monkeypatch, rec):
    async def fake_sock_connect(self, sock, address):
        rec.append(("sock_connect", address))

    for cls in (selector_events.BaseSelectorEventLoop, proactor_events.BaseProactorEventLoop):
        monkeypatch.setattr(cls, "sock_connect", fake_sock_connect)
    if sys.platform == "win32":
        from asyncio import windows_events

        def fake_iocp(self, conn, address):
            rec.append(("iocp_connect", address))

        monkeypatch.setattr(windows_events.IocpProactor, "connect", fake_iocp)


def _fake_playwright(monkeypatch, rec):
    try:
        from playwright.async_api import BrowserType as AsyncBT
        from playwright.sync_api import BrowserType as SyncBT
    except ImportError:
        return

    def fake_sync(self, *a, **k):
        rec.append(("sync_cdp", a, k))

    async def fake_async(self, *a, **k):
        rec.append(("async_cdp", a, k))

    monkeypatch.setattr(SyncBT, "connect_over_cdp", fake_sync)
    monkeypatch.setattr(AsyncBT, "connect_over_cdp", fake_async)


@pytest.fixture
def calls(monkeypatch):
    """원본을 가짜로 교체(루트 autouse 가드 위에 덮어씀) → 가드 재설치. 기록 리스트를 돌려준다."""
    rec: list[tuple] = []
    _fake_sockets(monkeypatch, rec)
    _fake_asyncio(monkeypatch, rec)
    _fake_playwright(monkeypatch, rec)
    monkeypatch.delenv(guard.ALLOW_ENV, raising=False)
    guard.install_guard(monkeypatch)
    return rec


HOSTS = ["127.0.0.1", "localhost", "::1", "0.0.0.0", "127.0.0.2"]


@pytest.mark.parametrize("host", HOSTS)
def test_socket_paths_blocked_before_original(calls, host):
    s = socket.socket.__new__(socket.socket)
    with pytest.raises(ConnectionRefusedError, match="test guard: blocked connect to"):
        socket.socket.connect(s, (host, 9222))
    with pytest.raises(ConnectionRefusedError, match="test guard: blocked connect to"):
        socket.socket.connect_ex(s, (host, 9222))
    with pytest.raises(ConnectionRefusedError, match="test guard: blocked connect to"):
        socket.create_connection((host, 9222), timeout=0.2)
    assert calls == []


def test_ipv6_four_tuple_and_string_port_blocked(calls):
    with pytest.raises(ConnectionRefusedError, match=guard.ALLOW_ENV):
        socket.create_connection(("::1", 9222, 0, 0))
    assert guard.is_blocked_address(("LocalHost", "9222"))
    assert calls == []


def test_other_ports_and_hosts_delegate_to_fake_original(calls):
    s = socket.socket.__new__(socket.socket)
    socket.socket.connect(s, ("127.0.0.1", 9333))
    assert socket.socket.connect_ex(s, ("127.0.0.1", 18080)) == 0
    socket.create_connection(("example.com", 9222))
    assert [c[0] for c in calls] == ["connect", "connect_ex", "create_connection"]


def test_odd_address_types_not_blocked():
    assert not guard.is_blocked_address("127.0.0.1:9222")
    assert not guard.is_blocked_address(("127.0.0.1", "abc"))
    assert not guard.is_blocked_address((None, 9222))
    assert not guard.is_blocked_address(("127.0.0.1",))
    assert not guard.is_blocked_address(("10.0.0.5", 9222))


def test_env_override_leaves_original_untouched(monkeypatch):
    rec = []
    monkeypatch.setattr(socket.socket, "connect", lambda self, address: rec.append(address))
    before = socket.socket.connect
    monkeypatch.setenv(guard.ALLOW_ENV, "1")
    assert guard.guard_enabled() is False
    guard.install_guard(monkeypatch)
    assert socket.socket.connect is before
    socket.socket.connect(socket.socket.__new__(socket.socket), ("127.0.0.1", 9222))  # 가짜 원본만 호출
    assert rec == [("127.0.0.1", 9222)]
    monkeypatch.setenv(guard.ALLOW_ENV, "0")
    assert guard.guard_enabled() is True


def test_env_flip_after_install_disables_wrapper(calls, monkeypatch):
    monkeypatch.setenv(guard.ALLOW_ENV, "1")
    socket.socket.connect(socket.socket.__new__(socket.socket), ("127.0.0.1", 9222))
    assert calls == [("connect", ("127.0.0.1", 9222))]


@pytest.mark.parametrize("cls", [selector_events.BaseSelectorEventLoop, proactor_events.BaseProactorEventLoop])
def test_asyncio_sock_connect_blocked_and_delegated(calls, cls):
    async def run():
        with pytest.raises(ConnectionRefusedError, match="test guard"):
            await cls.sock_connect(object(), None, ("127.0.0.1", 9222))
        await cls.sock_connect(object(), None, ("127.0.0.1", 9333))

    _drive(run())
    assert calls == [("sock_connect", ("127.0.0.1", 9333))]


@pytest.mark.skipif(sys.platform != "win32", reason="IocpProactor 는 Windows 전용")
def test_iocp_proactor_connect_blocked_and_delegated(calls):
    from asyncio import windows_events

    with pytest.raises(ConnectionRefusedError, match="test guard"):
        windows_events.IocpProactor.connect(object(), None, ("::1", 9222, 0, 0))
    windows_events.IocpProactor.connect(object(), None, ("127.0.0.1", 9333))
    assert calls == [("iocp_connect", ("127.0.0.1", 9333))]


def test_playwright_sync_and_async_wrappers(calls):
    sync_api = pytest.importorskip("playwright.sync_api")
    async_api = pytest.importorskip("playwright.async_api")
    with pytest.raises(ConnectionRefusedError, match="test guard"):
        sync_api.BrowserType.connect_over_cdp(object(), "http://127.0.0.1:9222")
    with pytest.raises(ConnectionRefusedError, match="test guard"):
        sync_api.BrowserType.connect_over_cdp(object(), endpoint_url="http://localhost:9222/")
    sync_api.BrowserType.connect_over_cdp(object(), "http://127.0.0.1:9333")

    async def run():
        with pytest.raises(ConnectionRefusedError, match="test guard"):
            await async_api.BrowserType.connect_over_cdp(object(), "http://127.0.0.1:9222")
        await async_api.BrowserType.connect_over_cdp(object(), "http://127.0.0.1:9333")

    _drive(run())
    assert [c[0] for c in calls] == ["sync_cdp", "async_cdp"]


def test_real_cdp_skip_list_nodeids_exist():
    """skip 목록의 파일명::시험명 키가 실제 시험 함수로 존재하는지 — 파일을 실행하지 않고 ast 로만 확인.

    키가 폴더 무관(파일명 기준)이라 tests/ 아래 어디에 있어도 찾는다(B0-a: tests/<기능>/ 이동 대비)."""
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    assert guard.REAL_CDP_TESTS
    for key in guard.REAL_CDP_TESTS:
        filename, func = key.split("::")
        matches = list(root.rglob(filename))
        assert matches, f"{filename} 을 tests/ 아래에서 찾지 못함 ({key})"
        tree = ast.parse(matches[0].read_text(encoding="utf-8"))
        names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        assert func in names, key


def test_apply_real_cdp_skips_marks_only_listed(monkeypatch):
    class Item:
        def __init__(self, nodeid):
            self.nodeid = nodeid
            self.marks = []

        def add_marker(self, m):
            self.marks.append(m)

    listed = next(iter(guard.REAL_CDP_TESTS))
    # 폴더가 있어도(이동 후 nodeid 형태) 파일명::시험명만 보고 매칭되는지 확인.
    items = [Item(f"tests/some_feature_folder/{listed}"), Item("tests/other.py::test_x")]
    monkeypatch.delenv(guard.ALLOW_ENV, raising=False)
    assert guard.apply_real_cdp_skips(items, "M") == 1
    assert items[0].marks == ["M"]
    assert items[1].marks == []
    monkeypatch.setenv(guard.ALLOW_ENV, "1")
    assert guard.apply_real_cdp_skips(items, "M") == 0

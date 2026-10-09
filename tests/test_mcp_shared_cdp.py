"""MCP 서버가 도구마다 새 CDP 연결을 맺지 않고 공용 연결 하나를 쓰는지 검사 (이슈 #45, 기준서 2026-09-30_mcp_shared_cdp_connection.md).

mcp 패키지 버전이 환경마다 달라 mcp_server 를 import 하지 않고 소스 구조로 검사한다.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_SRC_PATH = Path("ai_orchestrator/server/mcp_server.py")
_SRC = _SRC_PATH.read_text(encoding="utf-8")
_TREE = ast.parse(_SRC)

# 공용 연결을 만드는 유일한 곳(연결 자체가 여기 한 곳에만 있어야 한다)
_ALLOWED_CONNECT_FUNCS = {"_cdp_browser"}


def _functions() -> dict[str, ast.FunctionDef]:
    return {n.name: n for n in ast.walk(_TREE) if isinstance(n, ast.FunctionDef)}


def _calls_in(fn: ast.FunctionDef, attr: str) -> int:
    return sum(
        1 for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == attr
    )


def test_connect_over_cdp_appears_only_in_the_shared_helper():
    assert len(_functions().items()) > 0, "검사 대상 함수가 0개 — 아래 assert 가 공허하게 통과한다"
    offenders = [
        name
        for name, fn in _functions().items()
        if name not in _ALLOWED_CONNECT_FUNCS and _calls_in(fn, "connect_over_cdp")
    ]
    assert offenders == [], f"도구 함수에서 새 CDP 연결을 맺고 있다: {offenders}"


def test_sync_playwright_context_manager_not_used_per_tool_call():
    """`with sync_playwright() as pw:` 를 도구 호출마다 열고 닫는 패턴은 없어야 한다."""
    assert re.search(r"with\s+sync_playwright\(\)\s+as", _SRC) is None


def test_shared_helper_exists_and_is_used_by_every_browser_tool():
    fns = _functions()
    assert "_cdp_browser" in fns
    users = {
        "_cdp_collect",
        "_open_seller_center",
        "_list_cafe_boards",
        "_add_cafe_board",
        "_auto_register_product",
        "_edit_product",
    }
    for name in users:
        body = ast.get_source_segment(_SRC, fns[name])
        assert "_cdp_browser(" in body or "_cdp_context(" in body, f"{name} 가 공용 연결을 쓰지 않는다"


def test_universal_page_reuses_the_same_shared_connection():
    """snapshot_page/act_on_page 도 같은 공용 연결을 쓴다(연결이 프로세스에 하나만 있어야 한다)."""
    body = ast.get_source_segment(_SRC, _functions()["_get_universal_page"])
    assert "_cdp_browser(" in body


def test_tools_do_not_grab_the_first_tab_of_the_users_browser():
    """`contexts[0].pages[0]`(사용자가 보던 첫 탭)을 덮어쓰지 않는다."""
    assert "pages[0]" not in "".join(
        ast.get_source_segment(_SRC, _functions()[n]) or "" for n in ("_cdp_collect", "_open_seller_center")
    )


# ── 공용 헬퍼 동작 (가짜 playwright 로) ─────────────────────────────────


class _FakeBrowser:
    def __init__(self, connected=True):
        self._connected = connected
        self.contexts = ["ctx"]

    def is_connected(self):
        return self._connected


class _FakePlaywright:
    def __init__(self, browsers):
        self.browsers = list(browsers)
        self.connect_calls = 0
        self.chromium = self

    def connect_over_cdp(self, url, **kw):
        self.connect_calls += 1
        return self.browsers.pop(0)


def _load_helper():
    """헬퍼 함수 소스만 잘라 격리 실행한다(mcp 패키지 import 회피)."""
    fn = _functions()["_cdp_browser"]
    ns: dict = {"_universal_browser": {}, "Any": object, "CDP_URL": "http://127.0.0.1:9222"}
    code = "from __future__ import annotations\n" + ast.get_source_segment(_SRC, fn)
    exec(compile(code, "helper", "exec"), ns)  # 테스트가 만든 소스 조각만 실행
    return ns


def test_helper_reuses_live_connection():
    ns = _load_helper()
    fake = _FakePlaywright([_FakeBrowser()])
    ns["_start_playwright"] = lambda: fake
    b1 = ns["_cdp_browser"]()
    b2 = ns["_cdp_browser"]()
    assert b1 is b2 and fake.connect_calls == 1


def test_helper_reconnects_when_connection_died():
    ns = _load_helper()
    dead, alive = _FakeBrowser(connected=False), _FakeBrowser()
    fake = _FakePlaywright([dead, alive])
    ns["_start_playwright"] = lambda: fake
    first = ns["_cdp_browser"]()
    assert first is dead
    dead._connected = False
    second = ns["_cdp_browser"]()
    assert second is alive and fake.connect_calls == 2

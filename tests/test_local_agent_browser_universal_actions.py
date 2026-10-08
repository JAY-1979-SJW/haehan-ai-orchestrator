"""scripts/browser/agent/universal_actions.py 회귀 테스트.

실기 CDP 검증(위키백과 실제 페이지, snapshot 785개 노드/click으로 실제 페이지 이동/
navigate 후 ref 무효화까지)은 2026-09-28 세션에서 직접 실행해 확인했다
(docs/specs/2026-09-28_cdp_universal_automation_and_mcp_trigger.md). 여기서는 CDP
프로토콜 응답을 흉내 낸 fake 세션으로, 실기로 매번 Chrome을 띄우지 않고도 회귀를 잡는다.
"""

from __future__ import annotations

from typing import Any

import pytest

from scripts.browser.agent import universal_actions as ua

AX_TREE_RESPONSE = {
    "nodes": [
        {
            "nodeId": "1",
            "role": {"type": "role", "value": "RootWebArea"},
            "name": {"type": "computedString", "value": "테스트 페이지"},
            "ignored": False,
            "backendDOMNodeId": 100,
            "childIds": ["2", "3", "4"],
        },
        {
            "nodeId": "2",
            "role": {"type": "role", "value": "button"},
            "name": {"type": "computedString", "value": "장바구니 담기"},
            "ignored": False,
            "backendDOMNodeId": 101,
            "childIds": [],
        },
        {
            "nodeId": "3",
            "role": {"type": "role", "value": "generic"},  # 구조적 wrapper — 제외 대상
            "name": {"type": "computedString", "value": "wrapper"},
            "ignored": False,
            "backendDOMNodeId": 102,
            "childIds": ["5"],
        },
        {
            "nodeId": "4",
            "role": {"type": "role", "value": "textbox"},
            "name": {"type": "computedString", "value": ""},  # 이름 없음 — 제외 대상
            "ignored": False,
            "backendDOMNodeId": 103,
            "childIds": [],
        },
        {
            "nodeId": "5",
            "role": {"type": "role", "value": "textbox"},
            "name": {"type": "computedString", "value": "검색어"},
            "value": {"type": "computedString", "value": "기존 값"},
            "ignored": False,
            "backendDOMNodeId": 104,
            "childIds": [],
        },
    ]
}


class FakeCDPSession:
    """page.context.new_cdp_session(page) 가 돌려주는 CDPSession 흉내."""

    def __init__(self, box_quad: list[float] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any] | None]] = []
        self.detached = False
        self._box_quad = box_quad or [10.0, 20.0, 110.0, 20.0, 110.0, 40.0, 10.0, 40.0]

    def send(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append((method, params))
        if method == "Accessibility.getFullAXTree":
            return AX_TREE_RESPONSE
        if method == "DOM.getBoxModel":
            return {"model": {"content": self._box_quad}}
        if method == "DOM.resolveNode":
            return {"object": {"objectId": "obj-1"}}
        return {}

    def detach(self) -> None:
        self.detached = True


class FakeContext:
    def __init__(self, session: FakeCDPSession) -> None:
        self._session = session

    def new_cdp_session(self, _page: Any) -> FakeCDPSession:
        return self._session


class FakeKeyboard:
    def __init__(self) -> None:
        self.presses: list[str] = []
        self.typed: list[str] = []

    def press(self, key: str) -> None:
        self.presses.append(key)

    def type(self, text: str) -> None:  # Playwright API 이름 그대로
        self.typed.append(text)


class FakePage:
    def __init__(self, session: FakeCDPSession | None = None) -> None:
        self.context = FakeContext(session or FakeCDPSession())
        self.keyboard = FakeKeyboard()
        self.url = "https://example.com/before"
        self.goto_calls: list[str] = []

    def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 30000) -> None:
        self.goto_calls.append(url)
        self.url = url

    def screenshot(self) -> bytes:
        return b"PNG-fake"


def test_snapshot_filters_structural_and_unnamed_nodes() -> None:
    page = FakePage()
    snap = ua.snapshot(page)

    names = [(n.role, n.name) for n in snap.nodes]
    assert ("button", "장바구니 담기") in names
    assert ("textbox", "검색어") in names
    # 구조적 wrapper(role=generic)와 이름 없는 textbox(role=textbox, name="")는 제외돼야 함
    assert not any(role == "generic" for role, _ in names)
    assert ("textbox", "") not in names
    # RootWebArea는 이름(페이지 제목)이 있어 남는다 — 실기 검증(wikipedia.org)에서도
    # 첫 노드가 항상 RootWebArea였고 문제 없었음(Claude가 role로 구분 가능)
    assert len(names) == 3


def test_snapshot_as_text_shows_ref_role_name() -> None:
    page = FakePage()
    snap = ua.snapshot(page)
    text = snap.as_text()
    assert '[e2] button "장바구니 담기"' in text
    assert "value=" in text  # 검색어 노드는 기존 값이 있음


def test_act_click_uses_box_center_and_dispatches_mouse_events() -> None:
    session = FakeCDPSession(box_quad=[0.0, 0.0, 100.0, 0.0, 100.0, 50.0, 0.0, 50.0])
    page = FakePage(session)
    snap = ua.snapshot(page)
    button_ref = next(n.ref for n in snap.nodes if n.role == "button")

    ua.act(page, button_ref, "click")

    mouse_events = [(m, p) for m, p in session.calls if m == "Input.dispatchMouseEvent"]
    ev_params = [p for _, p in mouse_events if p is not None]
    assert len(ev_params) == len(mouse_events)
    assert [p["type"] for p in ev_params] == ["mousePressed", "mouseReleased"]
    # 중심좌표 = (0+100+100+0)/4=50, (0+0+50+50)/4=25
    assert ev_params[0]["x"] == 50.0
    assert ev_params[0]["y"] == 25.0
    assert session.detached is True  # 세션 정리 확인


def test_act_fill_clears_then_types_via_playwright_keyboard() -> None:
    page = FakePage()
    snap = ua.snapshot(page)
    text_ref = next(n.ref for n in snap.nodes if n.role == "textbox")

    ua.act(page, text_ref, "fill", "새 검색어")

    assert page.keyboard.presses == ["Control+A", "Backspace"]
    assert page.keyboard.typed == ["새 검색어"]


def test_act_fill_without_value_raises() -> None:
    page = FakePage()
    snap = ua.snapshot(page)
    text_ref = next(n.ref for n in snap.nodes if n.role == "textbox")

    with pytest.raises(ua.UniversalActionError, match="value"):
        ua.act(page, text_ref, "fill")


def test_act_unknown_ref_raises() -> None:
    page = FakePage()
    ua.snapshot(page)

    with pytest.raises(ua.UniversalActionError, match="알 수 없는 ref"):
        ua.act(page, "e999", "click")


def test_act_unknown_action_raises() -> None:
    page = FakePage()
    snap = ua.snapshot(page)
    ref = snap.nodes[0].ref

    with pytest.raises(ua.UniversalActionError, match="알 수 없는 action"):
        ua.act(page, ref, "drag")


def test_navigate_invalidates_ref_registry() -> None:
    page = FakePage()
    snap = ua.snapshot(page)
    ref = snap.nodes[0].ref

    ua.navigate(page, "https://example.com/after")

    assert page.goto_calls == ["https://example.com/after"]
    with pytest.raises(ua.UniversalActionError, match="다시 호출"):
        ua.act(page, ref, "click")


def test_screenshot_delegates_to_page() -> None:
    page = FakePage()
    assert ua.screenshot(page) == b"PNG-fake"


def test_max_depth_limits_traversal() -> None:
    page = FakePage()
    # depth 0 = 루트(RootWebArea, depth=0)까지만 포함, 그 자식(button 등, depth=1)은 제외
    snap = ua.snapshot(page, max_depth=0)
    roles = {n.role for n in snap.nodes}
    assert roles == {"RootWebArea"}

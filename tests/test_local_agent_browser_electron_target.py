"""scripts/browser/agent/electron_target.py 회귀 테스트.

실기 검증(2026-09-28, 실행 중인 Electron 앱에 --remote-debugging-port=9333으로 접속해
admin-web webview snapshot 40개 노드/실제 클릭/스크린샷까지 확인)은
docs/specs/2026-09-28_cdp_universal_automation_and_mcp_trigger.md 참고. 여기서는
websocket 연결 없이 순수 로직(타겟 탐색, 세션 핸들 detach 계약)만 회귀로 잡는다.
"""

from __future__ import annotations

import pytest

from scripts.browser.agent import electron_target as et


def test_find_target_prefers_webview_over_page() -> None:
    targets = [
        {"type": "page", "url": "file:///shell.html"},
        {"type": "webview", "url": "http://127.0.0.1:3000/"},
    ]
    found = et._find_target(targets, "127.0.0.1:3000")
    assert found["type"] == "webview"


def test_find_target_falls_back_to_page_when_no_webview_matches() -> None:
    targets = [{"type": "page", "url": "http://127.0.0.1:3000/"}]
    found = et._find_target(targets, "127.0.0.1:3000")
    assert found["type"] == "page"


def test_find_target_raises_when_nothing_matches() -> None:
    targets = [{"type": "page", "url": "file:///shell.html"}]
    with pytest.raises(et.ElectronTargetError, match="못 찾음"):
        et._find_target(targets, "127.0.0.1:3000")


class _FakeRawSession:
    """_RawCDPSession 대역 — websocket 연결 없이 send()/close() 호출만 기록."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, dict | None]] = []
        self.closed = False

    def send(self, method: str, params: dict | None = None, timeout: float = 15.0) -> dict:
        self.sent.append((method, params))
        return {"ok": True}

    def close(self) -> None:
        self.closed = True


def test_cdp_session_handle_detach_does_not_close_shared_connection() -> None:
    """실기 검증 중 실제로 잡았던 버그의 회귀 테스트: universal_actions.py는 매
    snapshot()/act() 호출 끝에 cdp.detach()를 부르는데, 이게 진짜 websocket을 닫으면
    바로 다음 호출이 끊긴 연결에 쓰려다 실패했다(2026-09-28). new_cdp_session()이
    돌려주는 핸들의 detach()는 공유 연결을 끊지 않아야 한다."""
    fake = _FakeRawSession()
    handle = et._CDPSessionHandle(fake)  # type: ignore[arg-type]

    handle.send("Accessibility.getFullAXTree", {})
    handle.detach()

    assert fake.closed is False  # detach()가 진짜 연결을 안 끊었어야 함
    assert fake.sent == [("Accessibility.getFullAXTree", {})]

    # detach() 이후에도 같은 fake 세션으로 계속 통신 가능(공유 연결이므로)
    handle.send("DOM.resolveNode", {"backendNodeId": 1})
    assert len(fake.sent) == 2


def test_electron_target_page_new_cdp_session_shares_underlying_session() -> None:
    """여러 번 new_cdp_session()을 불러도(=snapshot 한 번, act 한 번) 같은 실제
    세션(websocket 연결)을 공유해야 한다 — 매번 새 연결을 만들면 안 됨."""
    page = et.ElectronTargetPage.__new__(et.ElectronTargetPage)  # __init__(websocket 연결) 건너뜀
    page._session = _FakeRawSession()  # type: ignore[assignment]
    page.url = "http://127.0.0.1:3000/"

    handle1 = page.new_cdp_session(page)
    handle2 = page.new_cdp_session(page)
    handle1.send("Page.enable")
    handle1.detach()
    handle2.send("Page.captureScreenshot", {"format": "png"})

    assert page._session.closed is False  # type: ignore[attr-defined]
    assert len(page._session.sent) == 2  # type: ignore[attr-defined]


def test_electron_target_page_close_closes_real_session() -> None:
    page = et.ElectronTargetPage.__new__(et.ElectronTargetPage)
    page._session = _FakeRawSession()  # type: ignore[assignment]
    page.url = "http://127.0.0.1:3000/"

    page.close()

    assert page._session.closed is True  # type: ignore[attr-defined]

"""BrowserAgent — 연결 전 페이지 접근 계약.

connect() 전에는 페이지가 없다. 예전엔 `'NoneType' object has no attribute 'goto'` 같은 영문 AttributeError 가 나왔고,
이제는 "연결되지 않음" 을 분명히 알리는 RuntimeError 를 낸다(액션 메서드는 기존처럼 ActionResult(ok=False) 로 반환).
브라우저는 실제로 띄우지 않는다 — 가짜 페이지 객체만 쓴다.
"""

from __future__ import annotations

import pytest

from scripts.browser.agent.agent import BrowserAgent


class _FakePage:
    url = "https://example.test/after"

    def __init__(self) -> None:
        self.visited: list[str] = []

    def goto(self, url: str, timeout: int = 0) -> None:
        self.visited.append(url)

    def wait_for_timeout(self, ms: int) -> None:
        pass

    def wait_for_load_state(self, *_a, **_k) -> None:
        pass

    def go_back(self) -> None:
        self.visited.append("<back>")


def test_page_before_connect_raises_clear_error():
    agent = BrowserAgent()
    with pytest.raises(RuntimeError, match="connect"):
        _ = agent.page


def test_go_before_connect_returns_failure_with_clear_message():
    agent = BrowserAgent()
    result = agent.go("https://example.test")
    assert result.ok is False
    assert "connect" in result.error
    assert "NoneType" not in result.error


def test_click_before_connect_returns_failure_with_clear_message():
    agent = BrowserAgent()
    result = agent.click("#x")
    assert result.ok is False
    assert "connect" in result.error


def test_page_after_connect_is_returned():
    agent = BrowserAgent()
    fake = _FakePage()
    agent._page = fake  # connect() 가 하는 일을 흉내 — 실제 브라우저 없이
    assert agent.page is fake


def test_go_uses_the_connected_page():
    agent = BrowserAgent()
    fake = _FakePage()
    agent._page = fake
    result = agent.go("https://example.test/a", wait=0)
    assert result.ok is True
    assert fake.visited == ["https://example.test/a"]

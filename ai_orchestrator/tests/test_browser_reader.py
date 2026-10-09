"""core.agent_runtime.browser.browser_reader 검증 (Stage 2 read-only 브라우저 페이지 읽기).

실제 외부 웹사이트 접속 금지. 실제 브라우저 실행 금지. 모든 테스트는 fake
Playwright 팩토리(아래 ``_FakePlaywrightContext``) 를 ``_playwright_factory``
로 주입하여 수행한다. Playwright 설치 여부와 무관하게 PASS 해야 한다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / ".." / ".."))


# ─── Fake Playwright 계층 ──────────────────────────────────────────────────
#
# 아래 fake 객체들은 Playwright 의 sync_api 인터페이스 중 browser_reader 가
# 실제로 사용하는 최소 메서드만 구현한다. 만약 browser_reader 가 실수로
# 금지된 상호작용 API (click/fill/type/press/select_option/set_input_files/
# screenshot/evaluate/cookies 등) 를 호출하면 ``_forbidden`` 가 호출되어
# 테스트가 실패하도록 한다.

_FORBIDDEN_METHODS = frozenset(
    {
        "click",
        "fill",
        "type",
        "press",
        "dblclick",
        "hover",
        "select_option",
        "set_input_files",
        "tap",
        "check",
        "uncheck",
        "drag_and_drop",
        "keyboard",
        "mouse",
        "touchscreen",
        "evaluate",
        "evaluate_handle",
        "screenshot",
        "pdf",
        "on",
        "expect_download",
        "expect_popup",
        "storage_state",
        "add_cookies",
        "cookies",
        "request",
        "send_keys",
    }
)


class _ForbiddenCall(AssertionError):
    """read-only 규약을 위반하는 fake 메서드가 호출됨."""


def _forbidden(name: str):
    def _raise(*_a, **_kw):
        raise _ForbiddenCall(f"forbidden read-only violation: {name} should not be called")

    return _raise


class _FakePage:
    def __init__(
        self,
        html: str,
        landed_url: str,
        title: str,
        log: list,
    ) -> None:
        self._html = html
        self._landed_url = landed_url
        self._title = title
        self._log = log

    @property
    def url(self) -> str:
        return self._landed_url

    def goto(self, url: str, wait_until: str | None = None, timeout: int | None = None):
        self._log.append(("goto", url, wait_until, timeout))
        return None

    def title(self) -> str:
        self._log.append(("title",))
        return self._title

    def content(self) -> str:
        self._log.append(("content",))
        return self._html

    def close(self) -> None:
        self._log.append(("page.close",))

    def __getattr__(self, name: str):
        if name in _FORBIDDEN_METHODS:
            return _forbidden(f"page.{name}")
        raise AttributeError(name)


class _FakeContext:
    def __init__(self, page: _FakePage, log: list) -> None:
        self._page = page
        self._log = log

    def new_page(self) -> _FakePage:
        self._log.append(("new_page",))
        return self._page

    def close(self) -> None:
        self._log.append(("context.close",))

    def __getattr__(self, name: str):
        if name in _FORBIDDEN_METHODS:
            return _forbidden(f"context.{name}")
        raise AttributeError(name)


class _FakeBrowser:
    def __init__(self, context: _FakeContext, log: list) -> None:
        self._context = context
        self._log = log

    def new_context(self, **kwargs) -> _FakeContext:
        self._log.append(("new_context", kwargs))
        return self._context

    def close(self) -> None:
        self._log.append(("browser.close",))

    def __getattr__(self, name: str):
        if name in _FORBIDDEN_METHODS:
            return _forbidden(f"browser.{name}")
        raise AttributeError(name)


class _FakeChromium:
    def __init__(self, browser: _FakeBrowser, log: list) -> None:
        self._browser = browser
        self._log = log

    def launch(self, headless: bool = True, **kwargs) -> _FakeBrowser:
        self._log.append(("launch", {"headless": headless, **kwargs}))
        return self._browser


class _FakePlaywright:
    def __init__(self, browser: _FakeBrowser, log: list) -> None:
        self.chromium = _FakeChromium(browser, log)


class _FakePlaywrightContext:
    def __init__(self, browser: _FakeBrowser, log: list) -> None:
        self._pw = _FakePlaywright(browser, log)
        self._log = log

    def __enter__(self) -> _FakePlaywright:
        self._log.append(("__enter__",))
        return self._pw

    def __exit__(self, *_args) -> None:
        self._log.append(("__exit__",))
        return None


def _make_fake_factory(
    *,
    html: str = "<html><head><title>Example</title></head><body><h1>Hi</h1></body></html>",
    landed_url: str = "https://example.com/home",
    title: str = "Example",
):
    log: list = []
    page = _FakePage(html, landed_url, title, log)
    context = _FakeContext(page, log)
    browser = _FakeBrowser(context, log)

    def factory():
        return _FakePlaywrightContext(browser, log)

    return factory, log


# ─── URL 안전성 ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/html,<h1>x</h1>",
        "about:blank",
        "chrome://settings",
        "edge://settings",
        "ftp://example.com/",
    ],
)
def test_open_url_blocks_dangerous_schemes(url: str) -> None:
    from core.agent_runtime.browser.browser_reader import open_url_readonly

    # 팩토리 호출조차 되면 안 됨 — 차단되더라도 fake 을 전달하지 않는다.
    r = open_url_readonly(url)
    assert r["ok"] is False
    assert r["error_code"] in {
        "URL_SCHEME_BLOCKED",
        "URL_NO_HOST",
        "URL_PARSE_FAILED",
    }


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "http://127.0.0.1/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
    ],
)
def test_open_url_blocks_private_network_by_default(url: str) -> None:
    from core.agent_runtime.browser.browser_reader import open_url_readonly

    r = open_url_readonly(url)
    assert r["ok"] is False
    assert r["error_code"] == "URL_HOST_BLOCKED"


def test_open_url_private_network_never_reaches_factory() -> None:
    """차단된 URL 은 팩토리까지 도달하지 않아야 한다."""
    from core.agent_runtime.browser.browser_reader import open_url_readonly

    factory, log = _make_fake_factory()
    r = open_url_readonly("http://127.0.0.1/", _playwright_factory=factory)
    assert r["ok"] is False
    assert log == []  # 브라우저 실행조차 되지 않음


# ─── Playwright 미설치 ─────────────────────────────────────────────────────


def test_browser_dependency_missing_returns_error_code() -> None:
    from core.agent_runtime.browser.browser_reader import (
        BrowserDependencyMissing,
        open_url_readonly,
    )

    def bad_factory():
        raise BrowserDependencyMissing("playwright not installed")

    r = open_url_readonly(
        "https://example.com/",
        _playwright_factory=bad_factory,
    )
    assert r["ok"] is False
    assert r["error_code"] == "BROWSER_DEPENDENCY_MISSING"
    assert "playwright" in r["reason"].lower()


# ─── 기본 수집 ─────────────────────────────────────────────────────────────


def test_basic_title_current_url_and_content_collected() -> None:
    from core.agent_runtime.browser.browser_reader import open_url_readonly

    factory, log = _make_fake_factory(
        html="<html><head><title>Home</title></head><body><h1>Hi</h1><a href='/x'>x</a></body></html>",
        landed_url="https://example.com/home",
        title="Home",
    )
    r = open_url_readonly(
        "https://example.com/",
        _playwright_factory=factory,
    )
    assert r["ok"] is True
    assert r["title"] == "Home"
    assert r["current_url"] == "https://example.com/home"
    assert r["html_truncated"] is False
    # summary 는 title + counts 포함
    assert "title=Home" in r["summary"]
    # goto 한 번만 호출
    gotos = [e for e in log if isinstance(e, tuple) and e and e[0] == "goto"]
    assert len(gotos) == 1
    launches = [e for e in log if isinstance(e, tuple) and e and e[0] == "launch"]
    assert launches[-1][1]["headless"] is True


def test_visible_browser_option_launches_headed() -> None:
    from core.agent_runtime.browser.browser_reader import open_url_readonly

    factory, log = _make_fake_factory()
    r = open_url_readonly(
        "https://example.com/",
        headless=False,
        keep_open_ms=0,
        _playwright_factory=factory,
    )
    assert r["ok"] is True
    assert r["headless"] is False
    assert r["keep_open_ms"] == 0
    launches = [e for e in log if isinstance(e, tuple) and e and e[0] == "launch"]
    assert launches[-1][1]["headless"] is False


def test_browser_channel_option_uses_real_browser_channel() -> None:
    from core.agent_runtime.browser.browser_reader import open_url_readonly

    factory, log = _make_fake_factory()
    r = open_url_readonly(
        "https://example.com/",
        headless=False,
        browser_channel="chrome",
        _playwright_factory=factory,
    )
    assert r["ok"] is True
    assert r["browser_channel"] == "chrome"
    launches = [e for e in log if isinstance(e, tuple) and e and e[0] == "launch"]
    assert launches[-1][1]["channel"] == "chrome"


def test_analyze_html_structure_is_wired_in() -> None:
    from core.agent_runtime.browser.browser_reader import open_url_readonly

    factory, _log = _make_fake_factory(
        html=(
            "<html><head><title>T</title></head><body>"
            "<h1>Head</h1><a href='/a'>A</a><a href='/b'>B</a>"
            "<button>조회</button>"
            "<form method='get'><input name='q'></form>"
            "</body></html>"
        ),
        landed_url="https://example.com/",
        title="T",
    )
    r = open_url_readonly(
        "https://example.com/",
        _playwright_factory=factory,
    )
    assert r["ok"] is True
    struct = r["page_structure"]
    assert struct["ok"] is True
    counts = struct["counts"]
    assert counts["links"] == 2
    assert counts["buttons"] == 1
    assert counts["forms"] == 1


def test_html_length_truncation() -> None:
    from core.agent_runtime.browser.browser_reader import open_url_readonly

    big_html = "<html><body>" + ("A" * 2000) + "</body></html>"
    factory, _log = _make_fake_factory(
        html=big_html,
        landed_url="https://example.com/",
        title="T",
    )
    r = open_url_readonly(
        "https://example.com/",
        max_html_chars=100,
        _playwright_factory=factory,
    )
    assert r["ok"] is True
    assert r["html_truncated"] is True


# ─── 로그인 필요 추정 ──────────────────────────────────────────────────────


def test_login_password_input_detected() -> None:
    from core.agent_runtime.browser.browser_reader import open_url_readonly

    html = "<html><body><form><input name='user' type='text'><input name='pw' type='password'></form></body></html>"
    factory, _log = _make_fake_factory(
        html=html,
        landed_url="https://example.com/login",
        title="",
    )
    r = open_url_readonly(
        "https://example.com/",
        _playwright_factory=factory,
    )
    assert r["ok"] is True
    assert r["login_required_hint"] is True
    assert "password_input_detected" in r["login_reason"]


def test_login_keyword_detected() -> None:
    from core.agent_runtime.browser.browser_reader import open_url_readonly

    html = "<html><head><title>회원 로그인</title></head><body><h1>로그인</h1></body></html>"
    factory, _log = _make_fake_factory(
        html=html,
        landed_url="https://example.com/",
        title="회원 로그인",
    )
    r = open_url_readonly(
        "https://example.com/",
        _playwright_factory=factory,
    )
    assert r["ok"] is True
    assert r["login_required_hint"] is True
    assert "login_keyword" in r["login_reason"]


def test_no_login_detection_for_plain_page() -> None:
    from core.agent_runtime.browser.browser_reader import open_url_readonly

    html = "<html><body><h1>Welcome</h1><p>Hello</p></body></html>"
    factory, _log = _make_fake_factory(
        html=html,
        landed_url="https://example.com/",
        title="Welcome",
    )
    r = open_url_readonly(
        "https://example.com/",
        _playwright_factory=factory,
    )
    assert r["ok"] is True
    assert r["login_required_hint"] is False
    assert r["login_reason"] == []


# ─── 모달 후보 ────────────────────────────────────────────────────────────


def test_modal_candidates_detected() -> None:
    from core.agent_runtime.browser.browser_reader import open_url_readonly

    html = (
        "<html><body>"
        "<div role='dialog'><h2>공지</h2></div>"
        "<div class='popup-layer'></div>"
        "<div id='modal-announce'></div>"
        "<button>닫기</button>"
        "</body></html>"
    )
    factory, _log = _make_fake_factory(
        html=html,
        landed_url="https://example.com/",
        title="",
    )
    r = open_url_readonly(
        "https://example.com/",
        _playwright_factory=factory,
    )
    assert r["ok"] is True
    reasons = {c["reason"] for c in r["modal_candidates"]}
    assert "role_dialog" in reasons
    assert (
        any(reason.startswith("class_or_id:popup") for reason in reasons)
        or any(reason.startswith("class_or_id:modal") for reason in reasons)
        or any(reason.startswith("class_or_id:layer") for reason in reasons)
    )
    assert any(r_.startswith("close_button:") for r_ in reasons)


def test_modal_detection_handles_empty_html() -> None:
    from core.agent_runtime.browser.browser_reader import open_url_readonly

    factory, _log = _make_fake_factory(
        html="",
        landed_url="https://example.com/",
        title="",
    )
    r = open_url_readonly(
        "https://example.com/",
        _playwright_factory=factory,
    )
    assert r["ok"] is True
    assert r["modal_candidates"] == []


# ─── 민감정보 미포함 ──────────────────────────────────────────────────────


def test_result_contains_no_sensitive_tokens_or_full_html() -> None:
    from core.agent_runtime.browser.browser_reader import open_url_readonly

    unique_marker = "UNIQUE_BODY_MARKER_ABCDEF_12345"
    html = (
        "<html><head>"
        "<meta name='csrf-token' content='CSRF_SECRET_AAA'>"
        "</head><body>"
        f"<p>{unique_marker}</p>"
        "<form>"
        "<input name='pw' type='password' value='TOP_SECRET_PW_9999'>"
        "<input name='authorization' type='hidden' value='Bearer XYZ_TOKEN'>"
        "<input name='session_id' type='hidden' value='SESSION_DEADBEEF'>"
        "</form>"
        "</body></html>"
    )
    factory, _log = _make_fake_factory(
        html=html,
        landed_url="https://example.com/",
        title="",
    )
    r = open_url_readonly(
        "https://example.com/",
        _playwright_factory=factory,
    )
    s = json.dumps(r, ensure_ascii=False)
    for leak in (
        unique_marker,  # body 원문이 그대로 들어가지 않음
        "TOP_SECRET_PW_9999",
        "Bearer XYZ_TOKEN",
        "SESSION_DEADBEEF",
        "CSRF_SECRET_AAA",
    ):
        assert leak not in s, f"sensitive/raw token leaked: {leak!r}"

    # 결과 dict 에 raw html 키 자체가 없음
    assert "html" not in r


# ─── close 체인 ─────────────────────────────────────────────────────────────


def test_page_context_browser_all_closed() -> None:
    from core.agent_runtime.browser.browser_reader import open_url_readonly

    factory, log = _make_fake_factory()
    r = open_url_readonly(
        "https://example.com/",
        _playwright_factory=factory,
    )
    assert r["ok"] is True
    names = [e[0] for e in log if isinstance(e, tuple)]
    assert "page.close" in names
    assert "context.close" in names
    assert "browser.close" in names
    # close 순서: page → context → browser
    order = [n for n in names if n.endswith(".close")]
    assert order == ["page.close", "context.close", "browser.close"]


def test_close_chain_called_even_on_goto_failure() -> None:
    """goto 가 예외를 던져도 close 3종이 모두 호출된다."""
    from core.agent_runtime.browser.browser_reader import open_url_readonly

    factory, log = _make_fake_factory()
    # goto 를 강제로 실패시킨다 — 페이지 객체는 같은 log 를 공유하므로
    # 실행 후 close 흔적이 남아야 한다.
    original = log[:]  # noqa: F841
    # _FakePage 의 goto 를 monkeypatch
    # (컨텍스트 매니저를 통해 factory 내부 page 에 접근)
    # 직접 접근을 위해 fake 체인을 수동 구성한다.
    fail_log: list = []
    page = _FakePage(
        "<html></html>",
        "https://example.com/",
        "T",
        fail_log,
    )

    def _goto_fail(*_a, **_kw):
        fail_log.append(("goto.fail",))
        raise RuntimeError("synthetic goto failure")

    page.goto = _goto_fail  # type: ignore
    context = _FakeContext(page, fail_log)
    browser = _FakeBrowser(context, fail_log)

    def fail_factory():
        return _FakePlaywrightContext(browser, fail_log)

    r = open_url_readonly(
        "https://example.com/",
        _playwright_factory=fail_factory,
    )
    assert r["ok"] is False
    assert r["error_code"] == "BROWSER_OPEN_FAILED"
    names = [e[0] for e in fail_log if isinstance(e, tuple)]
    assert "page.close" in names
    assert "context.close" in names
    assert "browser.close" in names


# ─── 금지 API 미호출 ─────────────────────────────────────────────────────


def test_no_forbidden_interaction_methods_invoked_on_fakes() -> None:
    """fake 객체는 read-only 위반 API 가 호출되면 예외를 던진다.

    기본 실행 경로가 성공적으로 완료된다는 것 자체가 클릭/입력/제출/쿠키
    수집 등 위반 API 를 호출하지 않았다는 강한 증거이다.
    """
    from core.agent_runtime.browser.browser_reader import open_url_readonly

    factory, _log = _make_fake_factory(
        html="<html><body><form><input type='password'></form></body></html>",
        landed_url="https://example.com/",
        title="",
    )
    r = open_url_readonly(
        "https://example.com/",
        _playwright_factory=factory,
    )
    assert r["ok"] is True  # 위반이 있었다면 _ForbiddenCall 이 터졌을 것


def test_browser_reader_source_has_no_mutating_calls() -> None:
    """browser_reader.py 에 read-only 위반 API 호출 패턴이 실제로 없어야 한다."""
    from pathlib import Path

    import core.agent_runtime.browser.browser_reader as br

    src = Path(br.__file__).read_text(encoding="utf-8")

    # NOTE: 아래 토큰들은 read-only 위반이 될 수 있는 API 호출 패턴이다.
    # 이 테스트는 production code 에 이런 호출이 남아있지 않은지 정적으로 검증한다.
    forbidden_patterns = [
        ".click(",
        ".fill(",
        ".type(",
        ".press(",
        "select_option",
        "set_input_files",
        "storage_state",
        "add_cookies",
        "page.evaluate",
        "expect_download",
        "save_as",
        "send_keys",
    ]
    for token in forbidden_patterns:
        assert token not in src, f"{token!r} found in browser_reader.py"


# ─── action 통합 ──────────────────────────────────────────────────────────


def test_action_web_open_url_readonly_happy_path(monkeypatch) -> None:
    from core.agent_runtime.browser import browser_reader
    from core.agent_runtime.connection.actions import execute_action

    captured: list[dict] = []

    def fake_open(**kwargs):
        captured.append(dict(kwargs))
        return {
            "ok": True,
            "url": kwargs.get("url"),
            "current_url": "https://example.com/home",
            "title": "Home",
            "html_truncated": False,
            "login_required_hint": False,
            "login_reason": [],
            "modal_candidates": [],
            "page_structure": {
                "ok": True,
                "counts": {
                    "headings": 0,
                    "links": 0,
                    "buttons": 0,
                    "inputs": 0,
                    "forms": 0,
                    "tables": 0,
                },
            },
            "summary": "title=Home links=0 buttons=0 forms=0 tables=0",
        }

    monkeypatch.setattr(browser_reader, "open_url_readonly", fake_open)

    r = execute_action(
        "web_open_url_readonly",
        {"url": "https://example.com/", "keyword_hints": ["기성"]},
    )
    assert r.success is True
    assert r.data["title"] == "Home"
    assert r.data["current_url"] == "https://example.com/home"
    assert r.data["login_required_hint"] is False
    assert "page_structure" in r.data
    # HTML 원문은 반환 data 에 없음
    assert "html" not in r.data
    # 단 한 번 호출, url 전달
    assert len(captured) == 1
    assert captured[0]["url"] == "https://example.com/"
    assert captured[0]["headless"] is False


def test_action_default_allow_private_network_false(monkeypatch) -> None:
    from core.agent_runtime.browser import browser_reader
    from core.agent_runtime.connection.actions import execute_action

    captured: list[dict] = []

    def fake_open(**kwargs):
        captured.append(dict(kwargs))
        return {
            "ok": True,
            "url": kwargs.get("url"),
            "current_url": "",
            "title": "",
            "html_truncated": False,
            "login_required_hint": False,
            "login_reason": [],
            "modal_candidates": [],
            "page_structure": {"ok": True, "counts": {}},
            "summary": "",
        }

    monkeypatch.setattr(browser_reader, "open_url_readonly", fake_open)

    execute_action(
        "web_open_url_readonly",
        {"url": "https://example.com/"},
    )
    assert captured, "factory was never called"
    assert captured[0]["allow_private_network"] is False
    assert captured[0]["headless"] is False


def test_action_web_open_url_readonly_background_requires_approval(monkeypatch) -> None:
    from core.agent_runtime.browser import browser_reader
    from core.agent_runtime.connection.actions import execute_action

    def fake_open(**_kwargs):
        raise AssertionError("browser should not open without background approval")

    monkeypatch.setattr(browser_reader, "open_url_readonly", fake_open)

    r = execute_action(
        "web_open_url_readonly",
        {"url": "https://example.com/", "headless": True},
    )
    assert r.success is False
    assert r.error_code == "BACKGROUND_NOT_APPROVED"


def test_action_web_open_url_readonly_background_with_approval(monkeypatch) -> None:
    from core.agent_runtime.browser import browser_reader
    from core.agent_runtime.connection.actions import execute_action

    captured: list[dict] = []

    def fake_open(**kwargs):
        captured.append(dict(kwargs))
        return {
            "ok": True,
            "url": kwargs.get("url"),
            "current_url": "https://example.com/",
            "title": "Home",
            "html_truncated": False,
            "headless": kwargs.get("headless"),
            "login_required_hint": False,
            "login_reason": [],
            "modal_candidates": [],
            "page_structure": {"ok": True, "counts": {}},
            "summary": "title=Home links=0 buttons=0 forms=0 tables=0",
        }

    monkeypatch.setattr(browser_reader, "open_url_readonly", fake_open)

    r = execute_action(
        "web_open_url_readonly",
        {
            "url": "https://example.com/",
            "headless": True,
            "background_approved": True,
        },
    )
    assert r.success is True
    assert captured[0]["headless"] is True
    assert r.data["background_approved"] is True


def test_action_web_open_url_readonly_missing_url() -> None:
    from core.agent_runtime.connection.actions import execute_action

    r = execute_action("web_open_url_readonly", {})
    assert r.success is False
    assert r.error_code == "MISSING_URL"


def test_action_web_open_url_readonly_propagates_error_code(monkeypatch) -> None:
    from core.agent_runtime.browser import browser_reader
    from core.agent_runtime.connection.actions import execute_action

    def fake_open(**_kwargs):
        return {
            "ok": False,
            "url": "http://127.0.0.1/",
            "error_code": "URL_HOST_BLOCKED",
            "reason": "blocked",
        }

    monkeypatch.setattr(browser_reader, "open_url_readonly", fake_open)

    r = execute_action(
        "web_open_url_readonly",
        {"url": "http://127.0.0.1/"},
    )
    assert r.success is False
    assert r.error_code == "URL_HOST_BLOCKED"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

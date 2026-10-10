"""core.agent_runtime.browser.browser_actions 검증 (Stage 3 guarded browser action 골격).

실제 외부 웹사이트 접속 금지. 실제 계정/비밀번호 입력 금지. 모든 테스트는
fake Playwright 팩토리(아래 ``_FakePlaywrightContext``) 를
``_playwright_factory`` 로 주입하여 수행한다.

fake 객체는 이번 단계에서도 절대 호출되어서는 안 되는 API 들(다운로드,
업로드, 쿠키, storage_state 등)이 호출되면 예외를 던진다. click/fill/
select_option/mouse.wheel 은 의도된 실행 경로이므로 **호출만 기록**한다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / ".." / ".."))


# ─── Fake Playwright 계층 ─────────────────────────────────────────────────

# 본 단계 guarded 함수가 실수로 호출해서는 안 되는 API.
_FORBIDDEN_METHODS = frozenset(
    {
        "set_input_files",
        "check",
        "uncheck",
        "drag_and_drop",
        "press",
        "keyboard",
        "screenshot",
        "pdf",
        "storage_state",
        "add_cookies",
        "cookies",
        "expect_download",
        "save_as",
        "request",
        "evaluate",
        "evaluate_handle",
        "on",
    }
)


class _ForbiddenCall(AssertionError):
    """stage-3 guarded 규약을 위반하는 fake 메서드가 호출됨."""


def _forbidden(name: str):
    def _raise(*_a, **_kw):
        raise _ForbiddenCall(f"forbidden stage-3 violation: {name} should not be called")

    return _raise


class _FakeMouse:
    def __init__(self, log: list) -> None:
        self._log = log

    def wheel(self, delta_x: int, delta_y: int) -> None:
        self._log.append(("mouse.wheel", int(delta_x), int(delta_y)))


class _FakePage:
    def __init__(self, landed_url: str, title: str, log: list) -> None:
        self._landed_url = landed_url
        self._title = title
        self._log = log
        self.mouse = _FakeMouse(log)

    @property
    def url(self) -> str:
        return self._landed_url

    def goto(self, url: str, wait_until: str | None = None, timeout: int | None = None):
        self._log.append(("goto", url, wait_until, timeout))
        return None

    def title(self) -> str:
        self._log.append(("title",))
        return self._title

    def click(self, selector: str, timeout: int | None = None):
        self._log.append(("click", selector, timeout))
        return None

    def fill(self, selector: str, value: str, timeout: int | None = None):
        self._log.append(("fill", selector, value, timeout))
        return None

    def select_option(self, selector: str, value, timeout: int | None = None):
        self._log.append(("select_option", selector, value, timeout))
        return None

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
    landed_url: str = "https://example.com/home",
    title: str = "Example",
):
    log: list = []
    page = _FakePage(landed_url, title, log)
    context = _FakeContext(page, log)
    browser = _FakeBrowser(context, log)

    def factory():
        return _FakePlaywrightContext(browser, log)

    return factory, log


# ─── 분류기 단위 테스트 ───────────────────────────────────────────────────


def test_classify_safe_click_is_low() -> None:
    from core.agent_runtime.browser.browser_actions import classify_browser_action

    r = classify_browser_action("click", text="상세보기")
    assert r["risk"] == "low"
    assert r["category"] == "safe_read"
    assert r["requires_approval"] is False


@pytest.mark.parametrize("text", ["저장", "제출", "등록", "수정", "전송", "신청", "취소"])
def test_classify_high_write_button(text: str) -> None:
    from core.agent_runtime.browser.browser_actions import classify_browser_action

    r = classify_browser_action("click", text=text)
    assert r["risk"] == "high"
    assert r["category"] == "danger_write"
    assert r["requires_approval"] is True


@pytest.mark.parametrize("text", ["삭제", "탈퇴", "결제", "승인", "확정", "마감", "로그아웃"])
def test_classify_critical_text_button(text: str) -> None:
    from core.agent_runtime.browser.browser_actions import classify_browser_action

    r = classify_browser_action("click", text=text)
    assert r["risk"] == "critical"
    assert r["category"] == "danger_write"
    assert r["requires_approval"] is True


def test_classify_type_text_general_input_is_medium() -> None:
    from core.agent_runtime.browser.browser_actions import classify_browser_action

    r = classify_browser_action("type_text", selector="#search", value="query")
    assert r["risk"] == "medium"
    assert r["category"] == "safe_input"
    assert r["requires_approval"] is False


def test_classify_password_selector_blocked() -> None:
    from core.agent_runtime.browser.browser_actions import classify_browser_action

    r = classify_browser_action("type_text", selector="input[type=password]")
    assert r["category"] == "blocked"
    assert r["requires_approval"] is True
    assert r["risk"] in ("high", "critical")


def test_classify_password_selector_by_name_blocked() -> None:
    from core.agent_runtime.browser.browser_actions import classify_browser_action

    r = classify_browser_action("type_text", selector="#user-password")
    assert r["category"] == "blocked"


def test_classify_select_option_medium() -> None:
    from core.agent_runtime.browser.browser_actions import classify_browser_action

    r = classify_browser_action("select_option", selector="#region", value="seoul")
    assert r["risk"] == "medium"
    assert r["category"] == "safe_input"
    assert r["requires_approval"] is False


def test_classify_scroll_low() -> None:
    from core.agent_runtime.browser.browser_actions import classify_browser_action

    r = classify_browser_action("scroll")
    assert r["risk"] == "low"
    assert r["category"] == "safe_read"
    assert r["requires_approval"] is False


@pytest.mark.parametrize(
    "action",
    [
        "submit_form",
        "upload_file",
        "download_file",
        "delete",
        "approve",
        "payment",
        "credential_submit",
        "password_fill",
        "storage_state",
        "cookies",
    ],
)
def test_classify_blocked_actions(action: str) -> None:
    from core.agent_runtime.browser.browser_actions import classify_browser_action

    r = classify_browser_action(action)
    assert r["category"] == "blocked"
    assert r["requires_approval"] is True
    assert r["risk"] == "critical"


# ─── 실행 게이트 — 성공 경로 ─────────────────────────────────────────────


def test_safe_click_calls_page_click() -> None:
    from core.agent_runtime.browser.browser_actions import (
        perform_browser_action_readwrite_guarded,
    )

    factory, log = _make_fake_factory()
    r = perform_browser_action_readwrite_guarded(
        url="https://example.com/list",
        action="click",
        selector="#more-details",
        _playwright_factory=factory,
    )
    assert r["ok"] is True
    assert r["action_executed"] is True
    assert r["approval_required"] is False
    assert r["risk"] == "low"
    names = [e[0] for e in log if isinstance(e, tuple)]
    assert "click" in names
    # goto → click → close 순서 유지
    assert names.index("goto") < names.index("click")


def test_type_text_general_input_calls_page_fill() -> None:
    from core.agent_runtime.browser.browser_actions import (
        perform_browser_action_readwrite_guarded,
    )

    factory, log = _make_fake_factory()
    r = perform_browser_action_readwrite_guarded(
        url="https://example.com/form",
        action="type_text",
        selector="#search-input",
        value="hello",
        _playwright_factory=factory,
    )
    assert r["ok"] is True
    assert r["action_executed"] is True
    assert r["risk"] == "medium"
    fills = [e for e in log if isinstance(e, tuple) and e[0] == "fill"]
    assert len(fills) == 1
    assert fills[0][1] == "#search-input"
    assert fills[0][2] == "hello"


def test_select_option_calls_page_select_option() -> None:
    from core.agent_runtime.browser.browser_actions import (
        perform_browser_action_readwrite_guarded,
    )

    factory, log = _make_fake_factory()
    r = perform_browser_action_readwrite_guarded(
        url="https://example.com/",
        action="select_option",
        selector="#region",
        value="seoul",
        _playwright_factory=factory,
    )
    assert r["ok"] is True
    assert r["action_executed"] is True
    selects = [e for e in log if isinstance(e, tuple) and e[0] == "select_option"]
    assert len(selects) == 1
    assert selects[0][1] == "#region"


def test_scroll_uses_mouse_wheel_only() -> None:
    from core.agent_runtime.browser.browser_actions import (
        perform_browser_action_readwrite_guarded,
    )

    factory, log = _make_fake_factory()
    r = perform_browser_action_readwrite_guarded(
        url="https://example.com/",
        action="scroll",
        value="800",
        _playwright_factory=factory,
    )
    assert r["ok"] is True
    assert r["action_executed"] is True
    wheel_calls = [e for e in log if isinstance(e, tuple) and e[0] == "mouse.wheel"]
    assert len(wheel_calls) == 1
    assert wheel_calls[0][2] == 800


# ─── 실행 게이트 — 차단 경로 ─────────────────────────────────────────────


def test_save_button_click_requires_approval_and_never_clicks() -> None:
    from core.agent_runtime.browser.browser_actions import (
        perform_browser_action_readwrite_guarded,
    )

    factory, log = _make_fake_factory()
    r = perform_browser_action_readwrite_guarded(
        url="https://example.com/",
        action="click",
        text="저장",
        _playwright_factory=factory,
    )
    assert r["ok"] is True
    assert r["approval_required"] is True
    assert r["action_executed"] is False
    assert r["risk"] == "high"
    # 브라우저 자체가 열리지 않아야 한다 (log 비어있어야 함).
    assert log == []


def test_submit_button_click_requires_approval() -> None:
    from core.agent_runtime.browser.browser_actions import (
        perform_browser_action_readwrite_guarded,
    )

    factory, log = _make_fake_factory()
    r = perform_browser_action_readwrite_guarded(
        url="https://example.com/",
        action="click",
        text="제출",
        _playwright_factory=factory,
    )
    assert r["action_executed"] is False
    assert r["approval_required"] is True
    names = [e[0] for e in log if isinstance(e, tuple)]
    assert "click" not in names


def test_delete_button_blocked_never_clicks() -> None:
    from core.agent_runtime.browser.browser_actions import (
        perform_browser_action_readwrite_guarded,
    )

    factory, log = _make_fake_factory()
    r = perform_browser_action_readwrite_guarded(
        url="https://example.com/",
        action="click",
        text="삭제",
        _playwright_factory=factory,
    )
    assert r["ok"] is True
    assert r["action_executed"] is False
    assert r["approval_required"] is True
    assert r["risk"] == "critical"
    assert log == []


def test_critical_even_when_approved_is_not_executed() -> None:
    from core.agent_runtime.browser.browser_actions import (
        perform_browser_action_readwrite_guarded,
    )

    factory, log = _make_fake_factory()
    r = perform_browser_action_readwrite_guarded(
        url="https://example.com/",
        action="click",
        text="결제",
        approved=True,
        _playwright_factory=factory,
    )
    assert r["action_executed"] is False
    assert r["approval_required"] is True
    assert log == []


def test_password_fill_blocked_never_fills() -> None:
    from core.agent_runtime.browser.browser_actions import (
        perform_browser_action_readwrite_guarded,
    )

    factory, log = _make_fake_factory()
    r = perform_browser_action_readwrite_guarded(
        url="https://example.com/login",
        action="type_text",
        selector="input[type=password]",
        value="plaintext-not-stored",
        _playwright_factory=factory,
    )
    assert r["ok"] is True
    assert r["action_executed"] is False
    assert r["approval_required"] is True
    assert r["category"] == "blocked"
    names = [e[0] for e in log if isinstance(e, tuple)]
    assert "fill" not in names
    assert log == []


def test_form_submit_is_blocked() -> None:
    from core.agent_runtime.browser.browser_actions import (
        perform_browser_action_readwrite_guarded,
    )

    factory, log = _make_fake_factory()
    r = perform_browser_action_readwrite_guarded(
        url="https://example.com/",
        action="submit_form",
        _playwright_factory=factory,
    )
    assert r["ok"] is True
    assert r["action_executed"] is False
    assert r["approval_required"] is True
    assert r["category"] == "blocked"
    assert log == []


@pytest.mark.parametrize(
    "banned_action",
    [
        "upload_file",
        "download_file",
        "set_input_files",
        "delete",
        "approve",
        "payment",
        "storage_state",
        "cookies",
    ],
)
def test_banned_actions_never_execute(banned_action: str) -> None:
    from core.agent_runtime.browser.browser_actions import (
        perform_browser_action_readwrite_guarded,
    )

    factory, log = _make_fake_factory()
    r = perform_browser_action_readwrite_guarded(
        url="https://example.com/",
        action=banned_action,
        _playwright_factory=factory,
    )
    assert r["action_executed"] is False
    assert r["approval_required"] is True
    assert r["category"] == "blocked"
    assert log == []


# ─── URL 안전성 ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "http://127.0.0.1/",
        "http://192.168.1.1/",
        "http://169.254.169.254/",
    ],
)
def test_url_safety_blocks_private_network_default(url: str) -> None:
    from core.agent_runtime.browser.browser_actions import (
        perform_browser_action_readwrite_guarded,
    )

    factory, log = _make_fake_factory()
    r = perform_browser_action_readwrite_guarded(
        url=url,
        action="click",
        selector="#x",
        _playwright_factory=factory,
    )
    assert r["ok"] is False
    assert r["error_code"] == "URL_HOST_BLOCKED"
    assert r["action_executed"] is False
    assert log == []  # 브라우저도 열리지 않음


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "data:text/html,<h1>x</h1>",
    ],
)
def test_url_safety_blocks_dangerous_schemes(url: str) -> None:
    from core.agent_runtime.browser.browser_actions import (
        perform_browser_action_readwrite_guarded,
    )

    factory, log = _make_fake_factory()
    r = perform_browser_action_readwrite_guarded(
        url=url,
        action="click",
        selector="#x",
        _playwright_factory=factory,
    )
    assert r["ok"] is False
    assert r["action_executed"] is False
    assert log == []


# ─── Playwright 미설치 ───────────────────────────────────────────────────


def test_playwright_missing_graceful_fail() -> None:
    from core.agent_runtime.browser.browser_actions import (
        BrowserActionDependencyMissing,
        perform_browser_action_readwrite_guarded,
    )

    def bad_factory():
        raise BrowserActionDependencyMissing("playwright not installed")

    r = perform_browser_action_readwrite_guarded(
        url="https://example.com/",
        action="click",
        selector="#x",
        _playwright_factory=bad_factory,
    )
    assert r["ok"] is False
    assert r["error_code"] == "BROWSER_DEPENDENCY_MISSING"
    assert r["action_executed"] is False


# ─── 결과 위생 — 쿠키/토큰/비밀번호 값 미포함 ──────────────────────────


def test_result_contains_no_sensitive_values() -> None:
    """password 값/쿠키/토큰 후보가 반환 dict 에 절대 포함되지 않는다."""
    from core.agent_runtime.browser.browser_actions import (
        perform_browser_action_readwrite_guarded,
    )

    leak_marker = "TOP_SECRET_PW_DEADBEEF"
    factory, _log = _make_fake_factory()
    r = perform_browser_action_readwrite_guarded(
        url="https://example.com/login",
        action="type_text",
        selector="input[type=password]",
        value=leak_marker,
        _playwright_factory=factory,
    )
    s = json.dumps(r, ensure_ascii=False)
    assert leak_marker not in s
    for banned in ("Bearer ", "cookie", "Set-Cookie", "session_id"):
        assert banned not in s


# ─── close 체인 ───────────────────────────────────────────────────────────


def test_page_context_browser_all_closed_on_safe_action() -> None:
    from core.agent_runtime.browser.browser_actions import (
        perform_browser_action_readwrite_guarded,
    )

    factory, log = _make_fake_factory()
    r = perform_browser_action_readwrite_guarded(
        url="https://example.com/",
        action="scroll",
        _playwright_factory=factory,
    )
    assert r["ok"] is True
    names = [e[0] for e in log if isinstance(e, tuple)]
    assert "page.close" in names
    assert "context.close" in names
    assert "browser.close" in names
    order = [n for n in names if n.endswith(".close")]
    assert order == ["page.close", "context.close", "browser.close"]


# ─── 정적 검증 — 금지 패턴이 실행 코드에 없어야 한다 ───────────────────


def test_browser_actions_source_has_no_mutating_network_calls() -> None:
    from pathlib import Path

    import core.agent_runtime.browser.browser_actions as mod

    src = Path(mod.__file__).read_text(encoding="utf-8")
    # 실제로 form submit / 쿠키 / 다운로드 관련 API 를 호출하지 않아야 한다.
    banned_tokens = (
        "storage_state(",
        "add_cookies(",
        ".cookies(",
        "set_input_files(",
        "expect_download(",
        "save_as(",
        "page.evaluate(",
    )
    for token in banned_tokens:
        assert token not in src, f"{token!r} appeared in browser_actions.py"


# ─── action 통합 — execute_action 경로 ──────────────────────────────────


def test_action_web_click_guarded_safe(monkeypatch) -> None:
    from core.agent_runtime.browser import browser_actions
    from core.agent_runtime.connection.actions import execute_action

    captured: list[dict] = []

    def fake_perform(**kwargs):
        captured.append(dict(kwargs))
        return {
            "ok": True,
            "url": kwargs.get("url"),
            "action": kwargs.get("action"),
            "risk": "low",
            "category": "safe_read",
            "classification": {
                "risk": "low",
                "category": "safe_read",
                "requires_approval": False,
                "reason": ["click:safe"],
            },
            "approval_required": False,
            "action_executed": True,
            "summary": "ok:click risk=low",
        }

    monkeypatch.setattr(
        browser_actions,
        "perform_browser_action_readwrite_guarded",
        fake_perform,
    )

    r = execute_action(
        "web_click_guarded",
        {"url": "https://example.com/", "selector": "#more"},
    )
    assert r.success is True
    assert r.data["risk"] == "low"
    assert r.data["approval_required"] is False
    assert r.data["action_executed"] is True
    assert captured[0]["action"] == "click"
    assert captured[0]["selector"] == "#more"


def test_action_web_type_guarded_password_approval_required(monkeypatch) -> None:
    from core.agent_runtime.browser import browser_actions
    from core.agent_runtime.connection.actions import execute_action

    def fake_perform(**kwargs):
        return {
            "ok": True,
            "url": kwargs.get("url"),
            "action": kwargs.get("action"),
            "risk": "high",
            "category": "blocked",
            "classification": {
                "risk": "high",
                "category": "blocked",
                "requires_approval": True,
                "reason": ["selector_hint:password"],
            },
            "approval_required": True,
            "action_executed": False,
            "summary": "blocked:type_text risk=high",
        }

    monkeypatch.setattr(
        browser_actions,
        "perform_browser_action_readwrite_guarded",
        fake_perform,
    )

    r = execute_action(
        "web_type_guarded",
        {
            "url": "https://example.com/login",
            "selector": "input[type=password]",
            "value": "SECRET",
        },
    )
    assert r.success is True  # success=True 이지만 approval_required=True.
    assert r.data["approval_required"] is True
    assert r.data["action_executed"] is False
    assert r.data["category"] == "blocked"


def test_action_web_scroll_guarded_defaults(monkeypatch) -> None:
    from core.agent_runtime.browser import browser_actions
    from core.agent_runtime.connection.actions import execute_action

    captured: list[dict] = []

    def fake_perform(**kwargs):
        captured.append(dict(kwargs))
        return {
            "ok": True,
            "url": kwargs.get("url"),
            "action": "scroll",
            "risk": "low",
            "category": "safe_read",
            "classification": {
                "risk": "low",
                "category": "safe_read",
                "requires_approval": False,
                "reason": ["scroll:low"],
            },
            "approval_required": False,
            "action_executed": True,
            "summary": "ok:scroll risk=low",
        }

    monkeypatch.setattr(
        browser_actions,
        "perform_browser_action_readwrite_guarded",
        fake_perform,
    )

    r = execute_action(
        "web_scroll_guarded",
        {"url": "https://example.com/"},
    )
    assert r.success is True
    assert captured[0]["allow_private_network"] is False
    assert captured[0]["approved"] is False


def test_action_web_click_guarded_missing_url() -> None:
    from core.agent_runtime.connection.actions import execute_action

    r = execute_action("web_click_guarded", {})
    assert r.success is False
    assert r.error_code == "MISSING_URL"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

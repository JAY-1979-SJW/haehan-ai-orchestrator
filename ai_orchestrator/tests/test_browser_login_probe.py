"""core.agent_runtime.browser.browser_login_probe 검증 (수동 로그인 확인 모드).

실제 네이버/외부 웹사이트 접속 금지. 실제 Playwright 실행 금지. 모든 테스트는
fake Playwright 팩토리 + fake time 모듈을 주입해 deterministic 하게 수행.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / ".." / ".."))


# ─── Fake Playwright 계층 ────────────────────────────────────────────────

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
        raise _ForbiddenCall(f"forbidden read-only violation: {name}")

    return _raise


class _ScriptedPage:
    """관찰 회차별로 다른 title/url/html 을 돌려주는 fake page.

    각 관찰은 title() → url → content() 순으로 호출되며, content() 호출 뒤
    내부 커서가 다음 state 로 advance 한다 (단, 마지막 state 에 도달한 뒤에는
    그대로 유지).
    """

    def __init__(self, script: list[dict], log: list) -> None:
        self._script = list(script) or [{"title": "", "url": "", "html": ""}]
        self._log = log
        self._idx = 0

    def _state(self) -> dict:
        return self._script[min(self._idx, len(self._script) - 1)]

    def _advance(self) -> None:
        if self._idx < len(self._script) - 1:
            self._idx += 1

    @property
    def url(self) -> str:
        self._log.append(("page.url",))
        return self._state().get("url", "")

    def goto(self, url: str, wait_until: str | None = None, timeout: int | None = None):
        self._log.append(("goto", url, wait_until, timeout))
        return None

    def title(self) -> str:
        self._log.append(("title",))
        return self._state().get("title", "")

    def content(self) -> str:
        self._log.append(("content",))
        html = self._state().get("html", "")
        self._advance()
        return html

    def close(self) -> None:
        self._log.append(("page.close",))

    def __getattr__(self, name: str):
        if name in _FORBIDDEN_METHODS:
            return _forbidden(f"page.{name}")
        raise AttributeError(name)


class _FakeContext:
    def __init__(self, page: _ScriptedPage, log: list) -> None:
        self._page = page
        self._log = log

    def new_page(self) -> _ScriptedPage:
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
        self._b = browser
        self._log = log

    def launch(self, headless: bool = True, **kwargs) -> _FakeBrowser:
        self._log.append(("launch", {"headless": headless, **kwargs}))
        return self._b


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


class _FakeTime:
    def __init__(self) -> None:
        self._now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self._now

    def sleep(self, secs: float) -> None:
        self.sleeps.append(float(secs))
        self._now += float(secs)


def _make_probe_factory(script: list[dict]):
    log: list = []
    page = _ScriptedPage(script, log)
    context = _FakeContext(page, log)
    browser = _FakeBrowser(context, log)

    def factory():
        return _FakePlaywrightContext(browser, log)

    return factory, log, page


# ─── fixture HTML ─────────────────────────────────────────────────────────

_LOGIN_HTML = (
    "<html><head><title>네이버 로그인</title></head>"
    "<body><h1>로그인</h1>"
    "<form method='post'>"
    "<input name='id' type='text'>"
    "<input name='pw' type='password'>"
    "<button type='submit'>로그인</button>"
    "</form></body></html>"
)

_POST_LOGIN_HTML = (
    "<html><head><title>네이버</title></head>"
    "<body><h1>메인</h1>"
    "<a href='/mypage'>내정보</a>"
    "<a href='/mail'>메일</a>"
    "</body></html>"
)


# ─── 1. allowed_hosts 외 URL 차단 ────────────────────────────────────────


def test_url_outside_allowed_hosts_blocked():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    factory, log, _ = _make_probe_factory(
        [
            {"title": "x", "url": "https://example.com/", "html": "<html></html>"},
        ]
    )
    r = probe_manual_login_flow(
        url="https://example.com/",
        wait_seconds=5,
        poll_interval_seconds=1,
        allowed_hosts=["naver.com", "nid.naver.com"],
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    assert r["ok"] is False
    assert r["error_code"] == "HOST_NOT_ALLOWED"
    # 팩토리/브라우저까지 도달하면 안 됨.
    assert log == []


# ─── 2. naver.com / nid.naver.com 허용 ───────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "https://www.naver.com/",
        "https://nid.naver.com/nidlogin.login",
    ],
)
def test_naver_hosts_reach_factory(url):
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    factory, log, _ = _make_probe_factory(
        [
            {"title": "Naver", "url": url, "html": _LOGIN_HTML},
        ]
    )
    r = probe_manual_login_flow(
        url=url,
        wait_seconds=3,
        poll_interval_seconds=1,
        allowed_hosts=["www.naver.com", "nid.naver.com"],
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    # HOST_NOT_ALLOWED 로 차단되지 않았음.
    assert r.get("error_code") != "HOST_NOT_ALLOWED"
    gotos = [e for e in log if isinstance(e, tuple) and e and e[0] == "goto"]
    assert len(gotos) == 1
    assert gotos[0][1] == url


# ─── 3. file/javascript/data URL 차단 ────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/html,<h1>x</h1>",
        "about:blank",
        "chrome://settings",
        "ftp://example.com/",
    ],
)
def test_dangerous_scheme_blocked(url):
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    factory, log, _ = _make_probe_factory(
        [
            {"title": "x", "url": url, "html": ""},
        ]
    )
    r = probe_manual_login_flow(
        url=url,
        wait_seconds=3,
        poll_interval_seconds=1,
        allowed_hosts=["naver.com"],
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    assert r["ok"] is False
    assert r["error_code"] in {
        "URL_SCHEME_BLOCKED",
        "URL_NO_HOST",
        "URL_PARSE_FAILED",
    }
    assert log == []


# ─── 4. localhost/private IP 기본 차단 ───────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "http://127.0.0.1/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
    ],
)
def test_private_host_blocked(url):
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    factory, log, _ = _make_probe_factory(
        [
            {"title": "x", "url": url, "html": ""},
        ]
    )
    r = probe_manual_login_flow(
        url=url,
        wait_seconds=3,
        poll_interval_seconds=1,
        allowed_hosts=["naver.com"],
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    assert r["ok"] is False
    assert r["error_code"] == "URL_HOST_BLOCKED"
    assert log == []


# ─── 5. 초기 페이지 password input 감지 ─────────────────────────────────


def test_initial_password_input_detected():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    script = [
        {"title": "네이버 로그인", "url": "https://nid.naver.com/nidlogin.login", "html": _LOGIN_HTML},
    ]
    factory, _log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://nid.naver.com/nidlogin.login",
        wait_seconds=3,
        poll_interval_seconds=1,
        allowed_hosts=["nid.naver.com"],
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    # 로그인 변화 없음 → timeout.
    assert r["ok"] is False
    assert r["error_code"] == "LOGIN_TIMEOUT"
    init = r["initial"]
    assert init["login_required_hint"] is True
    assert "password_input_detected" in init["login_reason"]


# ─── 6. password input 사라짐 → login_completed_hint=True ───────────────


def test_password_disappeared_sets_completed_hint():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    script = [
        {"title": "네이버 로그인", "url": "https://nid.naver.com/nidlogin.login", "html": _LOGIN_HTML},
        {"title": "네이버 로그인", "url": "https://nid.naver.com/nidlogin.login", "html": _LOGIN_HTML},
        # password 사라짐 (URL 은 동일하게 유지 가능)
        {"title": "네이버", "url": "https://nid.naver.com/nidlogin.login", "html": _POST_LOGIN_HTML},
    ]
    factory, _log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://nid.naver.com/nidlogin.login",
        wait_seconds=30,
        poll_interval_seconds=1,
        allowed_hosts=["nid.naver.com"],
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    assert r["ok"] is True
    after = r["after"]
    assert after["login_completed_hint"] is True
    assert "password_input_disappeared" in after["login_completion_reason"]


# ─── 7. current_url 변경 → login_completed_hint=True ─────────────────────


def test_url_changed_sets_completed_hint():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    script = [
        {"title": "네이버 로그인", "url": "https://nid.naver.com/nidlogin.login", "html": _LOGIN_HTML},
        {"title": "네이버", "url": "https://www.naver.com/", "html": _POST_LOGIN_HTML},
    ]
    factory, _log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://nid.naver.com/nidlogin.login",
        wait_seconds=30,
        poll_interval_seconds=1,
        allowed_hosts=["nid.naver.com", "www.naver.com"],
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    assert r["ok"] is True
    assert "url_changed" in r["after"]["login_completion_reason"]


# ─── 8. success_url_contains 로 완료 감지 ────────────────────────────────


def test_success_url_contains_match():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    script = [
        {"title": "t", "url": "https://nid.naver.com/nidlogin.login", "html": "<html><body></body></html>"},
        {"title": "t", "url": "https://nid.naver.com/dashboard/home", "html": "<html><body></body></html>"},
    ]
    factory, _log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://nid.naver.com/nidlogin.login",
        wait_seconds=30,
        poll_interval_seconds=1,
        success_url_contains=["/dashboard"],
        allowed_hosts=["nid.naver.com"],
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    assert r["ok"] is True
    reasons = r["after"]["login_completion_reason"]
    assert any(x.startswith("success_url_match:") for x in reasons)


# ─── 9. success_text_hints 로 완료 감지 ──────────────────────────────────


def test_success_text_hints_match():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    script = [
        {"title": "t", "url": "https://nid.naver.com/x", "html": "<html><body></body></html>"},
        {"title": "t", "url": "https://nid.naver.com/x", "html": "<html><body><h1>환영합니다</h1></body></html>"},
    ]
    factory, _log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://nid.naver.com/x",
        wait_seconds=30,
        poll_interval_seconds=1,
        success_text_hints=["환영"],
        allowed_hosts=["nid.naver.com"],
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    assert r["ok"] is True
    reasons = r["after"]["login_completion_reason"]
    assert any(x.startswith("success_text_match:") for x in reasons)


# ─── 10. timeout → LOGIN_TIMEOUT ─────────────────────────────────────────


def test_timeout_returns_login_timeout():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    script = [
        {"title": "t", "url": "https://nid.naver.com/login", "html": _LOGIN_HTML},
    ]
    factory, _log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://nid.naver.com/login",
        wait_seconds=3,
        poll_interval_seconds=1,
        allowed_hosts=["nid.naver.com"],
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    assert r["ok"] is False
    assert r["error_code"] == "LOGIN_TIMEOUT"
    assert "last_observation" in r


# ─── 11. 결과에 password value 없음 ──────────────────────────────────────


def test_result_has_no_password_value():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    html = (
        "<html><body><form>"
        "<input name='user' type='text' value='someuser'>"
        "<input name='pw' type='password' value='secret-password-xyz'>"
        "</form></body></html>"
    )
    script = [
        {"title": "login", "url": "https://nid.naver.com/login", "html": html},
    ]
    factory, _log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://nid.naver.com/login",
        wait_seconds=3,
        poll_interval_seconds=1,
        allowed_hosts=["nid.naver.com"],
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    assert "secret-password-xyz" not in repr(r)


# ─── 12. 결과에 hidden value 없음 ────────────────────────────────────────


def test_result_has_no_hidden_value():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    html = (
        "<html><body><form>"
        "<input name='csrf' type='hidden' value='csrfTOKEN123XYZ'>"
        "<input name='pw' type='password'>"
        "</form></body></html>"
    )
    script = [
        {"title": "login", "url": "https://nid.naver.com/login", "html": html},
    ]
    factory, _log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://nid.naver.com/login",
        wait_seconds=3,
        poll_interval_seconds=1,
        allowed_hosts=["nid.naver.com"],
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    assert "csrfTOKEN123XYZ" not in repr(r)


# ─── 13. cookie/token/storage_state 호출 없음 ────────────────────────────


def test_no_cookie_or_storage_calls_in_log():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    script = [
        {"title": "t", "url": "https://nid.naver.com/login", "html": _LOGIN_HTML},
        {"title": "t", "url": "https://nid.naver.com/login", "html": _LOGIN_HTML},
    ]
    factory, log, _ = _make_probe_factory(script)
    probe_manual_login_flow(
        url="https://nid.naver.com/login",
        wait_seconds=3,
        poll_interval_seconds=1,
        allowed_hosts=["nid.naver.com"],
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    for entry in log:
        if isinstance(entry, tuple) and entry:
            tag = str(entry[0]).lower()
            for bad in ("storage_state", "cookies", "localstorage", "sessionstorage", "add_cookies"):
                assert bad not in tag, f"forbidden tag in log: {entry}"


# ─── 14. page.click/fill/type/press/select_option 호출 없음 ─────────────


def test_no_interaction_methods_called():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    script = [
        {"title": "t", "url": "https://nid.naver.com/login", "html": _LOGIN_HTML},
        {"title": "t", "url": "https://nid.naver.com/login", "html": _LOGIN_HTML},
    ]
    factory, log, _ = _make_probe_factory(script)
    # fake page 는 forbidden 메서드 호출 시 AssertionError 를 던진다.
    r = probe_manual_login_flow(
        url="https://nid.naver.com/login",
        wait_seconds=3,
        poll_interval_seconds=1,
        allowed_hosts=["nid.naver.com"],
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    assert isinstance(r, dict)
    forbidden = (
        "click",
        "fill",
        "type",
        "press",
        "select_option",
        "set_input_files",
        "evaluate",
        "screenshot",
        "dblclick",
    )
    for entry in log:
        if isinstance(entry, tuple) and entry:
            tag = str(entry[0]).lower()
            for bad in forbidden:
                assert bad not in tag, f"forbidden interaction: {entry}"


# ─── 15. storage_state/cookies/localStorage/sessionStorage 호출 없음 ───


def test_no_session_state_api_calls():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    script = [
        {"title": "t", "url": "https://nid.naver.com/login", "html": _LOGIN_HTML},
    ]
    factory, log, _ = _make_probe_factory(script)
    probe_manual_login_flow(
        url="https://nid.naver.com/login",
        wait_seconds=3,
        poll_interval_seconds=1,
        allowed_hosts=["nid.naver.com"],
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    # context.storage_state, context.cookies 등 방어.
    for entry in log:
        if not (isinstance(entry, tuple) and entry):
            continue
        tag = str(entry[0]).lower()
        assert "storage_state" not in tag
        assert "cookies" not in tag
        assert "localstorage" not in tag
        assert "sessionstorage" not in tag


# ─── 16. page/context/browser close 호출 확인 ────────────────────────────


def test_close_methods_called():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    script = [
        {"title": "t", "url": "https://nid.naver.com/login", "html": _LOGIN_HTML},
    ]
    factory, log, _ = _make_probe_factory(script)
    probe_manual_login_flow(
        url="https://nid.naver.com/login",
        wait_seconds=3,
        poll_interval_seconds=1,
        allowed_hosts=["nid.naver.com"],
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    tags = [e[0] for e in log if isinstance(e, tuple) and e]
    assert "page.close" in tags
    assert "context.close" in tags
    assert "browser.close" in tags


# ─── 17. web_probe_manual_login action 정상 반환 ────────────────────────


def test_action_web_probe_manual_login_returns_result():
    from core.agent_runtime.connection.actions import execute_action

    script = [
        {"title": "Naver Login", "url": "https://nid.naver.com/nidlogin.login", "html": _LOGIN_HTML},
        {"title": "Naver", "url": "https://www.naver.com/", "html": _POST_LOGIN_HTML},
    ]
    factory, _log, _ = _make_probe_factory(script)
    result = execute_action(
        "web_probe_manual_login",
        {
            "url": "https://nid.naver.com/nidlogin.login",
            "wait_seconds": 30,
            "poll_interval_seconds": 1,
            "allowed_hosts": ["nid.naver.com", "www.naver.com"],
            "_browser_factory": factory,
            "_clock": _FakeTime(),
        },
    )
    assert result.success is True
    assert result.data.get("login_completed_hint") is True
    assert result.data.get("mode") == "manual_login_probe"


def test_action_probe_blocks_non_allowed_host():
    from core.agent_runtime.connection.actions import execute_action

    # allowed_hosts=[naver.com] 에 걸리지 않는 호스트 → HOST_NOT_ALLOWED.
    # 실제 브라우저는 실행되지 않는다 (factory 도 주입하지 않음).
    result = execute_action(
        "web_probe_manual_login",
        {
            "url": "https://example.com/",
            "wait_seconds": 3,
            "poll_interval_seconds": 1,
            "allowed_hosts": ["naver.com"],
        },
    )
    assert result.success is False
    assert result.error_code == "HOST_NOT_ALLOWED"


# ─── 18. Playwright 미설치 graceful fail ─────────────────────────────────


def test_playwright_missing_graceful():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow
    from core.agent_runtime.browser.browser_reader import BrowserDependencyMissing

    def bad_factory():
        raise BrowserDependencyMissing("playwright not installed")

    r = probe_manual_login_flow(
        url="https://nid.naver.com/login",
        wait_seconds=3,
        poll_interval_seconds=1,
        allowed_hosts=["nid.naver.com"],
        _browser_factory=bad_factory,
        _clock=_FakeTime(),
    )
    assert r["ok"] is False
    assert r["error_code"] == "BROWSER_DEPENDENCY_MISSING"


# ─── 19. smoke 스크립트는 pytest 에서 실제 실행하지 않음 ────────────────


def test_smoke_script_not_auto_executed():
    """pytest import 만으로 실제 네이버 접속이 발생하지 않아야 한다."""
    smoke_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "naver" / "smoke_naver_manual_login_probe.py"
    assert smoke_path.exists(), "smoke script missing"
    src = smoke_path.read_text(encoding="utf-8")
    # 실제 실행은 __main__ 가드 뒤에서만 일어난다.
    assert 'if __name__ == "__main__":' in src or "if __name__ == '__main__':" in src
    # 모듈 최상단에서 probe_manual_login_flow 호출 금지.
    for line in src.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        # 최상단 (들여쓰기 없음) 에서 함수 호출 흔적 금지.
        if not line.startswith((" ", "\t")):
            assert "probe_manual_login_flow(" not in line


# ─── 20. production 코드에 네이버 계정/비밀번호/토큰 하드코딩 없음 ────


def test_no_credentials_hardcoded():
    root = Path(__file__).resolve().parent.parent.parent
    probe_src = (root / "core" / "agent_runtime" / "browser" / "browser_login_probe.py").read_text(encoding="utf-8")
    smoke_src = (root / "scripts" / "naver" / "smoke_naver_manual_login_probe.py").read_text(encoding="utf-8")

    forbidden_tokens = (
        "NAVER_ID",
        "NAVER_PW",
        "nid_aut",
        "NID_SES",
        "NID_AUT",
        "skyjwshin",
        "Bearer ",
        "sk-",
    )
    for src_name, src in (
        ("browser_login_probe.py", probe_src),
        ("smoke_naver_manual_login_probe.py", smoke_src),
    ):
        for tok in forbidden_tokens:
            assert tok not in src, f"forbidden token {tok!r} in {src_name}"

    # 실제 입력/자동화 API 흔적도 production 코드에서 발견되면 안 됨.
    for tok in (
        ".fill(",
        ".type(",
        ".click(",
        ".press(",
        ".select_option(",
        ".set_input_files(",
        ".storage_state(",
        ".add_cookies(",
    ):
        assert tok not in probe_src, f"forbidden interaction API {tok!r} in browser_login_probe.py"
        assert tok not in smoke_src, f"forbidden interaction API {tok!r} in smoke_naver_manual_login_probe.py"


# ─── 21. require_visible_confirm: 사용자 확인 전까지 polling 금지 ────────


class _RecordingInput:
    """input 호출을 기록하고 scripted response 를 돌려주는 fake."""

    def __init__(self, responses=None, raise_on=None):
        self.prompts: list[str] = []
        self._responses = list(responses or [])
        self._raise_on = set(raise_on or [])
        self._call_idx = 0

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        idx = self._call_idx
        self._call_idx += 1
        if idx in self._raise_on:
            raise KeyboardInterrupt
        if self._responses:
            return self._responses.pop(0)
        return ""


def test_require_visible_confirm_blocks_polling_until_user_presses_enter():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    # 사용자가 Ctrl+C 로 중단하면 polling 은 시작되지 않아야 한다.
    fake_input = _RecordingInput(raise_on=[0])
    clock = _FakeTime()
    script = [
        {"title": "Naver", "url": "https://nid.naver.com/nidlogin.login", "html": _LOGIN_HTML},
    ]
    factory, log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://nid.naver.com/nidlogin.login",
        wait_seconds=30,
        poll_interval_seconds=1,
        allowed_hosts=["nid.naver.com"],
        require_visible_confirm=True,
        _browser_factory=factory,
        _clock=clock,
        _input_reader=fake_input,
    )
    assert r["ok"] is False
    assert r["error_code"] == "VISIBILITY_NOT_CONFIRMED"
    assert r["visible_confirmed_by_user"] is False
    # Ctrl+C 로 취소되었으므로 clock.sleep() 이 한 번도 호출되지 않아야 한다.
    assert clock.sleeps == []
    # 딱 한 번 visibility 프롬프트만 출력됨.
    assert len(fake_input.prompts) == 1
    assert "Enter" in fake_input.prompts[0]


def test_require_visible_confirm_sets_flag_when_user_confirms():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    fake_input = _RecordingInput(responses=[""])
    clock = _FakeTime()
    script = [
        {"title": "Naver", "url": "https://nid.naver.com/nidlogin.login", "html": _LOGIN_HTML},
    ]
    factory, _log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://nid.naver.com/nidlogin.login",
        wait_seconds=3,
        poll_interval_seconds=1,
        allowed_hosts=["nid.naver.com"],
        require_visible_confirm=True,
        _browser_factory=factory,
        _clock=clock,
        _input_reader=fake_input,
    )
    assert r["visible_confirmed_by_user"] is True
    # confirm 후 polling 루프가 최소 한 번 돌았다.
    assert len(clock.sleeps) >= 1


# ─── 22. keep_open: 종료 전 사용자 Enter 기다림 ─────────────────────────


def test_keep_open_waits_for_enter_before_close():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    fake_input = _RecordingInput(responses=[""])
    script = [
        {"title": "Naver", "url": "https://www.naver.com/", "html": _POST_LOGIN_HTML},
    ]
    factory, log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://www.naver.com/",
        wait_seconds=3,
        poll_interval_seconds=1,
        allowed_hosts=["www.naver.com"],
        keep_open=True,
        _browser_factory=factory,
        _clock=_FakeTime(),
        _input_reader=fake_input,
    )
    # keep_open 프롬프트가 호출되었다.
    assert any("닫" in p for p in fake_input.prompts), fake_input.prompts
    # 프롬프트가 browser.close 이전에 호출되었다.
    tags = [e[0] for e in log if isinstance(e, tuple) and e]
    assert "browser.close" in tags
    # 사용자 응답을 받은 뒤에 close 가 호출된다는 것을 확인하기 위해,
    # keep_open 프롬프트가 최소 1회 호출되었다는 것만 검증한다.
    assert isinstance(r, dict)


# ─── 23. success_url_match 단독으로는 login_completed_hint=True 안 됨 ──


def test_success_url_match_alone_does_not_mark_completed():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    # 초기부터 target URL 에 있고, password input 도 없고, URL 도 변하지 않으면
    # success_url_match 는 애초에 발생하지 않으며, 완료로 판정되지도 않는다.
    script = [
        {"title": "Naver", "url": "https://www.naver.com/", "html": _POST_LOGIN_HTML},
    ]
    factory, _log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://www.naver.com/",
        wait_seconds=3,
        poll_interval_seconds=1,
        success_url_contains=["naver.com"],
        allowed_hosts=["www.naver.com"],
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    assert r["login_completed_hint"] is False
    assert r["ok"] is False
    # success_url_match 는 reason 에 포함되지 않는다 (initial 이 이미 매칭).
    reasons = r.get("login_completion_reason") or []
    assert not any(x.startswith("success_url_match:") for x in reasons)


# ─── 24. already_logged_in_or_public_page 상태 구분 ─────────────────────


def test_already_logged_in_state_detected():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    # 초기 URL 이 target 토큰에 매칭 + password input 없음 +
    # login_required_hint 없음 → already_logged_in_or_public_page 로 분류.
    script = [
        {"title": "Naver", "url": "https://www.naver.com/", "html": "<html><body><h1>메인</h1></body></html>"},
    ]
    factory, _log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://www.naver.com/",
        wait_seconds=3,
        poll_interval_seconds=1,
        success_url_contains=["naver.com"],
        allowed_hosts=["www.naver.com"],
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    assert r["login_state_hint"] == "already_logged_in_or_public_page"
    assert r["login_completed_hint"] is False
    assert r["ok"] is False
    assert r["error_code"] == "LOGIN_NOT_CONFIRMED"


# ─── 25. require_user_login_confirm: 사용자 Enter → user_confirmed_login


def test_user_confirmed_login_adds_reason_and_completes():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    fake_input = _RecordingInput(responses=[""])
    script = [
        {"title": "Naver", "url": "https://www.naver.com/", "html": "<html><body><h1>메인</h1></body></html>"},
    ]
    factory, _log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://www.naver.com/",
        wait_seconds=3,
        poll_interval_seconds=1,
        success_url_contains=["naver.com"],
        allowed_hosts=["www.naver.com"],
        require_user_login_confirm=True,
        _browser_factory=factory,
        _clock=_FakeTime(),
        _input_reader=fake_input,
    )
    assert r["login_confirmed_by_user"] is True
    reasons = r.get("login_completion_reason") or []
    assert "user_confirmed_login" in reasons
    assert r["login_state_hint"] == "manual_login_completed"
    assert r["login_completed_hint"] is True
    assert r["ok"] is True


def test_user_login_confirm_n_response_does_not_mark_completed():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    # 사용자가 "n" 응답 → login_confirmed_by_user=False, hint=False.
    fake_input = _RecordingInput(responses=["n"])
    script = [
        {"title": "Naver Login", "url": "https://nid.naver.com/nidlogin.login", "html": _LOGIN_HTML},
    ]
    factory, _log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://nid.naver.com/nidlogin.login",
        wait_seconds=3,
        poll_interval_seconds=1,
        allowed_hosts=["nid.naver.com"],
        require_user_login_confirm=True,
        _browser_factory=factory,
        _clock=_FakeTime(),
        _input_reader=fake_input,
    )
    assert r["login_confirmed_by_user"] is False
    assert r["login_completed_hint"] is False
    reasons = r.get("login_completion_reason") or []
    assert "user_confirmed_login" not in reasons


def test_require_user_login_confirm_suppresses_auto_completion():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    # 강한 구조 근거 (password_input_disappeared) 가 있어도 사용자가
    # 확인하지 않으면 login_completed_hint=True 로 단정하지 않는다.
    fake_input = _RecordingInput(responses=["n"])
    script = [
        {"title": "Naver Login", "url": "https://nid.naver.com/nidlogin.login", "html": _LOGIN_HTML},
        {"title": "Naver", "url": "https://nid.naver.com/nidlogin.login", "html": _POST_LOGIN_HTML},
    ]
    factory, _log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://nid.naver.com/nidlogin.login",
        wait_seconds=30,
        poll_interval_seconds=1,
        allowed_hosts=["nid.naver.com"],
        require_user_login_confirm=True,
        _browser_factory=factory,
        _clock=_FakeTime(),
        _input_reader=fake_input,
    )
    reasons = r.get("login_completion_reason") or []
    assert "password_input_disappeared" in reasons
    # 사용자 미확인 → hint=False 유지.
    assert r["login_confirmed_by_user"] is False
    assert r["login_completed_hint"] is False


# ─── 26. browser_channel 파라미터 ─────────────────────────────────────────


def test_browser_channel_chrome_forwarded_to_launch():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    script = [
        {"title": "Naver", "url": "https://www.naver.com/", "html": _POST_LOGIN_HTML},
    ]
    factory, log, _ = _make_probe_factory(script)
    probe_manual_login_flow(
        url="https://www.naver.com/",
        wait_seconds=3,
        poll_interval_seconds=1,
        allowed_hosts=["www.naver.com"],
        browser_channel="chrome",
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    launch_entries = [e for e in log if isinstance(e, tuple) and e and e[0] == "launch"]
    assert launch_entries
    kwargs = launch_entries[0][1]
    assert kwargs.get("channel") == "chrome"
    assert kwargs.get("headless") is False


def test_browser_channel_chromium_does_not_set_channel_kwarg():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    script = [
        {"title": "Naver", "url": "https://www.naver.com/", "html": _POST_LOGIN_HTML},
    ]
    factory, log, _ = _make_probe_factory(script)
    probe_manual_login_flow(
        url="https://www.naver.com/",
        wait_seconds=3,
        poll_interval_seconds=1,
        allowed_hosts=["www.naver.com"],
        browser_channel="chromium",
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    launch_entries = [e for e in log if isinstance(e, tuple) and e and e[0] == "launch"]
    kwargs = launch_entries[0][1]
    assert "channel" not in kwargs


def test_invalid_browser_channel_returns_error():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    script = [
        {"title": "Naver", "url": "https://www.naver.com/", "html": "<html></html>"},
    ]
    factory, log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://www.naver.com/",
        wait_seconds=3,
        poll_interval_seconds=1,
        allowed_hosts=["www.naver.com"],
        browser_channel="safari",  # 허용되지 않음
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    assert r["ok"] is False
    assert r["error_code"] == "BROWSER_CHANNEL_INVALID"
    # 팩토리는 호출되지 않았어야 한다.
    assert log == []


# ─── 27. 자동 로그인/클릭/입력/쿠키 수집 없음 유지 ──────────────────────


def test_no_auto_login_or_cookie_collection_with_new_options():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    fake_input = _RecordingInput(responses=["", "", ""])
    script = [
        {"title": "Naver Login", "url": "https://nid.naver.com/nidlogin.login", "html": _LOGIN_HTML},
        {"title": "Naver", "url": "https://www.naver.com/", "html": _POST_LOGIN_HTML},
    ]
    factory, log, _ = _make_probe_factory(script)
    probe_manual_login_flow(
        url="https://nid.naver.com/nidlogin.login",
        wait_seconds=30,
        poll_interval_seconds=1,
        allowed_hosts=["nid.naver.com", "www.naver.com"],
        require_visible_confirm=True,
        require_user_login_confirm=True,
        keep_open=True,
        _browser_factory=factory,
        _clock=_FakeTime(),
        _input_reader=fake_input,
    )
    forbidden = (
        "click",
        "fill",
        "type",
        "press",
        "select_option",
        "set_input_files",
        "evaluate",
        "screenshot",
        "dblclick",
        "storage_state",
        "cookies",
        "add_cookies",
        "localstorage",
        "sessionstorage",
    )
    for entry in log:
        if isinstance(entry, tuple) and entry:
            tag = str(entry[0]).lower()
            for bad in forbidden:
                assert bad not in tag, f"forbidden op in log: {entry}"

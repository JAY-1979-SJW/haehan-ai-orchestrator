"""유튜브/구글 수동 로그인 smoke 스크립트 검증.

실제 유튜브/구글 접속 금지. 실제 Playwright 실행 금지. 모든 테스트는
fake Playwright 팩토리 + fake time 모듈을 주입해 deterministic 하게 수행.

기존 ``core.agent_runtime.browser.browser_login_probe.probe_manual_login_flow`` 를 재사용
하므로, 본 테스트는 유튜브 smoke 스크립트 경로 (허용 호스트 / 완료 감지)
를 중심으로 검증한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


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

    def goto(self, url, wait_until=None, timeout=None):
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

    def __getattr__(self, name):
        if name in _FORBIDDEN_METHODS:
            return _forbidden(f"page.{name}")
        raise AttributeError(name)


class _FakeContext:
    def __init__(self, page, log):
        self._p = page
        self._log = log

    def new_page(self):
        self._log.append(("new_page",))
        return self._p

    def close(self):
        self._log.append(("context.close",))

    def __getattr__(self, name):
        if name in _FORBIDDEN_METHODS:
            return _forbidden(f"context.{name}")
        raise AttributeError(name)


class _FakeBrowser:
    def __init__(self, context, log):
        self._c = context
        self._log = log

    def new_context(self, **kwargs):
        self._log.append(("new_context", kwargs))
        return self._c

    def close(self):
        self._log.append(("browser.close",))

    def __getattr__(self, name):
        if name in _FORBIDDEN_METHODS:
            return _forbidden(f"browser.{name}")
        raise AttributeError(name)


class _FakeChromium:
    def __init__(self, browser, log):
        self._b = browser
        self._log = log

    def launch(self, headless=True, **kwargs):
        self._log.append(("launch", {"headless": headless, **kwargs}))
        return self._b


class _FakePlaywright:
    def __init__(self, browser, log):
        self.chromium = _FakeChromium(browser, log)


class _FakePlaywrightContext:
    def __init__(self, browser, log):
        self._pw = _FakePlaywright(browser, log)
        self._log = log

    def __enter__(self):
        self._log.append(("__enter__",))
        return self._pw

    def __exit__(self, *_args):
        self._log.append(("__exit__",))
        return None


class _FakeTime:
    def __init__(self):
        self._now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self):
        return self._now

    def sleep(self, secs):
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


# 유튜브 smoke 의 기본 허용 호스트 목록.
_YT_ALLOWED_HOSTS = [
    "youtube.com",
    "www.youtube.com",
    "studio.youtube.com",
    "accounts.google.com",
    "myaccount.google.com",
]

_GOOGLE_LOGIN_HTML = (
    "<html><head><title>Sign in - Google Accounts</title></head>"
    "<body><h1>Sign in</h1>"
    "<form method='post'>"
    "<input name='identifier' type='email'>"
    "<input name='password' type='password'>"
    "<button type='submit'>Next</button>"
    "</form></body></html>"
)

_YT_HOME_HTML = (
    "<html><head><title>YouTube</title></head>"
    "<body><h1>Home</h1>"
    "<a href='/feed/subscriptions'>Subscriptions</a>"
    "<a href='/feed/history'>History</a>"
    "</body></html>"
)

_STUDIO_HOME_HTML = (
    "<html><head><title>YouTube Studio</title></head>"
    "<body><h1>Channel dashboard</h1>"
    "<a href='/channel/analytics'>Analytics</a>"
    "</body></html>"
)


# ─── 1~5. 허용 호스트 ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "https://youtube.com/",
        "https://www.youtube.com/",
        "https://studio.youtube.com/",
        "https://accounts.google.com/ServiceLogin",
        "https://myaccount.google.com/",
    ],
)
def test_allowed_hosts_reach_factory(url):
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    factory, log, _ = _make_probe_factory(
        [
            {"title": "t", "url": url, "html": "<html></html>"},
        ]
    )
    r = probe_manual_login_flow(
        url=url,
        wait_seconds=3,
        poll_interval_seconds=1,
        allowed_hosts=_YT_ALLOWED_HOSTS,
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    assert r.get("error_code") != "HOST_NOT_ALLOWED"
    gotos = [e for e in log if isinstance(e, tuple) and e and e[0] == "goto"]
    assert len(gotos) == 1
    assert gotos[0][1] == url


# ─── 6. 허용 목록 외 도메인 차단 ─────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/",
        "https://facebook.com/",
        "https://maps.google.com/",  # 허용 목록에 없음 — accounts/myaccount 만.
    ],
)
def test_outside_allowed_hosts_blocked(url):
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    factory, log, _ = _make_probe_factory(
        [
            {"title": "t", "url": url, "html": "<html></html>"},
        ]
    )
    r = probe_manual_login_flow(
        url=url,
        wait_seconds=3,
        poll_interval_seconds=1,
        allowed_hosts=_YT_ALLOWED_HOSTS,
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    assert r["ok"] is False
    assert r["error_code"] == "HOST_NOT_ALLOWED"
    assert log == []


# ─── 7. file/javascript/data URL 차단 ────────────────────────────────────


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
        allowed_hosts=_YT_ALLOWED_HOSTS,
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


# ─── 8. localhost/private IP 기본 차단 ───────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "http://127.0.0.1/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
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
        allowed_hosts=_YT_ALLOWED_HOSTS,
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    assert r["ok"] is False
    assert r["error_code"] == "URL_HOST_BLOCKED"
    assert log == []


# ─── 9. 초기 로그인 키워드/password input 감지 ──────────────────────────


def test_initial_login_required_hint_detected():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    # Google 로그인 화면 (password input + "Sign in" 제목).
    script = [
        {
            "title": "Sign in - Google Accounts",
            "url": "https://accounts.google.com/ServiceLogin",
            "html": _GOOGLE_LOGIN_HTML,
        },
    ]
    factory, _log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://accounts.google.com/ServiceLogin",
        wait_seconds=3,
        poll_interval_seconds=1,
        allowed_hosts=_YT_ALLOWED_HOSTS,
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    # 로그인 변화 없음 → timeout.
    assert r["ok"] is False
    assert r["error_code"] == "LOGIN_TIMEOUT"
    init = r["initial"]
    assert init["login_required_hint"] is True
    # password_input_detected 또는 login_keyword 중 최소 하나.
    assert any(reason in ("password_input_detected", "login_keyword") for reason in init["login_reason"])


# ─── 10. accounts.google.com → www.youtube.com URL 변경 시 완료 ─────────


def test_google_to_youtube_redirect_marks_completed():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    script = [
        {
            "title": "Sign in - Google Accounts",
            "url": "https://accounts.google.com/ServiceLogin?continue=https://www.youtube.com",
            "html": _GOOGLE_LOGIN_HTML,
        },
        {"title": "YouTube", "url": "https://www.youtube.com/", "html": _YT_HOME_HTML},
    ]
    factory, _log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://accounts.google.com/ServiceLogin?continue=https://www.youtube.com",
        wait_seconds=30,
        poll_interval_seconds=1,
        allowed_hosts=_YT_ALLOWED_HOSTS,
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    assert r["ok"] is True
    reasons = r["after"]["login_completion_reason"]
    assert "url_changed" in reasons


# ─── 11. accounts.google.com → studio.youtube.com URL 변경 시 완료 ──────


def test_google_to_studio_redirect_marks_completed():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    script = [
        {
            "title": "Sign in - Google Accounts",
            "url": "https://accounts.google.com/ServiceLogin?continue=https://studio.youtube.com",
            "html": _GOOGLE_LOGIN_HTML,
        },
        {
            "title": "YouTube Studio",
            "url": "https://studio.youtube.com/channel/UCxxxx/videos",
            "html": _STUDIO_HOME_HTML,
        },
    ]
    factory, _log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://accounts.google.com/ServiceLogin?continue=https://studio.youtube.com",
        wait_seconds=30,
        poll_interval_seconds=1,
        allowed_hosts=_YT_ALLOWED_HOSTS,
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    assert r["ok"] is True
    reasons = r["after"]["login_completion_reason"]
    assert "url_changed" in reasons


# ─── 12. password input 사라짐으로 완료 감지 ────────────────────────────


def test_password_disappeared_completes():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    script = [
        {"title": "Sign in", "url": "https://accounts.google.com/v3/signin/identifier", "html": _GOOGLE_LOGIN_HTML},
        # 같은 URL 이지만 password input 이 사라짐 (intermediate step 같은 경우).
        {
            "title": "Verified",
            "url": "https://accounts.google.com/v3/signin/identifier",
            "html": "<html><body><h1>환영합니다</h1></body></html>",
        },
    ]
    factory, _log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://accounts.google.com/v3/signin/identifier",
        wait_seconds=30,
        poll_interval_seconds=1,
        allowed_hosts=_YT_ALLOWED_HOSTS,
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    assert r["ok"] is True
    reasons = r["after"]["login_completion_reason"]
    assert "password_input_disappeared" in reasons


# ─── 13. success_url_contains 로 완료 감지 ───────────────────────────────


def test_success_url_contains_match():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    script = [
        {"title": "t", "url": "https://accounts.google.com/signin", "html": "<html><body></body></html>"},
        {"title": "t", "url": "https://www.youtube.com/feed/subscriptions", "html": "<html><body></body></html>"},
    ]
    factory, _log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://accounts.google.com/signin",
        wait_seconds=30,
        poll_interval_seconds=1,
        success_url_contains=["youtube.com"],
        allowed_hosts=_YT_ALLOWED_HOSTS,
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    assert r["ok"] is True
    reasons = r["after"]["login_completion_reason"]
    assert any(x.startswith("success_url_match:") for x in reasons)


# ─── 14. success_text_hints 로 완료 감지 ─────────────────────────────────


def test_success_text_hints_match():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    script = [
        {"title": "t", "url": "https://www.youtube.com/", "html": "<html><body></body></html>"},
        {
            "title": "YouTube",
            "url": "https://www.youtube.com/",
            "html": "<html><body><h1>Subscriptions</h1></body></html>",
        },
    ]
    factory, _log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://www.youtube.com/",
        wait_seconds=30,
        poll_interval_seconds=1,
        success_text_hints=["Subscriptions"],
        allowed_hosts=_YT_ALLOWED_HOSTS,
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    assert r["ok"] is True
    reasons = r["after"]["login_completion_reason"]
    assert any(x.startswith("success_text_match:") for x in reasons)


# ─── 15. timeout 시 LOGIN_TIMEOUT 반환 ───────────────────────────────────


def test_timeout_returns_login_timeout():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    script = [
        {"title": "Sign in", "url": "https://accounts.google.com/ServiceLogin", "html": _GOOGLE_LOGIN_HTML},
    ]
    factory, _log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://accounts.google.com/ServiceLogin",
        wait_seconds=3,
        poll_interval_seconds=1,
        allowed_hosts=_YT_ALLOWED_HOSTS,
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    assert r["ok"] is False
    assert r["error_code"] == "LOGIN_TIMEOUT"
    assert "last_observation" in r


# ─── 16. 결과에 password value 없음 ──────────────────────────────────────


def test_result_has_no_password_value():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    html = (
        "<html><body><form>"
        "<input name='identifier' type='email' value='someone@example.com'>"
        "<input name='password' type='password' value='secret-yt-pw-xyz'>"
        "</form></body></html>"
    )
    script = [
        {"title": "Sign in", "url": "https://accounts.google.com/signin", "html": html},
    ]
    factory, _log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://accounts.google.com/signin",
        wait_seconds=3,
        poll_interval_seconds=1,
        allowed_hosts=_YT_ALLOWED_HOSTS,
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    assert "secret-yt-pw-xyz" not in repr(r)


# ─── 17. hidden value 없음 ───────────────────────────────────────────────


def test_result_has_no_hidden_value():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    html = (
        "<html><body><form>"
        "<input name='csrf' type='hidden' value='GOOG_csrf_TOKEN_789'>"
        "<input name='password' type='password'>"
        "</form></body></html>"
    )
    script = [
        {"title": "Sign in", "url": "https://accounts.google.com/signin", "html": html},
    ]
    factory, _log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://accounts.google.com/signin",
        wait_seconds=3,
        poll_interval_seconds=1,
        allowed_hosts=_YT_ALLOWED_HOSTS,
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    assert "GOOG_csrf_TOKEN_789" not in repr(r)


# ─── 18. cookie/token/storage_state 호출 없음 ────────────────────────────


def test_no_cookie_or_storage_calls_in_log():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    script = [
        {"title": "t", "url": "https://www.youtube.com/", "html": _YT_HOME_HTML},
        {"title": "t", "url": "https://www.youtube.com/", "html": _YT_HOME_HTML},
    ]
    factory, log, _ = _make_probe_factory(script)
    probe_manual_login_flow(
        url="https://www.youtube.com/",
        wait_seconds=3,
        poll_interval_seconds=1,
        allowed_hosts=_YT_ALLOWED_HOSTS,
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    for entry in log:
        if isinstance(entry, tuple) and entry:
            tag = str(entry[0]).lower()
            for bad in ("storage_state", "cookies", "localstorage", "sessionstorage", "add_cookies"):
                assert bad not in tag, f"forbidden tag in log: {entry}"


# ─── 19. page.click/fill/type/press/select_option 호출 없음 ─────────────


def test_no_interaction_methods_called():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    script = [
        {"title": "t", "url": "https://www.youtube.com/", "html": _YT_HOME_HTML},
        {"title": "t", "url": "https://www.youtube.com/", "html": _YT_HOME_HTML},
    ]
    factory, log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://www.youtube.com/",
        wait_seconds=3,
        poll_interval_seconds=1,
        allowed_hosts=_YT_ALLOWED_HOSTS,
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


# ─── 20. storage_state/cookies/localStorage/sessionStorage 호출 없음 ───


def test_no_session_state_api_calls():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    script = [
        {"title": "t", "url": "https://www.youtube.com/", "html": _YT_HOME_HTML},
    ]
    factory, log, _ = _make_probe_factory(script)
    probe_manual_login_flow(
        url="https://www.youtube.com/",
        wait_seconds=3,
        poll_interval_seconds=1,
        allowed_hosts=_YT_ALLOWED_HOSTS,
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    for entry in log:
        if not (isinstance(entry, tuple) and entry):
            continue
        tag = str(entry[0]).lower()
        assert "storage_state" not in tag
        assert "cookies" not in tag
        assert "localstorage" not in tag
        assert "sessionstorage" not in tag


# ─── 21. page/context/browser close 호출 확인 ────────────────────────────


def test_close_methods_called():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    script = [
        {"title": "t", "url": "https://www.youtube.com/", "html": _YT_HOME_HTML},
    ]
    factory, log, _ = _make_probe_factory(script)
    probe_manual_login_flow(
        url="https://www.youtube.com/",
        wait_seconds=3,
        poll_interval_seconds=1,
        allowed_hosts=_YT_ALLOWED_HOSTS,
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    tags = [e[0] for e in log if isinstance(e, tuple) and e]
    assert "page.close" in tags
    assert "context.close" in tags
    assert "browser.close" in tags


# ─── 22. smoke 스크립트는 pytest 에서 실제 실행하지 않음 ───────────────


def test_smoke_script_not_auto_executed():
    smoke_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "youtube" / "smoke_youtube_manual_login_probe.py"
    assert smoke_path.exists(), "smoke script missing"
    src = smoke_path.read_text(encoding="utf-8")
    assert 'if __name__ == "__main__":' in src or "if __name__ == '__main__':" in src
    # 최상단에서 probe 호출 금지.
    for line in src.splitlines():
        if line.startswith((" ", "\t")) or line.lstrip().startswith("#"):
            continue
        assert "probe_manual_login_flow(" not in line


# ─── 23. 유튜브/구글 계정/비밀번호/토큰 하드코딩 없음 ──────────────────


def test_no_credentials_hardcoded():
    root = Path(__file__).resolve().parent.parent.parent
    smoke_src = (root / "scripts" / "youtube" / "smoke_youtube_manual_login_probe.py").read_text(encoding="utf-8")

    forbidden_tokens = (
        "YOUTUBE_ID",
        "YOUTUBE_PW",
        "GOOGLE_ID",
        "GOOGLE_PW",
        # 구글 세션 쿠키 이름.
        "SID=",
        "HSID=",
        "SSID=",
        "APISID=",
        "SAPISID=",
        "LOGIN_INFO=",
        "Bearer ",
        "sk-",
        # 개인 이메일/사용자명 하드코딩 방어.
        "skyjwshin",
    )
    for tok in forbidden_tokens:
        assert tok not in smoke_src, f"forbidden token {tok!r} in smoke_youtube_manual_login_probe.py"

    # 실제 상호작용 API 도 smoke 스크립트에 없어야 한다.
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
        assert tok not in smoke_src, f"forbidden interaction API {tok!r} in smoke_youtube_manual_login_probe.py"


# ─── 24. YT: success_url_match:youtube.com 단독으로 완료 단정 금지 ─────


class _RecordingInput:
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


def test_yt_success_url_match_alone_does_not_mark_completed():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    # 초기부터 youtube.com 에 있고 password 없음 → 완료 단정 금지.
    script = [
        {"title": "YouTube", "url": "https://www.youtube.com/", "html": "<html><body><h1>홈</h1></body></html>"},
    ]
    factory, _log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://www.youtube.com/",
        wait_seconds=3,
        poll_interval_seconds=1,
        success_url_contains=["youtube.com", "studio.youtube.com"],
        allowed_hosts=_YT_ALLOWED_HOSTS,
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    assert r["login_completed_hint"] is False
    assert r["ok"] is False
    assert r["login_state_hint"] == "already_logged_in_or_public_page"


# ─── 25. YT: accounts.google.com → youtube.com 이동은 완료 후보 ─────────


def test_yt_google_to_youtube_transition_is_completion_candidate():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    script = [
        {
            "title": "Sign in - Google Accounts",
            "url": "https://accounts.google.com/v3/signin/identifier",
            "html": _GOOGLE_LOGIN_HTML,
        },
        {"title": "YouTube", "url": "https://www.youtube.com/", "html": _YT_HOME_HTML},
    ]
    factory, _log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://accounts.google.com/v3/signin/identifier",
        wait_seconds=30,
        poll_interval_seconds=1,
        success_url_contains=["youtube.com"],
        allowed_hosts=_YT_ALLOWED_HOSTS,
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    assert r["ok"] is True
    assert r["login_completed_hint"] is True
    assert r["login_state_hint"] == "manual_login_completed"
    reasons = r.get("login_completion_reason") or []
    # url_changed 또는 password_input_disappeared 중 최소 하나 (강한 근거).
    assert any(
        rx in reasons
        for rx in (
            "url_changed",
            "password_input_disappeared",
            "login_required_hint_cleared",
        )
    ), reasons


# ─── 26. YT: require_user_login_confirm → user_confirmed_login reason ──


def test_yt_user_confirmed_login_adds_reason():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    fake_input = _RecordingInput(responses=[""])
    script = [
        {"title": "YouTube", "url": "https://www.youtube.com/", "html": _YT_HOME_HTML},
    ]
    factory, _log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://www.youtube.com/",
        wait_seconds=3,
        poll_interval_seconds=1,
        success_url_contains=["youtube.com"],
        allowed_hosts=_YT_ALLOWED_HOSTS,
        require_user_login_confirm=True,
        _browser_factory=factory,
        _clock=_FakeTime(),
        _input_reader=fake_input,
    )
    assert r["login_confirmed_by_user"] is True
    assert r["login_completed_hint"] is True
    assert r["login_state_hint"] == "manual_login_completed"
    reasons = r.get("login_completion_reason") or []
    assert "user_confirmed_login" in reasons


# ─── 27. YT: already_logged_in_or_public_page 상태 구분 ─────────────────


def test_yt_already_logged_in_state():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    script = [
        {"title": "YouTube", "url": "https://www.youtube.com/", "html": "<html><body><h1>홈</h1></body></html>"},
    ]
    factory, _log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://www.youtube.com/",
        wait_seconds=3,
        poll_interval_seconds=1,
        success_url_contains=["youtube.com", "studio.youtube.com"],
        allowed_hosts=_YT_ALLOWED_HOSTS,
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    assert r["login_state_hint"] == "already_logged_in_or_public_page"
    assert r["login_completed_hint"] is False
    assert r["error_code"] == "LOGIN_NOT_CONFIRMED"


# ─── 28. YT: password input 있었다가 사라지면 완료 후보 ────────────────


def test_yt_password_disappeared_is_completion_candidate():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    script = [
        {
            "title": "Sign in - Google Accounts",
            "url": "https://accounts.google.com/v3/signin/challenge/pwd",
            "html": _GOOGLE_LOGIN_HTML,
        },
        {
            "title": "Google",
            "url": "https://accounts.google.com/v3/signin/challenge/pwd",
            "html": "<html><body><h1>환영합니다</h1></body></html>",
        },
    ]
    factory, _log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://accounts.google.com/v3/signin/challenge/pwd",
        wait_seconds=30,
        poll_interval_seconds=1,
        allowed_hosts=_YT_ALLOWED_HOSTS,
        _browser_factory=factory,
        _clock=_FakeTime(),
    )
    assert r["ok"] is True
    reasons = r.get("login_completion_reason") or []
    assert "password_input_disappeared" in reasons
    assert r["login_state_hint"] == "manual_login_completed"


# ─── 29. YT: require_visible_confirm → 사용자 확인 전에 polling 금지 ──


def test_yt_require_visible_confirm_blocks_polling():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    fake_input = _RecordingInput(raise_on=[0])
    clock = _FakeTime()
    script = [
        {"title": "YouTube", "url": "https://www.youtube.com/", "html": _YT_HOME_HTML},
    ]
    factory, _log, _ = _make_probe_factory(script)
    r = probe_manual_login_flow(
        url="https://www.youtube.com/",
        wait_seconds=30,
        poll_interval_seconds=1,
        allowed_hosts=_YT_ALLOWED_HOSTS,
        require_visible_confirm=True,
        _browser_factory=factory,
        _clock=clock,
        _input_reader=fake_input,
    )
    assert r["error_code"] == "VISIBILITY_NOT_CONFIRMED"
    assert r["visible_confirmed_by_user"] is False
    assert clock.sleeps == []


# ─── 30. YT: keep_open → 종료 전 Enter 기다림 ──────────────────────────


def test_yt_keep_open_prompts_before_close():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    fake_input = _RecordingInput(responses=[""])
    script = [
        {"title": "YouTube", "url": "https://www.youtube.com/", "html": _YT_HOME_HTML},
    ]
    factory, log, _ = _make_probe_factory(script)
    probe_manual_login_flow(
        url="https://www.youtube.com/",
        wait_seconds=3,
        poll_interval_seconds=1,
        success_url_contains=["youtube.com"],
        allowed_hosts=_YT_ALLOWED_HOSTS,
        keep_open=True,
        _browser_factory=factory,
        _clock=_FakeTime(),
        _input_reader=fake_input,
    )
    # keep_open 프롬프트가 호출되었고, browser.close 도 이후에 호출되었다.
    assert any("닫" in p for p in fake_input.prompts), fake_input.prompts
    tags = [e[0] for e in log if isinstance(e, tuple) and e]
    assert "browser.close" in tags


# ─── 31. YT: 새 옵션이 있어도 자동 클릭/입력/쿠키 수집 없음 유지 ───────


def test_yt_no_auto_login_or_cookies_with_new_options():
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    fake_input = _RecordingInput(responses=["", "", ""])
    script = [
        {"title": "Sign in", "url": "https://accounts.google.com/signin", "html": _GOOGLE_LOGIN_HTML},
        {"title": "YouTube", "url": "https://www.youtube.com/", "html": _YT_HOME_HTML},
    ]
    factory, log, _ = _make_probe_factory(script)
    probe_manual_login_flow(
        url="https://accounts.google.com/signin",
        wait_seconds=30,
        poll_interval_seconds=1,
        success_url_contains=["youtube.com"],
        allowed_hosts=_YT_ALLOWED_HOSTS,
        require_visible_confirm=True,
        require_user_login_confirm=True,
        keep_open=True,
        browser_channel="chrome",
        viewport={"width": 1280, "height": 800},
        slow_mo_ms=100,
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


# ─── 32. smoke 스크립트에 새 옵션이 노출돼 있음 ─────────────────────────


def test_smoke_script_exposes_new_options():
    smoke_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "youtube" / "smoke_youtube_manual_login_probe.py"
    src = smoke_path.read_text(encoding="utf-8")
    assert "--require-visible-confirm" in src
    assert "--require-user-login-confirm" in src
    assert "--keep-open" in src
    assert "--browser-channel" in src

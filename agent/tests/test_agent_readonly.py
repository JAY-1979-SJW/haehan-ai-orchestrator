"""로컬 에이전트 read-only 테스트.

필수 검증 항목:
1) 허용 action (ping, get_system_info, open_page_readonly, inspect_page) 만 실행
2) 비허용 action 차단 (click / type / submit / login / download …)
3) localhost / private IP / file:// 차단
4) inspect_page 정상 반환 (final_url/title/snippet/input/button/link count)
5) snippet 1000자 제한
6) Playwright timeout 안전 처리 (크래시 없이 error 반환)
7) Playwright 예외 안전 처리
8) 로그에 민감정보 미기록 (password/token/cookie/authorization/session)
9) 브라우저 동시 실행 1개 제한
"""
from __future__ import annotations

import json
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


# ── Playwright 테스트 더블 ───────────────────────────────────────────
class _FakeTimeout(Exception):
    """Playwright TimeoutError 대체."""


class _FakeResponse:
    def __init__(self, status: int = 200):
        self.status = status


class _FakeLocator:
    def __init__(self, *, text: str = "", count: int = 0):
        self._text = text
        self._count = count

    def inner_text(self, timeout=None):  # noqa: ARG002
        return self._text

    def count(self):
        return self._count


class _FakePage:
    def __init__(
        self,
        *,
        goto_raises: bool = False,
        resolved_url: str = "https://www.law.go.kr/resolved",
        title_val: str = "테스트 타이틀",
        body_val: str = "본문 샘플",
        input_count: int = 3,
        button_count: int = 2,
        link_count: int = 7,
    ):
        self.url = resolved_url
        self._goto_raises = goto_raises
        self._title = title_val
        self._body = body_val
        self._input_count = input_count
        self._button_count = button_count
        self._link_count = link_count

    def goto(self, *_a, **_kw):
        if self._goto_raises:
            raise _FakeTimeout("goto timeout")
        return _FakeResponse()

    def title(self):
        return self._title

    def locator(self, selector: str):
        if selector == "body":
            return _FakeLocator(text=self._body)
        if selector == "input":
            return _FakeLocator(count=self._input_count)
        if selector == "button":
            return _FakeLocator(count=self._button_count)
        if selector == "a":
            return _FakeLocator(count=self._link_count)
        return _FakeLocator()

    def close(self):
        pass


class _FakeContext:
    def __init__(self, page: _FakePage):
        self._page = page

    def new_page(self):
        return self._page

    def close(self):
        pass


class _FakeBrowser:
    def __init__(self, page: _FakePage):
        self._ctx = _FakeContext(page)

    def new_context(self, **_):
        return self._ctx

    def close(self):
        pass


class _FakeChromium:
    def __init__(self, page: _FakePage):
        self._page = page

    def launch(self, **_):
        return _FakeBrowser(self._page)


class _FakePlaywrightCtx:
    def __init__(self, page: _FakePage):
        self.chromium = _FakeChromium(page)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _install_fake_playwright(monkeypatch, *, page: _FakePage):
    fake_mod = types.ModuleType("playwright.sync_api")
    fake_mod.sync_playwright = lambda: _FakePlaywrightCtx(page)
    fake_mod.TimeoutError = _FakeTimeout
    fake_pkg = types.ModuleType("playwright")
    monkeypatch.setitem(sys.modules, "playwright", fake_pkg)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_mod)


# ── 공통 픽스처 ──────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _isolated_log(tmp_path, monkeypatch):
    """각 테스트마다 로그 경로/브라우저 락을 격리 초기화."""
    from agent import config as _cfg
    from agent import runner as _runner
    monkeypatch.setattr(_cfg, "AGENT_LOG_PATH",
                        tmp_path / "agent_actions.jsonl")
    # 테스트 간 혹시 남은 락 해제 (defensive)
    if _runner._browser_lock.locked():
        try:
            _runner._browser_lock.release()
        except RuntimeError:
            pass
    yield
    if _runner._browser_lock.locked():
        try:
            _runner._browser_lock.release()
        except RuntimeError:
            pass


def _read_log(tmp_path):
    p = tmp_path / "agent_actions.jsonl"
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").strip().splitlines()]


# ══════════════════════════════════════════════════════════════════════
# 1) 허용 action 실행
# ══════════════════════════════════════════════════════════════════════
def test_ping_returns_ok():
    from agent import app
    out = app.run("ping")
    assert out["ok"] is True
    assert out["action"] == "ping"
    assert out["data"]["pong"] is True
    assert "fetched_at" in out["data"]
    assert out["error"] is None


def test_get_system_info_returns_expected_fields():
    from agent import app
    out = app.run("get_system_info")
    assert out["ok"] is True
    d = out["data"]
    for k in ("os", "os_release", "hostname", "python_version",
              "playwright_available", "chromium_available", "fetched_at"):
        assert k in d, f"missing field: {k}"


def test_open_page_readonly_runs_without_inspection(monkeypatch):
    from agent import app
    page = _FakePage(resolved_url="https://www.law.go.kr/final",
                     title_val="홈")
    _install_fake_playwright(monkeypatch, page=page)
    out = app.run("open_page_readonly", url="https://www.law.go.kr/")
    assert out["ok"] is True, out
    d = out["data"]
    assert d["url"] == "https://www.law.go.kr/"
    assert d["final_url"] == "https://www.law.go.kr/final"
    assert d["title"] == "홈"
    # open_page_readonly 는 snippet/카운트를 수집하지 않는다
    assert "snippet" not in d
    assert "input_count" not in d


# ══════════════════════════════════════════════════════════════════════
# 2) 비허용 action 차단
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("bad_action", [
    "click_button",
    "type_text",
    "submit_form",
    "login",
    "signup",
    "download_file",
    "upload_file",
    "select_option",
    "check_box",
    "",
    "FETCH_WEB_PAGE",  # 대소문자 정확히 맞아야 허용
])
def test_non_allowed_actions_are_blocked(bad_action):
    from agent import app
    out = app.run(bad_action, url="https://www.law.go.kr/")
    assert out["ok"] is False, out
    assert out["error"] == app.ERR_ACTION_NOT_ALLOWED


def test_non_allowed_action_is_logged_with_reason(tmp_path):
    from agent import app
    app.run("click_button", url="https://www.law.go.kr/")
    log = _read_log(tmp_path)
    assert log, "log file should have at least one entry"
    last = log[-1]
    assert last["action"] == "click_button"
    assert last["ok"] is False
    assert last["blocked_reason"] == app.ERR_ACTION_NOT_ALLOWED


# ══════════════════════════════════════════════════════════════════════
# 3) localhost / private IP / file:// 차단
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("bad_url,expect_marker", [
    ("http://localhost/", "blocked_host:localhost"),
    ("http://localhost:8080/", "blocked_host:localhost"),
    ("http://127.0.0.1/", "blocked_private_ip:127.0.0.1"),
    ("http://10.0.0.1/", "blocked_private_ip:10.0.0.1"),
    ("http://172.16.0.1/", "blocked_private_ip:172.16.0.1"),
    ("http://192.168.1.1/", "blocked_private_ip:192.168.1.1"),
    ("http://[::1]/", "blocked_private_ip:::1"),
    ("file:///etc/passwd", "scheme_not_allowed:file"),
    ("ftp://ftp.example.com/", "scheme_not_allowed:ftp"),
    ("data:text/html,x", "scheme_not_allowed:data"),
    ("javascript:alert(1)", "scheme_not_allowed:javascript"),
    ("", "empty_url"),
    ("not-a-url", "scheme_not_allowed:none"),
])
def test_url_policy_blocks_dangerous_targets(monkeypatch, bad_url, expect_marker):
    """브라우저가 실행되지 않고 URL 단계에서 차단되는지 확인."""
    from agent import app
    # Playwright 가 실수로라도 기동되지 않도록 sync_api 를 None 으로
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    out = app.run("open_page_readonly", url=bad_url)
    assert out["ok"] is False
    assert out["error"].startswith(app.ERR_URL_NOT_ALLOWED)
    assert expect_marker in out["error"], out


def test_inspect_page_blocks_localhost(monkeypatch):
    from agent import app
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    out = app.run("inspect_page", url="http://localhost:8080/")
    assert out["ok"] is False
    assert app.ERR_URL_NOT_ALLOWED in out["error"]
    assert "blocked_host:localhost" in out["error"]


# ══════════════════════════════════════════════════════════════════════
# 4) inspect_page 정상 반환
# ══════════════════════════════════════════════════════════════════════
def test_inspect_page_returns_all_readonly_fields(monkeypatch):
    from agent import app
    page = _FakePage(
        resolved_url="https://www.law.go.kr/LSW/main.html",
        title_val="국가법령정보센터",
        body_val="본문 샘플입니다.",
        input_count=5, button_count=4, link_count=17,
    )
    _install_fake_playwright(monkeypatch, page=page)
    out = app.run("inspect_page", url="https://www.law.go.kr/")
    assert out["ok"] is True, out
    d = out["data"]
    assert d["url"] == "https://www.law.go.kr/"
    assert d["final_url"] == "https://www.law.go.kr/LSW/main.html"
    assert d["title"] == "국가법령정보센터"
    assert d["snippet"] == "본문 샘플입니다."
    assert d["input_count"] == 5
    assert d["button_count"] == 4
    assert d["link_count"] == 17
    assert "fetched_at" in d and d["fetched_at"].endswith("+00:00")


# ══════════════════════════════════════════════════════════════════════
# 5) snippet 1000자 제한
# ══════════════════════════════════════════════════════════════════════
def test_inspect_page_snippet_is_truncated_to_1000(monkeypatch):
    from agent import app
    page = _FakePage(body_val="가" * 5000)
    _install_fake_playwright(monkeypatch, page=page)
    out = app.run("inspect_page", url="https://www.law.go.kr/")
    assert out["ok"] is True
    assert len(out["data"]["snippet"]) == 1000


# ══════════════════════════════════════════════════════════════════════
# 6) Playwright timeout 안전 처리
# ══════════════════════════════════════════════════════════════════════
def test_inspect_page_timeout_is_handled_safely(monkeypatch):
    from agent import app
    page = _FakePage(goto_raises=True)
    _install_fake_playwright(monkeypatch, page=page)
    out = app.run("inspect_page", url="https://www.law.go.kr/slow")
    assert out["ok"] is False
    assert out["error"] == "playwright_timeout"
    assert out["data"]["url"] == "https://www.law.go.kr/slow"


# ══════════════════════════════════════════════════════════════════════
# 7) Playwright 일반 예외 안전 처리
# ══════════════════════════════════════════════════════════════════════
def test_inspect_page_exception_is_handled_safely(monkeypatch):
    from agent import app

    def _raise(*_a, **_kw):
        raise RuntimeError("boom")

    fake_pkg = types.ModuleType("playwright")
    fake_mod = types.ModuleType("playwright.sync_api")
    fake_mod.sync_playwright = _raise
    fake_mod.TimeoutError = _FakeTimeout
    monkeypatch.setitem(sys.modules, "playwright", fake_pkg)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_mod)

    out = app.run("inspect_page", url="https://www.law.go.kr/")
    assert out["ok"] is False
    assert "playwright_error" in out["error"]


def test_missing_playwright_returns_clean_error(monkeypatch):
    from agent import app
    # import 가 실패하도록 sync_api 를 None 으로 주입
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    out = app.run("inspect_page", url="https://www.law.go.kr/")
    assert out["ok"] is False
    # None 모듈 → ImportError 처리 경로 or 속성 없음 경로. 어느 쪽이든 메시지는 깨끗함.
    assert out["error"]
    assert out["error"].startswith(("playwright_not_installed", "playwright_error"))


# ══════════════════════════════════════════════════════════════════════
# 8) 로그에 민감정보 미기록
# ══════════════════════════════════════════════════════════════════════
def test_log_does_not_record_sensitive_parameters(tmp_path, monkeypatch):
    from agent import app
    page = _FakePage()
    _install_fake_playwright(monkeypatch, page=page)

    secret_pw = "TOPSECRETPASSWORD-12345"
    secret_token = "BEARER-ABCDEF-SESSION-XYZ"
    secret_cookie = "SESSIONID=abc; csrf=xyz"

    app.run(
        "open_page_readonly",
        url="https://www.law.go.kr/",
        password=secret_pw,
        token=secret_token,
        cookie=secret_cookie,
        authorization="Bearer " + secret_token,
        session_id=secret_token,
    )

    raw = (tmp_path / "agent_actions.jsonl").read_text(encoding="utf-8")
    assert secret_pw not in raw
    assert secret_token not in raw
    assert secret_cookie not in raw
    # 키 자체도 저장되지 않아야 한다
    for banned in ("password", "token", "cookie", "authorization", "session"):
        assert banned not in raw.lower()


def test_log_strips_userinfo_from_url(tmp_path, monkeypatch):
    from agent import app
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    # userinfo 가 들어간 URL → validate_url 로직과 무관하게 로그에서 제거되어야
    app.run(
        "open_page_readonly",
        url="https://user:topsecretpw@www.law.go.kr/",
    )
    raw = (tmp_path / "agent_actions.jsonl").read_text(encoding="utf-8")
    assert "topsecretpw" not in raw
    assert "user:" not in raw


# ══════════════════════════════════════════════════════════════════════
# 9) 브라우저 동시 실행 1개 제한
# ══════════════════════════════════════════════════════════════════════
def test_concurrent_browser_limit(monkeypatch):
    from agent import app, runner
    # 다른 스레드가 이미 락을 잡고 있다고 가정 — 실제로는 단순히 lock 을 수동 점유
    page = _FakePage()
    _install_fake_playwright(monkeypatch, page=page)
    acquired = runner._browser_lock.acquire(blocking=False)
    assert acquired
    try:
        out = app.run("inspect_page", url="https://www.law.go.kr/")
    finally:
        runner._browser_lock.release()

    assert out["ok"] is False
    assert out["error"] == app.ERR_CONCURRENT_LIMIT
    assert out["data"]["url"] == "https://www.law.go.kr/"


def test_browser_lock_released_after_run(monkeypatch):
    """정상 실행 후 lock 이 반드시 해제된다."""
    from agent import app, runner
    page = _FakePage()
    _install_fake_playwright(monkeypatch, page=page)
    out = app.run("inspect_page", url="https://www.law.go.kr/")
    assert out["ok"] is True
    assert not runner._browser_lock.locked(), "browser lock leaked after success"


def test_browser_lock_released_after_exception(monkeypatch):
    """연결된 세션 내부 예외가 나더라도 lock 은 해제된다."""
    from agent import app, runner

    def _raise(*_a, **_kw):
        raise RuntimeError("boom")
    fake_pkg = types.ModuleType("playwright")
    fake_mod = types.ModuleType("playwright.sync_api")
    fake_mod.sync_playwright = _raise
    fake_mod.TimeoutError = _FakeTimeout
    monkeypatch.setitem(sys.modules, "playwright", fake_pkg)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_mod)

    out = app.run("inspect_page", url="https://www.law.go.kr/")
    assert out["ok"] is False
    assert not runner._browser_lock.locked(), "browser lock leaked after exception"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

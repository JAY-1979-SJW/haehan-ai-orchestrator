"""login_with_secret 테스트 (로그인 성공 여부 확인까지만).

필수 검증
1) 저장된 시크릿으로 로그인 성공
2) 없는 site_key (profile 미등록) 안전 실패
3) profile 있으나 시크릿 없음 안전 실패
4) profile 없는 사이트 차단 (site_profile_not_found)
5) 허용되지 않은 host 차단 (host_not_allowed)
6) password 가 agent 로그 어디에도 기록되지 않음
7) 성공/실패 결과 포맷 검증
8) 로그인 후 추가 동작 미수행 보장 (fill x2, click x1 외 호출 없음)
"""
from __future__ import annotations

import json
import os
import sys
import types

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


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


class _FakeLoginPage:
    """로그인 흐름용 테스트 더블.

    모든 호출을 ``self.actions`` 에 기록하되, fill 의 value 는 저장하지 않는다.
    그래야 테스트 내에서 우연히라도 평문 비밀번호가 흘러가지 않는다.
    """

    def __init__(
        self,
        *,
        post_submit_url: str = "https://example.com/home",
        body_text: str = "Welcome",
        visible_selectors: tuple[str, ...] = (),
        raise_on: str = "",
        initial_url: str = "https://example.com/login",
    ):
        self.url = initial_url
        self._post_submit_url = post_submit_url
        self._body_text = body_text
        self._visible = set(visible_selectors)
        self._raise_on = raise_on
        self.actions: list[tuple] = []

    def _maybe_raise(self, key: str) -> None:
        if self._raise_on == key:
            raise _FakeTimeout(f"timeout on {key}")

    def goto(self, url, wait_until=None, timeout=None):  # noqa: ARG002
        self.actions.append(("goto", url))
        self._maybe_raise("goto")
        self.url = url
        return _FakeResponse()

    def fill(self, selector, value, timeout=None):  # noqa: ARG002
        # value 는 절대 actions 에 기록하지 않는다.
        self.actions.append(("fill", selector))
        self._maybe_raise(f"fill:{selector}")

    def click(self, selector, timeout=None):  # noqa: ARG002
        self.actions.append(("click", selector))
        self._maybe_raise("click")
        self.url = self._post_submit_url

    def wait_for_load_state(self, *a, **kw):  # noqa: ARG002
        self.actions.append(("wait_for_load_state",))

    def locator(self, selector: str):
        self.actions.append(("locator", selector))
        if selector == "body":
            return _FakeLocator(text=self._body_text)
        if selector in self._visible:
            return _FakeLocator(count=1)
        return _FakeLocator(count=0)

    def title(self):
        return "title"

    def close(self):
        pass


class _FakeContext:
    def __init__(self, page):
        self._page = page

    def new_page(self):
        return self._page

    def close(self):
        pass


class _FakeBrowser:
    def __init__(self, page):
        self._ctx = _FakeContext(page)

    def new_context(self, **_):
        return self._ctx

    def close(self):
        pass


class _FakeChromium:
    def __init__(self, page):
        self._page = page

    def launch(self, **_):
        return _FakeBrowser(self._page)


class _FakePlaywrightCtx:
    def __init__(self, page):
        self.chromium = _FakeChromium(page)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _install_fake_playwright(monkeypatch, *, page):
    fake_mod = types.ModuleType("playwright.sync_api")
    fake_mod.sync_playwright = lambda: _FakePlaywrightCtx(page)
    fake_mod.TimeoutError = _FakeTimeout
    fake_pkg = types.ModuleType("playwright")
    monkeypatch.setitem(sys.modules, "playwright", fake_pkg)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_mod)


# ── 공통 픽스처 ──────────────────────────────────────────────────────
PW = "TOP-SECRET-LOGIN-PW-42-UNIQUE"
PW_ALT = "ALT-PW-999-UNIQUE"
USER = "alice@example.com"


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    from agent import config as _cfg
    from agent import runner as _runner
    from agent import site_profiles as _sp

    monkeypatch.setenv("AGENT_SECRETS_DIR", str(tmp_path / "secrets"))
    monkeypatch.setattr(
        _cfg, "AGENT_LOG_PATH", tmp_path / "agent_actions.jsonl"
    )
    _sp._REGISTRY.clear()
    if _runner._browser_lock.locked():
        try:
            _runner._browser_lock.release()
        except RuntimeError:
            pass
    yield
    _sp._REGISTRY.clear()
    if _runner._browser_lock.locked():
        try:
            _runner._browser_lock.release()
        except RuntimeError:
            pass


def _register_sample_profile(
    *,
    site_key: str = "sample",
    login_url: str = "https://example.com/login",
    success_check=None,
    allowed_hosts: tuple[str, ...] = ("example.com",),
):
    from agent import site_profiles as sp

    if success_check is None:
        success_check = sp.SuccessCheck(kind="url", value="/home")
    profile = sp.SiteProfile(
        site_key=site_key,
        login_url=login_url,
        username_selector="#user",
        password_selector="#pass",
        submit_selector="#submit",
        success_check=success_check,
        allowed_hosts=allowed_hosts,
    )
    sp.register_profile(profile)
    return profile


def _log_path(tmp_path):
    return tmp_path / "agent_actions.jsonl"


# ══════════════════════════════════════════════════════════════════════
# 1) 저장된 시크릿으로 로그인 성공
# ══════════════════════════════════════════════════════════════════════
def test_login_success_with_stored_secret(monkeypatch):
    from agent import app
    from agent.secrets import store as secret_store

    _register_sample_profile()
    secret_store.save_secret("sample", USER, PW, note="memo")
    page = _FakeLoginPage(post_submit_url="https://example.com/home")
    _install_fake_playwright(monkeypatch, page=page)

    out = app.run("login_with_secret", site_key="sample")

    assert out["ok"] is True, out
    assert out["error"] is None
    d = out["data"]
    assert d["site_key"] == "sample"
    assert d["login_url"] == "https://example.com/login"
    assert d["final_url"] == "https://example.com/home"
    assert d["login_success"] is True
    assert d["checked_by"] == "url"
    assert "fetched_at" in d and d["fetched_at"]


def test_login_success_via_selector_check(monkeypatch):
    from agent import app, site_profiles as sp
    from agent.secrets import store as secret_store

    _register_sample_profile(
        success_check=sp.SuccessCheck(kind="selector", value="nav.user-menu"),
    )
    secret_store.save_secret("sample", USER, PW)
    page = _FakeLoginPage(
        post_submit_url="https://example.com/home",
        visible_selectors=("nav.user-menu",),
    )
    _install_fake_playwright(monkeypatch, page=page)

    out = app.run("login_with_secret", site_key="sample")
    assert out["ok"] is True, out
    assert out["data"]["login_success"] is True
    assert out["data"]["checked_by"] == "selector"


def test_login_success_via_text_check(monkeypatch):
    from agent import app, site_profiles as sp
    from agent.secrets import store as secret_store

    _register_sample_profile(
        success_check=sp.SuccessCheck(kind="text", value="로그아웃"),
    )
    secret_store.save_secret("sample", USER, PW)
    page = _FakeLoginPage(
        post_submit_url="https://example.com/home",
        body_text="환영합니다 alice. 로그아웃 링크.",
    )
    _install_fake_playwright(monkeypatch, page=page)

    out = app.run("login_with_secret", site_key="sample")
    assert out["ok"] is True, out
    assert out["data"]["login_success"] is True
    assert out["data"]["checked_by"] == "text"


# ══════════════════════════════════════════════════════════════════════
# 2) 없는 site_key (profile 미등록)
# ══════════════════════════════════════════════════════════════════════
def test_unknown_site_key_is_rejected_without_browser(monkeypatch):
    from agent import app

    # Playwright 가 실수로라도 기동되지 않아야 한다
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)

    out = app.run("login_with_secret", site_key="does_not_exist")
    assert out["ok"] is False
    assert out["error"] == "site_profile_not_found"
    assert out["data"]["login_success"] is False
    assert out["data"]["site_key"] == "does_not_exist"


def test_empty_site_key_is_rejected():
    from agent import app

    out = app.run("login_with_secret", site_key="")
    assert out["ok"] is False
    assert out["error"] == app.ERR_SITE_KEY_REQUIRED
    assert out["data"]["login_success"] is False


# ══════════════════════════════════════════════════════════════════════
# 3) profile 있으나 시크릿 없음
# ══════════════════════════════════════════════════════════════════════
def test_missing_secret_is_safely_rejected(monkeypatch):
    from agent import app

    _register_sample_profile()
    # 시크릿은 저장하지 않음
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)

    out = app.run("login_with_secret", site_key="sample")
    assert out["ok"] is False
    assert out["error"] == "secret_not_found"
    assert out["data"]["login_success"] is False
    assert out["data"]["site_key"] == "sample"


# ══════════════════════════════════════════════════════════════════════
# 4) profile 없는 사이트 차단 (site_profile_not_found)
#    — 2) 와 동일한 보증을 "시크릿은 있지만 프로필 없음" 각도에서 재검증
# ══════════════════════════════════════════════════════════════════════
def test_profile_missing_even_with_secret_is_rejected(monkeypatch):
    from agent import app
    from agent.secrets import store as secret_store

    secret_store.save_secret("ghost_site", USER, PW)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)

    out = app.run("login_with_secret", site_key="ghost_site")
    assert out["ok"] is False
    assert out["error"] == "site_profile_not_found"


# ══════════════════════════════════════════════════════════════════════
# 5) 허용되지 않은 host 차단
# ══════════════════════════════════════════════════════════════════════
def test_host_not_allowed_is_blocked(monkeypatch):
    from agent import app
    from agent.secrets import store as secret_store

    _register_sample_profile(
        login_url="https://evil.example.com/login",
        allowed_hosts=("whitelisted.example.com",),
    )
    secret_store.save_secret("sample", USER, PW)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)

    out = app.run("login_with_secret", site_key="sample")
    assert out["ok"] is False
    assert out["error"] == "host_not_allowed"
    assert out["data"]["login_success"] is False


def test_localhost_login_url_blocked_by_policy(monkeypatch):
    from agent import app
    from agent.secrets import store as secret_store

    _register_sample_profile(
        login_url="http://localhost:8080/login",
        allowed_hosts=("localhost",),
    )
    secret_store.save_secret("sample", USER, PW)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)

    out = app.run("login_with_secret", site_key="sample")
    assert out["ok"] is False
    assert out["error"].startswith("login_url_not_allowed")
    assert "blocked_host:localhost" in out["error"]


# ══════════════════════════════════════════════════════════════════════
# 6) password 로그 미노출
# ══════════════════════════════════════════════════════════════════════
def test_password_never_appears_in_agent_log(monkeypatch, tmp_path):
    from agent import app
    from agent.secrets import store as secret_store

    _register_sample_profile()
    secret_store.save_secret("sample", USER, PW)
    page = _FakeLoginPage(post_submit_url="https://example.com/home")
    _install_fake_playwright(monkeypatch, page=page)

    app.run("login_with_secret", site_key="sample")

    raw = _log_path(tmp_path).read_text(encoding="utf-8")
    assert PW not in raw
    assert USER not in raw
    for banned in ("password", "token", "cookie", "authorization", "session"):
        assert banned not in raw.lower(), f"banned key '{banned}' leaked"


def test_failed_login_log_does_not_leak_password(monkeypatch, tmp_path):
    from agent import app, site_profiles as sp
    from agent.secrets import store as secret_store

    _register_sample_profile(
        success_check=sp.SuccessCheck(kind="url", value="/home"),
    )
    secret_store.save_secret("sample", USER, PW)
    # 제출 후에도 여전히 login URL 에 머물면 실패로 판정
    page = _FakeLoginPage(post_submit_url="https://example.com/login")
    _install_fake_playwright(monkeypatch, page=page)

    out = app.run("login_with_secret", site_key="sample")
    assert out["ok"] is False
    assert out["error"] == app.ERR_LOGIN_FAILED
    assert out["data"]["login_success"] is False

    raw = _log_path(tmp_path).read_text(encoding="utf-8")
    assert PW not in raw
    assert USER not in raw


# ══════════════════════════════════════════════════════════════════════
# 7) 결과 포맷 (성공/실패 모두)
# ══════════════════════════════════════════════════════════════════════
def test_success_result_format(monkeypatch):
    from agent import app
    from agent.secrets import store as secret_store

    _register_sample_profile()
    secret_store.save_secret("sample", USER, PW)
    page = _FakeLoginPage(post_submit_url="https://example.com/home")
    _install_fake_playwright(monkeypatch, page=page)

    out = app.run("login_with_secret", site_key="sample")
    assert set(out.keys()) == {"ok", "action", "data", "error"}
    assert out["action"] == "login_with_secret"
    assert out["ok"] is True
    assert out["error"] is None
    d = out["data"]
    required = {"site_key", "login_url", "final_url",
                "login_success", "checked_by", "fetched_at"}
    assert required.issubset(d.keys())
    assert "password" not in d
    assert "username" not in d


def test_failure_result_format(monkeypatch):
    from agent import app
    from agent.secrets import store as secret_store

    _register_sample_profile()
    secret_store.save_secret("sample", USER, PW)
    # 제출 후에도 login URL 유지 → 성공 조건(/home) 실패
    page = _FakeLoginPage(post_submit_url="https://example.com/login")
    _install_fake_playwright(monkeypatch, page=page)

    out = app.run("login_with_secret", site_key="sample")
    assert set(out.keys()) == {"ok", "action", "data", "error"}
    assert out["ok"] is False
    assert out["error"] == app.ERR_LOGIN_FAILED
    d = out["data"]
    assert d["site_key"] == "sample"
    assert d["login_url"] == "https://example.com/login"
    assert d["login_success"] is False
    assert "password" not in d


# ══════════════════════════════════════════════════════════════════════
# 8) 로그인 후 추가 동작 미수행 보장
# ══════════════════════════════════════════════════════════════════════
def test_no_actions_beyond_login_minimum(monkeypatch):
    from agent import app
    from agent.secrets import store as secret_store

    _register_sample_profile()
    secret_store.save_secret("sample", USER, PW)
    page = _FakeLoginPage(post_submit_url="https://example.com/home")
    _install_fake_playwright(monkeypatch, page=page)

    app.run("login_with_secret", site_key="sample")

    methods = [a[0] for a in page.actions]
    # 필수 최소 동작: goto 1회 + fill 2회(user/pass) + click 1회
    assert methods.count("goto") == 1
    assert methods.count("fill") == 2, f"fill must be exactly 2, got {methods}"
    assert methods.count("click") == 1, (
        f"submit click must be exactly 1, got {methods}"
    )

    # selector 는 username/password/submit 만 등장해야 하고 그 외는 금지
    fill_targets = [a[1] for a in page.actions if a[0] == "fill"]
    click_targets = [a[1] for a in page.actions if a[0] == "click"]
    assert set(fill_targets) == {"#user", "#pass"}
    assert click_targets == ["#submit"]

    # 금지된 메서드가 절대 호출되지 않아야 한다
    banned_methods = {
        "type", "press", "check", "uncheck", "select_option",
        "set_input_files", "screenshot", "evaluate",
        "expose_function", "add_init_script", "route",
    }
    for m in methods:
        assert m not in banned_methods, f"forbidden method called: {m}"


# ══════════════════════════════════════════════════════════════════════
# 추가 방어: 허용되지 않은 다른 action 은 여전히 차단
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("bad", [
    "click_button", "type_text", "submit_form", "signup",
    "download_file", "upload_file", "",
])
def test_non_login_write_actions_still_blocked(bad):
    from agent import app
    out = app.run(bad, site_key="sample")
    assert out["ok"] is False
    assert out["error"] == app.ERR_ACTION_NOT_ALLOWED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

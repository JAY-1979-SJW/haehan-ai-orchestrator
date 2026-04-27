"""inspect_after_login 테스트 (로그인 후 읽기 전용 탐색).

필수 검증
1) 로그인 후 inspect 성공
2) profile 없는 사이트 차단
3) secret 없는 사이트 차단
4) target_url host 미허용 차단
5) target_url path 미허용 차단(정책 적용 시)
6) 로그인 실패 시 inspect 미진행 (target 이동 0회)
7) 결과 포맷 검증 (성공/실패)
8) 로그인 후 추가 click/fill/submit 미수행 보장
9) 로그 민감정보 미노출
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
    pass


class _FakeResponse:
    def __init__(self, status: int = 200):
        self.status = status


class _FakeLocator:
    """리스트 반복(nth) 과 속성 읽기(get_attribute) 까지 지원.

    - ``items`` 가 설정되면 count/nth 는 해당 리스트 기반으로 동작.
    - ``item`` 이 설정되면 단일 요소 locator 로, inner_text / get_attribute 를 해당
      아이템에서 읽는다.
    - 쓰기 메서드(click/fill/type 등) 는 고의로 제공하지 않는다.
    """

    def __init__(
        self,
        *,
        text: str = "",
        count: int = 0,
        items: list[dict] | None = None,
        item: dict | None = None,
    ):
        self._text = text
        self._count = count
        self._items = items
        self._item = item

    def inner_text(self, timeout=None):  # noqa: ARG002
        if self._item is not None:
            return self._item.get("text", "")
        return self._text

    def count(self):
        if self._items is not None:
            return len(self._items)
        return self._count

    def nth(self, i: int) -> "_FakeLocator":
        if self._items is not None and 0 <= i < len(self._items):
            return _FakeLocator(item=self._items[i])
        return _FakeLocator()

    def get_attribute(self, name: str):
        if self._item is not None:
            return self._item.get(name)
        return None


class _FakeInspectPage:
    """로그인 + target 탐색 플로우용 페이지.

    설계 원칙: actions 에 method 명만 기록하고 value(평문 비밀번호) 는 기록하지 않는다.
    """

    def __init__(
        self,
        *,
        login_url: str = "https://example.com/login",
        post_login_url: str = "https://example.com/home",
        target_final_url: str | None = None,
        title_val: str = "Mypage Title",
        body_text: str = "환영합니다. 로그아웃.",
        counts: dict[str, int] | None = None,
        visible_selectors: tuple[str, ...] = (),
        links_list: list[dict] | None = None,
        buttons_list: list[dict] | None = None,
    ):
        self.url = login_url
        self._initial_login = login_url
        self._post_login_url = post_login_url
        self._target_final_url = target_final_url
        self._title_val = title_val
        self._body_text = body_text
        self._counts = counts or {"input": 0, "button": 0, "a": 0, "table": 0}
        self._visible = set(visible_selectors)
        self._links_list = links_list
        self._buttons_list = buttons_list
        self._goto_count = 0
        self.actions: list[tuple] = []

    def goto(self, url, wait_until=None, timeout=None):  # noqa: ARG002
        self.actions.append(("goto", url))
        self._goto_count += 1
        if self._goto_count == 1:
            self.url = url  # login page
        else:
            # target goto: use configured resolved URL or echo requested
            self.url = self._target_final_url or url
        return _FakeResponse()

    def fill(self, selector, value, timeout=None):  # noqa: ARG002
        # value 는 절대 기록하지 않는다
        self.actions.append(("fill", selector))

    def click(self, selector, timeout=None):  # noqa: ARG002
        self.actions.append(("click", selector))
        # 제출 후 URL 변경을 시뮬레이션
        self.url = self._post_login_url

    def wait_for_load_state(self, *a, **kw):  # noqa: ARG002
        self.actions.append(("wait_for_load_state",))

    def locator(self, selector: str):
        self.actions.append(("locator", selector))
        if selector == "body":
            return _FakeLocator(text=self._body_text)
        if selector == "a" and self._links_list is not None:
            return _FakeLocator(items=self._links_list)
        if selector == "button" and self._buttons_list is not None:
            return _FakeLocator(items=self._buttons_list)
        if selector in self._visible:
            return _FakeLocator(count=1)
        return _FakeLocator(count=self._counts.get(selector, 0))

    def title(self):
        self.actions.append(("title",))
        return self._title_val

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
PW = "SECRET-PW-INSPECT-42-UNIQUE"
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


def _register_profile(
    *,
    site_key: str = "sample",
    login_url: str = "https://example.com/login",
    success_check=None,
    allowed_hosts: tuple[str, ...] = ("example.com",),
    post_login_allowed_paths: tuple[str, ...] = (),
    inspect_success_check=None,
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
        post_login_allowed_paths=post_login_allowed_paths,
        inspect_success_check=inspect_success_check,
    )
    sp.register_profile(profile)
    return profile


def _log(tmp_path):
    p = tmp_path / "agent_actions.jsonl"
    return p.read_text(encoding="utf-8") if p.exists() else ""


# ══════════════════════════════════════════════════════════════════════
# 1) 로그인 후 inspect 성공
# ══════════════════════════════════════════════════════════════════════
def test_inspect_after_login_success(monkeypatch):
    from agent import app
    from agent.secrets import store as secret_store

    _register_profile()
    secret_store.save_secret("sample", USER, PW)
    page = _FakeInspectPage(
        post_login_url="https://example.com/home",
        target_final_url="https://example.com/mypage",
        title_val="Mypage Title",
        body_text="본문 " * 10,
        counts={"input": 2, "button": 3, "a": 5, "table": 1},
    )
    _install_fake_playwright(monkeypatch, page=page)

    out = app.run(
        "inspect_after_login",
        site_key="sample",
        target_url="https://example.com/mypage",
    )

    assert out["ok"] is True, out
    assert out["error"] is None
    d = out["data"]
    assert d["site_key"] == "sample"
    assert d["login_success"] is True
    assert d["target_url"] == "https://example.com/mypage"
    assert d["final_url"] == "https://example.com/mypage"
    assert d["title"] == "Mypage Title"
    assert d["snippet"].startswith("본문")
    assert len(d["snippet"]) <= 1000
    assert d["input_count"] == 2
    assert d["button_count"] == 3
    assert d["link_count"] == 5
    assert d["table_count"] == 1
    assert "fetched_at" in d and d["fetched_at"]
    # 평문 비밀번호/username 은 절대 응답에 포함되지 않는다
    assert "password" not in d
    assert "username" not in d


def test_snippet_truncated_to_1000(monkeypatch):
    from agent import app
    from agent.secrets import store as secret_store

    _register_profile()
    secret_store.save_secret("sample", USER, PW)
    page = _FakeInspectPage(
        post_login_url="https://example.com/home",
        target_final_url="https://example.com/big",
        body_text="가" * 5000,
    )
    _install_fake_playwright(monkeypatch, page=page)

    out = app.run(
        "inspect_after_login",
        site_key="sample",
        target_url="https://example.com/big",
    )
    assert out["ok"] is True
    assert len(out["data"]["snippet"]) == 1000


# ══════════════════════════════════════════════════════════════════════
# 2) profile 없는 사이트 차단
# ══════════════════════════════════════════════════════════════════════
def test_missing_profile_blocked_without_browser(monkeypatch):
    from agent import app
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)

    out = app.run(
        "inspect_after_login",
        site_key="ghost",
        target_url="https://example.com/mypage",
    )
    assert out["ok"] is False
    assert out["error"] == "site_profile_not_found"
    assert out["data"]["login_success"] is False
    assert out["data"]["site_key"] == "ghost"


# ══════════════════════════════════════════════════════════════════════
# 3) secret 없는 사이트 차단
# ══════════════════════════════════════════════════════════════════════
def test_missing_secret_blocked(monkeypatch):
    from agent import app
    _register_profile()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)

    out = app.run(
        "inspect_after_login",
        site_key="sample",
        target_url="https://example.com/mypage",
    )
    assert out["ok"] is False
    assert out["error"] == "secret_not_found"
    assert out["data"]["login_success"] is False


# ══════════════════════════════════════════════════════════════════════
# 4) target_url host 미허용
# ══════════════════════════════════════════════════════════════════════
def test_target_host_not_in_allowlist_is_blocked(monkeypatch):
    from agent import app
    from agent.secrets import store as secret_store

    _register_profile(allowed_hosts=("example.com",))
    secret_store.save_secret("sample", USER, PW)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)

    out = app.run(
        "inspect_after_login",
        site_key="sample",
        target_url="https://evil.com/mypage",
    )
    assert out["ok"] is False
    assert out["error"] == "target_host_not_allowed"
    assert out["data"]["login_success"] is False


def test_target_localhost_blocked_by_policy(monkeypatch):
    from agent import app
    from agent.secrets import store as secret_store

    _register_profile(allowed_hosts=("example.com", "localhost"))
    secret_store.save_secret("sample", USER, PW)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)

    out = app.run(
        "inspect_after_login",
        site_key="sample",
        target_url="http://localhost/admin",
    )
    assert out["ok"] is False
    assert out["error"].startswith("target_url_not_allowed")


def test_empty_target_url_is_rejected():
    from agent import app
    _register_profile()

    out = app.run(
        "inspect_after_login",
        site_key="sample",
        target_url="",
    )
    assert out["ok"] is False
    assert out["error"] == app.ERR_TARGET_URL_REQUIRED


# ══════════════════════════════════════════════════════════════════════
# 5) target_url path 미허용 차단
# ══════════════════════════════════════════════════════════════════════
def test_target_path_not_in_allowlist_is_blocked(monkeypatch):
    from agent import app
    from agent.secrets import store as secret_store

    _register_profile(
        post_login_allowed_paths=("/mypage",),
    )
    secret_store.save_secret("sample", USER, PW)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)

    out = app.run(
        "inspect_after_login",
        site_key="sample",
        target_url="https://example.com/admin/config",
    )
    assert out["ok"] is False
    assert out["error"] == "target_path_not_allowed"


def test_target_path_prefix_match_is_allowed(monkeypatch):
    from agent import app
    from agent.secrets import store as secret_store

    _register_profile(post_login_allowed_paths=("/mypage",))
    secret_store.save_secret("sample", USER, PW)
    page = _FakeInspectPage(
        post_login_url="https://example.com/home",
        target_final_url="https://example.com/mypage/info",
    )
    _install_fake_playwright(monkeypatch, page=page)

    out = app.run(
        "inspect_after_login",
        site_key="sample",
        target_url="https://example.com/mypage/info",
    )
    assert out["ok"] is True, out


# ══════════════════════════════════════════════════════════════════════
# 6) 로그인 실패 시 inspect 미진행
# ══════════════════════════════════════════════════════════════════════
def test_login_failure_prevents_target_navigation(monkeypatch):
    from agent import app
    from agent.secrets import store as secret_store

    _register_profile()
    secret_store.save_secret("sample", USER, PW)
    # 제출 후에도 login URL 에 머물면 success_check(/home) 실패
    page = _FakeInspectPage(
        post_login_url="https://example.com/login?err=1",
        target_final_url="https://example.com/mypage",
    )
    _install_fake_playwright(monkeypatch, page=page)

    out = app.run(
        "inspect_after_login",
        site_key="sample",
        target_url="https://example.com/mypage",
    )
    assert out["ok"] is False
    assert out["error"] == "login_failed"
    assert out["data"]["login_success"] is False

    # target_url 로 goto 가 발생하지 않았는지 검증: goto 는 login_url 1회만
    goto_calls = [a for a in page.actions if a[0] == "goto"]
    assert len(goto_calls) == 1, (
        f"target goto must not occur on login failure, got {goto_calls}"
    )
    assert goto_calls[0][1] == "https://example.com/login"


# ══════════════════════════════════════════════════════════════════════
# 7) 결과 포맷 검증 (성공/실패)
# ══════════════════════════════════════════════════════════════════════
def test_success_result_keys(monkeypatch):
    from agent import app
    from agent.secrets import store as secret_store

    _register_profile()
    secret_store.save_secret("sample", USER, PW)
    page = _FakeInspectPage(
        post_login_url="https://example.com/home",
        target_final_url="https://example.com/mypage",
    )
    _install_fake_playwright(monkeypatch, page=page)

    out = app.run(
        "inspect_after_login",
        site_key="sample",
        target_url="https://example.com/mypage",
    )
    assert set(out.keys()) == {"ok", "action", "data", "error"}
    assert out["action"] == "inspect_after_login"
    required = {
        "site_key", "login_success", "target_url", "final_url",
        "title", "snippet", "input_count", "button_count",
        "link_count", "table_count",
        "heading_count", "form_count", "visible_text_length",
        "top_links", "top_buttons", "page_kind",
        "fetched_at",
    }
    assert required.issubset(out["data"].keys())
    # 평문 비밀번호 관련 필드가 응답에 나타나면 안 된다
    for forbidden in ("password", "username", "token", "cookie",
                       "session", "authorization"):
        assert forbidden not in out["data"]


def test_failure_result_keys_on_login_failure(monkeypatch):
    from agent import app
    from agent.secrets import store as secret_store

    _register_profile()
    secret_store.save_secret("sample", USER, PW)
    page = _FakeInspectPage(
        post_login_url="https://example.com/login?err=1",
    )
    _install_fake_playwright(monkeypatch, page=page)

    out = app.run(
        "inspect_after_login",
        site_key="sample",
        target_url="https://example.com/mypage",
    )
    assert set(out.keys()) == {"ok", "action", "data", "error"}
    assert out["ok"] is False
    assert out["error"] == "login_failed"
    d = out["data"]
    assert d["site_key"] == "sample"
    assert d["target_url"] == "https://example.com/mypage"
    assert d["login_success"] is False


# ══════════════════════════════════════════════════════════════════════
# 8) 로그인 후 추가 click/fill/submit 미수행 보장
# ══════════════════════════════════════════════════════════════════════
def test_no_write_actions_after_login(monkeypatch):
    from agent import app
    from agent.secrets import store as secret_store

    _register_profile()
    secret_store.save_secret("sample", USER, PW)
    page = _FakeInspectPage(
        post_login_url="https://example.com/home",
        target_final_url="https://example.com/mypage",
    )
    _install_fake_playwright(monkeypatch, page=page)

    app.run(
        "inspect_after_login",
        site_key="sample",
        target_url="https://example.com/mypage",
    )

    methods = [a[0] for a in page.actions]
    # 쓰기 메서드 총량: fill x2 (로그인 user/pass), click x1 (로그인 submit).
    # 로그인 이후(두 번째 goto 이후)에는 어떠한 fill/click/submit 도 없어야 한다.
    assert methods.count("fill") == 2
    assert methods.count("click") == 1
    assert methods.count("goto") == 2

    # 로그인 이후 구간의 메서드 시퀀스 검증
    second_goto_idx = [i for i, a in enumerate(page.actions) if a[0] == "goto"][1]
    after_nav = page.actions[second_goto_idx + 1:]
    for a in after_nav:
        assert a[0] not in {
            "fill", "click", "type", "press", "check", "uncheck",
            "select_option", "set_input_files", "screenshot", "evaluate",
            "expose_function", "add_init_script", "route",
        }, f"write method after navigation: {a}"

    # 금지 메서드가 전체 구간에서 절대 호출되지 않아야 한다
    banned = {
        "type", "press", "check", "uncheck", "select_option",
        "set_input_files", "screenshot", "evaluate",
        "expose_function", "add_init_script", "route",
    }
    for m in methods:
        assert m not in banned, f"forbidden method: {m}"


# ══════════════════════════════════════════════════════════════════════
# 9) 로그 민감정보 미노출
# ══════════════════════════════════════════════════════════════════════
def test_log_does_not_leak_password(monkeypatch, tmp_path):
    from agent import app
    from agent.secrets import store as secret_store

    _register_profile()
    secret_store.save_secret("sample", USER, PW, note="memo")
    page = _FakeInspectPage(
        post_login_url="https://example.com/home",
        target_final_url="https://example.com/mypage",
    )
    _install_fake_playwright(monkeypatch, page=page)

    app.run(
        "inspect_after_login",
        site_key="sample",
        target_url="https://example.com/mypage",
    )

    raw = _log(tmp_path)
    assert PW not in raw
    assert USER not in raw
    for banned in ("password", "token", "cookie", "authorization", "session"):
        assert banned not in raw.lower()


def test_log_records_required_fields(monkeypatch, tmp_path):
    from agent import app
    from agent.secrets import store as secret_store

    _register_profile()
    secret_store.save_secret("sample", USER, PW)
    page = _FakeInspectPage(
        post_login_url="https://example.com/home",
        target_final_url="https://example.com/mypage",
    )
    _install_fake_playwright(monkeypatch, page=page)

    app.run(
        "inspect_after_login",
        site_key="sample",
        target_url="https://example.com/mypage",
    )

    lines = [
        json.loads(ln)
        for ln in _log(tmp_path).strip().splitlines()
        if ln
    ]
    last = lines[-1]
    assert last["action"] == "inspect_after_login"
    assert last["site_key"] == "sample"
    assert last["login_url"] == "https://example.com/login"
    assert last["target_url"] == "https://example.com/mypage"
    assert last["final_url"] == "https://example.com/mypage"
    assert last["ok"] is True
    assert last["checked_by"] == "url"
    assert "duration_ms" in last


# ══════════════════════════════════════════════════════════════════════
# 2단계: 구조화 필드 추출 (heading/form/visible_len/top_links/top_buttons/page_kind)
# ══════════════════════════════════════════════════════════════════════
def test_structured_fields_are_returned(monkeypatch):
    from agent import app
    from agent.secrets import store as secret_store

    _register_profile()
    secret_store.save_secret("sample", USER, PW)
    page = _FakeInspectPage(
        post_login_url="https://example.com/home",
        target_final_url="https://example.com/mypage",
        body_text="가" * 700,
        counts={
            "input": 1, "button": 2, "a": 4, "table": 0,
            "h1, h2, h3": 3, "form": 1,
        },
        links_list=[
            {"text": "링크1", "href": "/a"},
            {"text": "링크2", "href": "/b"},
        ],
        buttons_list=[{"text": "저장"}, {"text": "취소"}],
    )
    _install_fake_playwright(monkeypatch, page=page)

    out = app.run(
        "inspect_after_login",
        site_key="sample",
        target_url="https://example.com/mypage",
    )
    assert out["ok"] is True, out
    d = out["data"]
    assert d["heading_count"] == 3
    assert d["form_count"] == 1
    assert d["visible_text_length"] == 700
    assert d["top_links"] == [
        {"text": "링크1", "href": "/a"},
        {"text": "링크2", "href": "/b"},
    ]
    assert d["top_buttons"] == [{"text": "저장"}, {"text": "취소"}]
    assert d["page_kind"] in {
        "list_page", "detail_page", "dashboard", "login_result", "unknown",
    }


def test_top_links_capped_at_10(monkeypatch):
    from agent import app
    from agent.secrets import store as secret_store

    _register_profile()
    secret_store.save_secret("sample", USER, PW)
    many_links = [
        {"text": f"l{i}", "href": f"/p/{i}"} for i in range(15)
    ]
    page = _FakeInspectPage(
        post_login_url="https://example.com/home",
        target_final_url="https://example.com/mypage",
        links_list=many_links,
    )
    _install_fake_playwright(monkeypatch, page=page)

    out = app.run(
        "inspect_after_login",
        site_key="sample",
        target_url="https://example.com/mypage",
    )
    assert out["ok"] is True
    # 전체 링크 수는 15로 보고되지만 top_links 는 상위 10개로 제한된다
    assert out["data"]["link_count"] == 15
    assert len(out["data"]["top_links"]) == 10
    assert out["data"]["top_links"][0] == {"text": "l0", "href": "/p/0"}
    assert out["data"]["top_links"][-1] == {"text": "l9", "href": "/p/9"}


def test_top_buttons_capped_at_10(monkeypatch):
    from agent import app
    from agent.secrets import store as secret_store

    _register_profile()
    secret_store.save_secret("sample", USER, PW)
    many_buttons = [{"text": f"btn{i}"} for i in range(13)]
    page = _FakeInspectPage(
        post_login_url="https://example.com/home",
        target_final_url="https://example.com/mypage",
        buttons_list=many_buttons,
    )
    _install_fake_playwright(monkeypatch, page=page)

    out = app.run(
        "inspect_after_login",
        site_key="sample",
        target_url="https://example.com/mypage",
    )
    assert out["ok"] is True
    assert out["data"]["button_count"] == 13
    assert len(out["data"]["top_buttons"]) == 10
    assert out["data"]["top_buttons"][0] == {"text": "btn0"}


def test_top_link_text_and_href_are_truncated(monkeypatch):
    from agent import app
    from agent.secrets import store as secret_store

    _register_profile()
    secret_store.save_secret("sample", USER, PW)
    page = _FakeInspectPage(
        post_login_url="https://example.com/home",
        target_final_url="https://example.com/mypage",
        links_list=[
            {"text": "가" * 500, "href": "/" + ("x" * 1000)},
        ],
    )
    _install_fake_playwright(monkeypatch, page=page)

    out = app.run(
        "inspect_after_login",
        site_key="sample",
        target_url="https://example.com/mypage",
    )
    link = out["data"]["top_links"][0]
    assert len(link["text"]) == 200
    assert len(link["href"]) == 500


# ── page_kind 휴리스틱 ────────────────────────────────────────────────
def _run_with(monkeypatch, *, body_text, counts, links=None, buttons=None):
    from agent import app
    from agent.secrets import store as secret_store

    _register_profile()
    secret_store.save_secret("sample", USER, PW)
    page = _FakeInspectPage(
        post_login_url="https://example.com/home",
        target_final_url="https://example.com/mypage",
        body_text=body_text,
        counts=counts,
        links_list=links,
        buttons_list=buttons,
    )
    _install_fake_playwright(monkeypatch, page=page)
    return app.run(
        "inspect_after_login",
        site_key="sample",
        target_url="https://example.com/mypage",
    )


def test_page_kind_list_page(monkeypatch):
    out = _run_with(
        monkeypatch,
        body_text="리스트" * 50,
        counts={
            "input": 0, "button": 2, "a": 12, "table": 2,
            "h1, h2, h3": 1, "form": 0,
        },
    )
    assert out["ok"] is True
    assert out["data"]["page_kind"] == "list_page"


def test_page_kind_detail_page(monkeypatch):
    out = _run_with(
        monkeypatch,
        body_text="본문" * 400,  # 길이 800
        counts={
            "input": 0, "button": 0, "a": 3, "table": 0,
            "h1, h2, h3": 2, "form": 0,
        },
    )
    assert out["ok"] is True
    assert out["data"]["page_kind"] == "detail_page"


def test_page_kind_dashboard(monkeypatch):
    out = _run_with(
        monkeypatch,
        body_text="대시보드",
        counts={
            "input": 0, "button": 8, "a": 15, "table": 0,
            "h1, h2, h3": 1, "form": 0,
        },
    )
    assert out["ok"] is True
    assert out["data"]["page_kind"] == "dashboard"


def test_page_kind_login_result(monkeypatch):
    out = _run_with(
        monkeypatch,
        body_text="환영합니다",
        counts={
            "input": 0, "button": 1, "a": 2, "table": 0,
            "h1, h2, h3": 1, "form": 0,
        },
    )
    assert out["ok"] is True
    assert out["data"]["page_kind"] == "login_result"


def test_page_kind_unknown(monkeypatch):
    out = _run_with(
        monkeypatch,
        body_text="애매" * 150,  # 길이 300 (login_result 도, detail_page 도 아님)
        counts={
            "input": 0, "button": 2, "a": 5, "table": 0,
            "h1, h2, h3": 0, "form": 1,
        },
    )
    assert out["ok"] is True
    assert out["data"]["page_kind"] == "unknown"


# ── 2단계 추가 추출도 쓰기 동작을 유발하지 않는지 재확인 ────────────────
def test_structured_extraction_is_read_only(monkeypatch):
    from agent import app
    from agent.secrets import store as secret_store

    _register_profile()
    secret_store.save_secret("sample", USER, PW)
    page = _FakeInspectPage(
        post_login_url="https://example.com/home",
        target_final_url="https://example.com/mypage",
        counts={
            "input": 1, "button": 3, "a": 3, "table": 1,
            "h1, h2, h3": 2, "form": 1,
        },
        links_list=[
            {"text": f"l{i}", "href": f"/p/{i}"} for i in range(3)
        ],
        buttons_list=[{"text": f"b{i}"} for i in range(3)],
    )
    _install_fake_playwright(monkeypatch, page=page)

    app.run(
        "inspect_after_login",
        site_key="sample",
        target_url="https://example.com/mypage",
    )
    methods = [a[0] for a in page.actions]
    # 로그인 단계 외에는 쓰기 메서드가 절대 없어야 한다
    assert methods.count("fill") == 2
    assert methods.count("click") == 1
    assert methods.count("goto") == 2
    banned = {
        "type", "press", "check", "uncheck", "select_option",
        "set_input_files", "screenshot", "evaluate",
        "expose_function", "add_init_script", "route",
    }
    for m in methods:
        assert m not in banned, f"forbidden method: {m}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""F-4B — local_agent.browser_observer + action_observe_public_browser_page.

검증 항목:
  A) AST 보안 회귀 — 금지된 Playwright API / cookie / storage / debug-port
     literal 이 본 모듈에 없음.
  B) Google open-only 정책 — 6 도메인 + 서브도메인 launch 전 차단,
     query/fragment 미노출.
  C) 일반 공개 페이지 fixture — title / final_url_host_path / text_excerpt /
     links/buttons/forms count 수집.
  D) page_state 분류 — 404 / login / captcha / access_denied /
     developer_docs / search_portal / blank_or_empty / public_page.
  E) action 디스패처 — 정상 / Google block / scheme 거절 / 잘못된 파라미터.
  F) FORBIDDEN_ENV_VARS 가 비어있지 않으면 launch 전 거절.
"""
from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from local_agent import actions  # noqa: E402
from local_agent import browser_launcher as bl  # noqa: E402
from local_agent import browser_observer as bo  # noqa: E402


# ─── Playwright fake 객체 ────────────────────────────────────────────────

class _FakeResponse:
    def __init__(self, status: int = 200) -> None:
        self.status = status


class _FakePage:
    def __init__(
        self, *, url: str = "about:blank", title: str = "",
        html: str = "", status: int = 200,
        goto_raises: BaseException | None = None,
    ) -> None:
        self.url = url
        self._title = title
        self._html = html
        self._status = status
        self._goto_raises = goto_raises
        self.goto_calls: list[tuple[str, dict]] = []
        self.screenshot_calls: list[dict] = []

    def goto(
        self, target: str, *, timeout: int | None = None,
        wait_until: str | None = None,
    ) -> _FakeResponse | None:
        self.goto_calls.append(
            (target, {"timeout": timeout, "wait_until": wait_until}),
        )
        if self._goto_raises is not None:
            raise self._goto_raises
        if self.url == "about:blank":
            self.url = target
        return _FakeResponse(self._status)

    def title(self) -> str:
        return self._title

    def content(self) -> str:
        return self._html

    def screenshot(self, *, path: str, full_page: bool = False) -> None:
        self.screenshot_calls.append({"path": path, "full_page": full_page})
        # 빈 PNG 헤더만 써둔다 (실제 렌더링은 fake 환경에선 의미 없음).
        with open(path, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n")


class _FakeContext:
    def __init__(self, page: _FakePage) -> None:
        self._page = page
        self.closed = False

    def new_page(self) -> _FakePage:
        return self._page

    def close(self) -> None:
        self.closed = True


class _FakeBrowser:
    def __init__(self, context: _FakeContext) -> None:
        self._context = context
        self.new_context_calls: list[dict] = []
        self.closed = False

    def new_context(self, **kwargs: Any) -> _FakeContext:
        self.new_context_calls.append(dict(kwargs))
        return self._context

    def close(self) -> None:
        self.closed = True


class _FakeChromium:
    def __init__(self, browser: _FakeBrowser) -> None:
        self._browser = browser
        self.launch_calls: list[dict] = []

    def launch(self, **kwargs: Any) -> _FakeBrowser:
        self.launch_calls.append(dict(kwargs))
        return self._browser


class _FakePlaywright:
    def __init__(self, chromium: _FakeChromium) -> None:
        self.chromium = chromium


class _FakePlaywrightCM:
    def __init__(self, chromium: _FakeChromium) -> None:
        self._pw = _FakePlaywright(chromium)

    def __enter__(self) -> _FakePlaywright:
        return self._pw

    def __exit__(self, *exc: Any) -> None:
        return None


def _make_factory(page: _FakePage) -> Any:
    ctx = _FakeContext(page)
    browser = _FakeBrowser(ctx)
    chromium = _FakeChromium(browser)
    factory = lambda: _FakePlaywrightCM(chromium)  # noqa: E731
    factory.chromium = chromium  # type: ignore[attr-defined]
    factory.browser = browser    # type: ignore[attr-defined]
    factory.context = ctx        # type: ignore[attr-defined]
    return factory


def _empty_env() -> dict:
    """FORBIDDEN_ENV_VARS 가 모두 비어있는 깨끗한 env."""
    env: dict[str, str] = {}
    for k in bl._FORBIDDEN_ENV_VARS:
        env.pop(k, None)
    return env


# ═════════════════════════════════════════════════════════════════════════
# A) AST 보안 회귀
# ═════════════════════════════════════════════════════════════════════════

_FORBIDDEN_CALL_ATTRS_OBSERVER = {
    # 입력/조작 — observer 는 read-only.
    "fill", "press", "click", "type", "select_option", "set_input_files",
    # 쿠키 / 스토리지 — 절대 금지.
    "cookies", "add_cookies", "storage_state",
    # JS 실행 — 절대 금지.
    "evaluate", "evaluate_handle",
}
_FORBIDDEN_ATTR_USAGE_OBSERVER = {"keyboard", "mouse"}
_FORBIDDEN_NAMES_OBSERVER = {"localStorage", "sessionStorage"}
_FORBIDDEN_STRING_LITERALS_OBSERVER = (
    "--remote-debugging-port",
    "--headless",
    "GOOGLE_PASSWORD",
    "GOOGLE_LOGIN_PASSWORD",
    "GOOGLE_COOKIE",
    "GOOGLE_SESSION",
    "GOOGLE_STORAGE_STATE",
    "GOOGLE_OTP_SECRET",
)


def _scan_forbidden_apis(src: str) -> list[tuple[str, int]]:
    tree = ast.parse(src)
    offenders: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in _FORBIDDEN_CALL_ATTRS_OBSERVER:
                offenders.append((f"call:.{node.func.attr}(", node.lineno))
        if isinstance(node, ast.Attribute) and \
                node.attr in _FORBIDDEN_ATTR_USAGE_OBSERVER:
            offenders.append((f"attr:.{node.attr}", node.lineno))
        if isinstance(node, ast.Name) and \
                node.id in _FORBIDDEN_NAMES_OBSERVER:
            offenders.append((f"name:{node.id}", node.lineno))
    return offenders


def test_observer_module_has_no_forbidden_apis() -> None:
    src = Path(bo.__file__).read_text(encoding="utf-8")
    offenders = _scan_forbidden_apis(src)
    assert offenders == [], (
        f"forbidden API patterns in browser_observer: {offenders}"
    )


def _collect_non_docstring_str_constants(src: str) -> list[str]:
    """모듈/함수/클래스 docstring 을 제외한 모든 ast.Constant(str) 수집.

    docstring 안에는 "절대 수행하지 않음" 을 설명하기 위해 ``--headless`` /
    ``GOOGLE_PASSWORD`` 같은 토큰을 일부러 명시하는 게 정상이다. 본 검사는
    실제 코드 경로의 string literal 만 대상으로 한다.
    """
    tree = ast.parse(src)
    docstring_nodes: set[int] = set()

    def _mark_docstring(body: list[ast.stmt]) -> None:
        if not body:
            return
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            docstring_nodes.add(id(first.value))

    _mark_docstring(tree.body)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            _mark_docstring(node.body)

    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstring_nodes:
                continue
            out.append(node.value)
    return out


def test_observer_module_has_no_forbidden_string_literals() -> None:
    """docstring 외 실제 코드에서 사용된 string literal 만 검사.

    - ``--headless`` / ``--remote-debugging-port`` 같은 launch arg 가 코드
      경로에 들어가면 안 된다.
    - ``GOOGLE_PASSWORD`` 등 비밀 env 이름은 ``browser_launcher.
      _FORBIDDEN_ENV_VARS`` 를 import 해 사용하므로, observer 자체 코드
      경로에 literal 로 박혀선 안 된다.
    """
    src = Path(bo.__file__).read_text(encoding="utf-8")
    code_strings = _collect_non_docstring_str_constants(src)
    offenders: list[str] = []
    for s in code_strings:
        for lit in _FORBIDDEN_STRING_LITERALS_OBSERVER:
            if lit in s and (s, lit) not in offenders:
                offenders.append((s, lit))  # type: ignore[arg-type]
    assert offenders == [], (
        f"forbidden literals in browser_observer code paths: {offenders}"
    )


def test_action_function_observe_has_no_forbidden_apis() -> None:
    """actions.action_observe_public_browser_page 함수 자체도 동일 검사."""
    src = Path(actions.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    target = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and \
                node.name == "action_observe_public_browser_page":
            target = node
            break
    assert target is not None, \
        "action_observe_public_browser_page not found"

    offenders: list[tuple[str, int]] = []
    for node in ast.walk(target):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in _FORBIDDEN_CALL_ATTRS_OBSERVER:
                offenders.append((f"call:.{node.func.attr}(", node.lineno))
        if isinstance(node, ast.Attribute) and \
                node.attr in _FORBIDDEN_ATTR_USAGE_OBSERVER:
            offenders.append((f"attr:.{node.attr}", node.lineno))
        if isinstance(node, ast.Name) and \
                node.id in _FORBIDDEN_NAMES_OBSERVER:
            offenders.append((f"name:{node.id}", node.lineno))
    assert offenders == [], (
        f"forbidden API in action_observe_public_browser_page: {offenders}"
    )


# ═════════════════════════════════════════════════════════════════════════
# B) Google open-only 정책
# ═════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "url,expected_host_path",
    [
        ("https://accounts.google.com/signin?continue=secret-state",
         "accounts.google.com/signin"),
        ("https://www.google.com/?token=AAA",
         "www.google.com"),
        ("https://studio.youtube.com/channel/UC-xxx?next=YYY",
         "studio.youtube.com/channel/UC-xxx"),
        ("https://www.youtube.com/watch?v=SECRETID",
         "www.youtube.com/watch"),
        ("https://gmail.com/?session=AAA",
         "gmail.com"),
        ("https://drive.google.com/drive/folders/SECRET?usp=sharing",
         "drive.google.com/drive/folders/SECRET"),
    ],
)
def test_observe_blocks_google_open_only_before_launch(
    url: str, expected_host_path: str,
) -> None:
    page = _FakePage()
    factory = _make_factory(page)
    result = bo.observe_public_browser_page(
        url, _browser_factory=factory, _env=_empty_env(),
    )

    assert result["success"] is False
    assert result["error_code"] == "GOOGLE_OPEN_ONLY"
    assert "google_open_only_use_open_local_browser" in result["warnings"]
    # Playwright 호출 0회.
    assert factory.chromium.launch_calls == []
    # raw query/fragment 미노출.
    blob = str(result)
    for tok in ("?continue=", "?token=", "?next=", "?v=SECRETID",
                "?session=", "?usp=sharing", "secret-state",
                "SECRETID", "session=AAA", "token=AAA"):
        assert tok not in blob, (tok, blob)
    # target_url 은 host+path 까지만.
    assert result["target_url"].startswith(("http://", "https://")) or \
        result["target_url"] == ""


# ═════════════════════════════════════════════════════════════════════════
# C) 일반 공개 페이지 — 정상 흐름
# ═════════════════════════════════════════════════════════════════════════

def _basic_html(*, title: str = "Example Domain", body: str = "") -> str:
    body_html = body or (
        "<h1>Example Domain</h1>"
        "<p>This domain is for use in illustrative examples.</p>"
        "<a href='https://www.iana.org/about'>More information...</a>"
    )
    return f"""<!DOCTYPE html>
<html><head><title>{title}</title></head>
<body>{body_html}</body></html>"""


def test_observe_normal_page_returns_full_schema() -> None:
    html = _basic_html()
    page = _FakePage(
        url="about:blank", title="Example Domain", html=html, status=200,
    )
    factory = _make_factory(page)
    result = bo.observe_public_browser_page(
        "https://example.com/",
        _browser_factory=factory, _env=_empty_env(),
    )

    assert result["success"] is True
    assert result["error_code"] == ""
    assert result["status_code"] == 200
    assert result["title"] == "Example Domain"
    assert result["final_url_host_path"] == "example.com"
    assert result["page_state"] in {"public_page", "blank_or_empty"}
    assert result["text_length"] > 0
    assert "Example Domain" in result["text_excerpt"]
    assert result["links_count"] >= 1
    assert isinstance(result["links"], list)
    assert isinstance(result["buttons"], list)
    assert isinstance(result["forms"], list)
    assert result["screenshot_path"] is None
    # storage 미접근 — context 는 fresh new_context() 호출 (storage_state 없음).
    assert factory.browser.new_context_calls == [{}]
    # launch 옵션은 headless=False.
    assert factory.chromium.launch_calls[0].get("headless") is False
    assert "args" not in factory.chromium.launch_calls[0]


def test_observe_normal_page_strips_query_fragment_in_target_url() -> None:
    html = _basic_html()
    page = _FakePage(
        url="about:blank", title="Example Domain", html=html, status=200,
    )
    factory = _make_factory(page)
    result = bo.observe_public_browser_page(
        "https://example.com/?ref=secret-token#frag",
        _browser_factory=factory, _env=_empty_env(),
    )
    assert result["success"] is True
    assert "secret-token" not in str(result)
    assert "?ref=" not in str(result)
    assert "#frag" not in str(result)
    # final_url_host_path 도 query 미포함.
    assert "?" not in result["final_url_host_path"]


def test_observe_screenshot_optional_writes_file(tmp_path) -> None:
    html = _basic_html()
    page = _FakePage(
        url="about:blank", title="Example Domain", html=html, status=200,
    )
    factory = _make_factory(page)
    result = bo.observe_public_browser_page(
        "https://example.com/",
        capture_screenshot=True,
        _browser_factory=factory, _env=_empty_env(),
    )
    assert result["success"] is True
    sp = result["screenshot_path"]
    assert sp and Path(sp).is_file()
    # 정리.
    try:
        Path(sp).unlink()
    except OSError:
        pass


# ═════════════════════════════════════════════════════════════════════════
# D) page_state 분류 fixtures
# ═════════════════════════════════════════════════════════════════════════

def _observe_with_html(
    *, html: str, status: int = 200, title: str = "",
    final_url: str = "https://example.com/",
    target_url: str = "https://example.com/",
) -> dict:
    page = _FakePage(
        url=final_url, title=title, html=html, status=status,
    )
    factory = _make_factory(page)
    return bo.observe_public_browser_page(
        target_url, _browser_factory=factory, _env=_empty_env(),
    )


def test_page_state_not_found_on_404() -> None:
    r = _observe_with_html(
        html="<html><body><h1>Not Found</h1></body></html>",
        status=404, title="404 Not Found",
    )
    assert r["page_state"] == "not_found"
    assert r["success"] is False
    assert r["error_code"] == "PAGE_NOT_FOUND"


def test_page_state_server_error_on_500() -> None:
    r = _observe_with_html(
        html="<html><body><h1>Internal Server Error</h1></body></html>",
        status=500, title="500",
    )
    assert r["page_state"] == "server_error"
    assert r["success"] is False
    assert r["error_code"] == "HTTP_500"


def test_page_state_login_required_with_password_input() -> None:
    html = """<html><head><title>로그인 - Example</title></head>
    <body>
      <form method='post' action='/login'>
        <input type='text' name='id'/>
        <input type='password' name='pw'/>
        <button>로그인</button>
      </form>
    </body></html>"""
    r = _observe_with_html(html=html, title="로그인 - Example")
    assert r["page_state"] == "login_required"
    # password input 은 type 만 카운트하고 value 는 절대 수집하지 않는다.
    types_blob = ",".join(r["input_types"])
    assert "password" in types_blob
    # forms_sample 은 has_password=True 표기만 (value 없음).
    assert any(f.get("has_password") for f in r["forms"])


def test_page_state_captcha() -> None:
    html = """<html><head><title>보안문자 확인</title></head>
    <body><h1>보안문자</h1><p>자동입력방지 captcha 를 풀어주세요</p>
    </body></html>"""
    r = _observe_with_html(html=html, title="보안문자 확인", status=200)
    assert r["page_state"] == "captcha_or_bot_check"


def test_page_state_access_denied_with_403() -> None:
    html = "<html><body><h1>Forbidden</h1></body></html>"
    r = _observe_with_html(html=html, status=403, title="403 Forbidden")
    assert r["page_state"] == "access_denied"


def test_page_state_developer_docs_by_host() -> None:
    html = """<html><head><title>Kakao Developers</title></head>
    <body><h1>Kakao Developers</h1>
      <a href='/docs'>API Reference</a>
      <a href='/sdk'>SDK</a>
    </body></html>"""
    r = _observe_with_html(
        html=html, title="Kakao Developers",
        final_url="https://developers.kakao.com/",
        target_url="https://developers.kakao.com/",
    )
    assert r["page_state"] == "developer_docs"


def test_page_state_developer_docs_by_text() -> None:
    """host 에 token 이 없어도 본문에 docs/SDK 가 충분하면 분류된다."""
    html = """<html><head><title>Some API SDK</title></head>
    <body>
      <h1>API Reference</h1>
      <p>Documentation for our SDK and REST API.</p>
    </body></html>"""
    r = _observe_with_html(
        html=html, title="Some API SDK",
        final_url="https://example.com/api/", target_url="https://example.com/api/",
    )
    assert r["page_state"] == "developer_docs"


def test_page_state_search_portal() -> None:
    html = """<html><head><title>NAVER</title></head>
    <body>
      <h1>네이버</h1>
      <a href='/news'>뉴스</a>
      <a href='/cafe'>카페</a>
      <a href='/mail'>메일</a>
      <input type='text' name='query'/>
      <button>검색</button>
    </body></html>"""
    r = _observe_with_html(
        html=html, title="NAVER",
        final_url="https://www.naver.com/",
        target_url="https://www.naver.com/",
    )
    assert r["page_state"] == "search_portal"


def test_page_state_blank_or_empty() -> None:
    html = "<html><head><title>x</title></head><body></body></html>"
    r = _observe_with_html(html=html, title="x")
    assert r["page_state"] == "blank_or_empty"


def test_page_state_public_page_default() -> None:
    """위 분류 어디에도 강하게 매칭되지 않는 일반 페이지.

    text_blob 은 page_title + headings + links + buttons + table headers 만
    합산하므로 일반 fixture 에서도 충분한 길이가 되도록 heading/link 를
    여러 개 둔다 (실제 사이트는 자연히 길어진다)."""
    html = """<html><head><title>About Company X Industrial Widgets</title></head>
    <body>
      <h1>About Company X Industrial Widgets</h1>
      <h2>Mission and Core Values</h2>
      <h2>Company History since 1972 and Beyond</h2>
      <h3>Our Worldwide Distribution Network</h3>
      <a href='/products'>Industrial Widgets and Components</a>
      <a href='/services'>Manufacturing Services Catalog</a>
      <a href='/contact'>Contact Our Sales Office</a>
      <a href='/team'>Meet Our Engineering Team</a>
    </body></html>"""
    r = _observe_with_html(
        html=html, title="About Company X Industrial Widgets",
        final_url="https://company-x.example/",
        target_url="https://company-x.example/",
    )
    assert r["page_state"] == "public_page", (r["page_state"], r["text_length"])


# ═════════════════════════════════════════════════════════════════════════
# E) action 디스패처
# ═════════════════════════════════════════════════════════════════════════

def test_action_registered_and_dispatchable() -> None:
    assert "observe_public_browser_page" in actions._ACTIONS
    assert actions._ACTIONS["observe_public_browser_page"] is \
        actions.action_observe_public_browser_page
    assert "observe_public_browser_page" not in actions.FORBIDDEN_ACTIONS


def test_action_meta_registered_in_action_registry() -> None:
    from agent import action_registry as ar
    meta = ar.get_meta("observe_public_browser_page")
    assert meta is not None
    assert meta.category == ar.CATEGORY_LOCAL_BROWSER
    assert meta.risk_level == ar.RISK_MEDIUM
    assert meta.requires_browser is True
    assert meta.requires_secret is False
    assert meta.read_only is True


def test_action_in_policy_allowlist() -> None:
    from agent import policy
    assert "observe_public_browser_page" in policy.ALLOWED_ACTIONS


def test_action_dispatch_routes_to_observer() -> None:
    page = _FakePage(
        url="about:blank", title="Example", html=_basic_html(), status=200,
    )
    factory = _make_factory(page)
    result = actions.execute_action("observe_public_browser_page", {
        "url": "https://example.com/",
        "_browser_factory": factory,
        "_env": _empty_env(),
    })
    assert result.success is True
    assert result.data["status_code"] == 200
    assert result.data["title"] == "Example"
    assert result.data["page_state"] in {"public_page", "blank_or_empty"}


def test_action_missing_url_returns_fail() -> None:
    r = actions.action_observe_public_browser_page({})
    assert r.success is False
    assert r.error_code == "MISSING_URL"


@pytest.mark.parametrize(
    "bad_url",
    ["file:///x", "javascript:1", "data:,", "ftp://x", "about:blank"],
)
def test_action_non_http_url_rejected(bad_url: str) -> None:
    r = actions.action_observe_public_browser_page({"url": bad_url})
    assert r.success is False
    assert r.error_code == "URL_SCHEME_NOT_ALLOWED"


def test_action_invalid_timeout_returns_invalid_param() -> None:
    r = actions.action_observe_public_browser_page({
        "url": "https://example.com/",
        "timeout_ms": "not-int",
    })
    assert r.success is False
    assert r.error_code == "INVALID_PARAM"


def test_action_propagates_google_open_only() -> None:
    page = _FakePage()
    factory = _make_factory(page)
    r = actions.action_observe_public_browser_page({
        "url": "https://studio.youtube.com/",
        "_browser_factory": factory,
        "_env": _empty_env(),
    })
    assert r.success is False
    assert r.error_code == "GOOGLE_OPEN_ONLY"
    assert "google_open_only_use_open_local_browser" in r.data["warnings"]
    assert factory.chromium.launch_calls == []


def test_action_target_url_param_key_also_recognized() -> None:
    """params.target_url 도 url 과 동일하게 처리된다 (server gate 와 동치)."""
    page = _FakePage(
        url="about:blank", title="Example", html=_basic_html(), status=200,
    )
    factory = _make_factory(page)
    r = actions.action_observe_public_browser_page({
        "target_url": "https://example.com/",
        "_browser_factory": factory,
        "_env": _empty_env(),
    })
    assert r.success is True


# ═════════════════════════════════════════════════════════════════════════
# F) FORBIDDEN_ENV_VARS
# ═════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("forbidden_key", list(bl._FORBIDDEN_ENV_VARS))
def test_forbidden_env_var_blocks_observer_before_launch(
    forbidden_key: str,
) -> None:
    page = _FakePage()
    factory = _make_factory(page)
    env = _empty_env()
    env[forbidden_key] = "do-not-leak-this"

    r = bo.observe_public_browser_page(
        "https://example.com/",
        _browser_factory=factory, _env=env,
    )
    assert r["success"] is False
    assert r["error_code"] == "FORBIDDEN_ENV_PRESENT"
    assert any(
        w == f"forbidden_env_present:{forbidden_key}" for w in r["warnings"]
    )
    # Playwright 호출 없음.
    assert factory.chromium.launch_calls == []
    # 값 누출 없음.
    assert "do-not-leak-this" not in str(r)


# ═════════════════════════════════════════════════════════════════════════
# G) F-2/F-3 회귀 — open_local_browser 는 본 정책의 차단 대상이 아니다
# ═════════════════════════════════════════════════════════════════════════

def test_open_local_browser_action_still_allows_google_url(monkeypatch) -> None:
    """observe 는 차단되지만 open_local_browser (subprocess) 는 그대로 허용된다."""
    seen: list[dict] = []

    def _fake(**kwargs: Any) -> dict:
        seen.append(dict(kwargs))
        return {
            "launched": True,
            "target_url": kwargs.get("url", ""),
            "browser_provider": "chrome",
            "browser_channel": "chrome",
            "browser_path_category": "program_files",
            "profile_dir_category": "haehan_dedicated",
            "pid": 4242,
            "warnings": [],
        }

    monkeypatch.setattr(bl, "open_local_browser", _fake)
    r = actions.execute_action("open_local_browser", {
        "url": "https://studio.youtube.com/",
        "site_policy": bl.SITE_POLICY_GOOGLE,
        "profile_name": "google_main",
        "provider_override": "chrome",
    })
    assert r.success is True
    assert r.data["launched"] is True
    assert seen[0]["url"] == "https://studio.youtube.com/"


# ═════════════════════════════════════════════════════════════════════════
# H) wait_until / dwell_seconds (F-4F-0)
# ═════════════════════════════════════════════════════════════════════════

def test_observe_default_wait_until_passed_to_goto() -> None:
    page = _FakePage(
        url="about:blank", title="Example", html=_basic_html(), status=200,
    )
    factory = _make_factory(page)
    bo.observe_public_browser_page(
        "https://example.com/",
        _browser_factory=factory, _env=_empty_env(),
    )
    assert page.goto_calls
    assert page.goto_calls[0][1]["wait_until"] == "domcontentloaded"


@pytest.mark.parametrize(
    "w", ["commit", "domcontentloaded", "load", "networkidle"],
)
def test_observe_wait_until_allowed_values(w: str) -> None:
    page = _FakePage(
        url="about:blank", title="Example", html=_basic_html(), status=200,
    )
    factory = _make_factory(page)
    r = bo.observe_public_browser_page(
        "https://example.com/", wait_until=w,
        _browser_factory=factory, _env=_empty_env(),
    )
    assert r["success"] is True
    assert page.goto_calls[0][1]["wait_until"] == w


@pytest.mark.parametrize(
    "w",
    [
        "",                # 빈 문자열
        "wrong",           # 미허용 토큰
        "DOMCONTENTLOADED",  # 대소문자 불일치
        "fully_loaded",    # 미허용 토큰
        None,              # str 아님
        0,                 # str 아님
    ],
)
def test_observe_wait_until_rejected_for_invalid(w: Any) -> None:
    page = _FakePage()
    factory = _make_factory(page)
    r = bo.observe_public_browser_page(
        "https://example.com/", wait_until=w,
        _browser_factory=factory, _env=_empty_env(),
    )
    assert r["success"] is False
    assert r["error_code"] == "WAIT_UNTIL_INVALID"
    assert "wait_until_invalid" in r["warnings"]
    # Playwright 호출 0회 — launch 전 reject.
    assert factory.chromium.launch_calls == []


def test_observe_default_dwell_seconds_no_sleep(monkeypatch) -> None:
    sleeps: list[Any] = []
    monkeypatch.setattr(bo.time, "sleep", lambda s: sleeps.append(s))
    page = _FakePage(
        url="about:blank", title="Example", html=_basic_html(), status=200,
    )
    factory = _make_factory(page)
    r = bo.observe_public_browser_page(
        "https://example.com/",
        _browser_factory=factory, _env=_empty_env(),
    )
    assert r["success"] is True
    # dwell_seconds 미지정 → time.sleep 호출 0회.
    assert sleeps == []


def test_observe_dwell_seconds_one_calls_sleep_once(monkeypatch) -> None:
    sleeps: list[Any] = []
    monkeypatch.setattr(bo.time, "sleep", lambda s: sleeps.append(s))
    page = _FakePage(
        url="about:blank", title="Example", html=_basic_html(), status=200,
    )
    factory = _make_factory(page)
    r = bo.observe_public_browser_page(
        "https://example.com/", dwell_seconds=1,
        _browser_factory=factory, _env=_empty_env(),
    )
    assert r["success"] is True
    assert sleeps == [1]


def test_observe_dwell_seconds_30_boundary_allowed(monkeypatch) -> None:
    sleeps: list[Any] = []
    monkeypatch.setattr(bo.time, "sleep", lambda s: sleeps.append(s))
    page = _FakePage(
        url="about:blank", title="Example", html=_basic_html(), status=200,
    )
    factory = _make_factory(page)
    r = bo.observe_public_browser_page(
        "https://example.com/", dwell_seconds=30,
        _browser_factory=factory, _env=_empty_env(),
    )
    assert r["success"] is True
    assert sleeps == [30]


@pytest.mark.parametrize("d", [-1, -10, 31, 100, 9999])
def test_observe_dwell_seconds_out_of_range_rejected(d: int) -> None:
    page = _FakePage()
    factory = _make_factory(page)
    r = bo.observe_public_browser_page(
        "https://example.com/", dwell_seconds=d,
        _browser_factory=factory, _env=_empty_env(),
    )
    assert r["success"] is False
    assert r["error_code"] == "DWELL_SECONDS_INVALID"
    assert "dwell_seconds_invalid" in r["warnings"]
    # Playwright 호출 0회 — launch 전 reject.
    assert factory.chromium.launch_calls == []


@pytest.mark.parametrize(
    "d",
    [
        "10",     # 문자열은 observer 단에선 reject (action 단에서만 변환)
        1.5,      # float
        None,
        True,     # bool 명시 차단
        False,
        [1],
    ],
)
def test_observe_dwell_seconds_non_int_rejected(d: Any) -> None:
    page = _FakePage()
    factory = _make_factory(page)
    r = bo.observe_public_browser_page(
        "https://example.com/", dwell_seconds=d,
        _browser_factory=factory, _env=_empty_env(),
    )
    assert r["success"] is False
    assert r["error_code"] == "DWELL_SECONDS_INVALID"
    assert factory.chromium.launch_calls == []


def test_action_passes_wait_until_to_observer() -> None:
    page = _FakePage(
        url="about:blank", title="Example", html=_basic_html(), status=200,
    )
    factory = _make_factory(page)
    r = actions.execute_action("observe_public_browser_page", {
        "url": "https://example.com/",
        "wait_until": "networkidle",
        "_browser_factory": factory,
        "_env": _empty_env(),
    })
    assert r.success is True
    assert page.goto_calls[0][1]["wait_until"] == "networkidle"


def test_action_passes_dwell_seconds_to_observer(monkeypatch) -> None:
    sleeps: list[Any] = []
    monkeypatch.setattr(bo.time, "sleep", lambda s: sleeps.append(s))
    page = _FakePage(
        url="about:blank", title="Example", html=_basic_html(), status=200,
    )
    factory = _make_factory(page)
    r = actions.execute_action("observe_public_browser_page", {
        "url": "https://example.com/",
        "dwell_seconds": 2,
        "_browser_factory": factory,
        "_env": _empty_env(),
    })
    assert r.success is True
    assert sleeps == [2]


def test_action_dwell_seconds_string_int_converted(monkeypatch) -> None:
    """문자열 숫자 "3" 은 action 단에서 안전하게 int 로 변환된다."""
    sleeps: list[Any] = []
    monkeypatch.setattr(bo.time, "sleep", lambda s: sleeps.append(s))
    page = _FakePage(
        url="about:blank", title="Example", html=_basic_html(), status=200,
    )
    factory = _make_factory(page)
    r = actions.execute_action("observe_public_browser_page", {
        "url": "https://example.com/",
        "dwell_seconds": "3",
        "_browser_factory": factory,
        "_env": _empty_env(),
    })
    assert r.success is True
    assert sleeps == [3]


def test_action_dwell_seconds_non_numeric_string_rejected() -> None:
    r = actions.action_observe_public_browser_page({
        "url": "https://example.com/",
        "dwell_seconds": "abc",
    })
    assert r.success is False
    assert r.error_code == "INVALID_PARAM"


def test_action_dwell_seconds_negative_propagates_observer_reject() -> None:
    page = _FakePage()
    factory = _make_factory(page)
    r = actions.execute_action("observe_public_browser_page", {
        "url": "https://example.com/",
        "dwell_seconds": -5,
        "_browser_factory": factory,
        "_env": _empty_env(),
    })
    assert r.success is False
    assert r.data["error_code"] == "DWELL_SECONDS_INVALID"
    assert factory.chromium.launch_calls == []


def test_action_dwell_seconds_over_30_propagates_observer_reject() -> None:
    page = _FakePage()
    factory = _make_factory(page)
    r = actions.execute_action("observe_public_browser_page", {
        "url": "https://example.com/",
        "dwell_seconds": 31,
        "_browser_factory": factory,
        "_env": _empty_env(),
    })
    assert r.success is False
    assert r.data["error_code"] == "DWELL_SECONDS_INVALID"
    assert factory.chromium.launch_calls == []


def test_action_wait_until_invalid_propagates_observer_reject() -> None:
    page = _FakePage()
    factory = _make_factory(page)
    r = actions.execute_action("observe_public_browser_page", {
        "url": "https://example.com/",
        "wait_until": "fully_loaded",
        "_browser_factory": factory,
        "_env": _empty_env(),
    })
    assert r.success is False
    assert r.data["error_code"] == "WAIT_UNTIL_INVALID"
    assert factory.chromium.launch_calls == []


def test_google_open_only_blocks_before_dwell(monkeypatch) -> None:
    """dwell_seconds/wait_until 이 있어도 Google open-only 는 launch 전 차단."""
    sleeps: list[Any] = []
    monkeypatch.setattr(bo.time, "sleep", lambda s: sleeps.append(s))
    page = _FakePage()
    factory = _make_factory(page)
    r = bo.observe_public_browser_page(
        "https://accounts.google.com/signin?continue=secret",
        wait_until="networkidle",
        dwell_seconds=10,
        _browser_factory=factory, _env=_empty_env(),
    )
    assert r["success"] is False
    assert r["error_code"] == "GOOGLE_OPEN_ONLY"
    assert factory.chromium.launch_calls == []
    assert sleeps == []
    # query/fragment 미노출.
    assert "secret" not in str(r)

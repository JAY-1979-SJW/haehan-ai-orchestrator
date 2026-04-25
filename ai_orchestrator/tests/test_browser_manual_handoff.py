"""F-4F-2A — local_agent.browser_manual_handoff.

검증 항목:
  A) AST 보안 회귀 — 금지된 Playwright API / cookie / storage / debug-port
     literal 이 본 모듈에 없음.
  B) Google open-only 정책 — launch 전 차단, query/fragment 미노출.
  C) 파라미터 검증 — handoff_seconds / dwell_after_capture_seconds /
     wait_until.
  D) 정상 흐름 — handoff sleep 후 1회 캡처, 결과 schema, handoff 블록.
  E) FORBIDDEN_ENV_VARS 비어있지 않으면 launch 전 거절.
  F) 보안프로그램/홈택스 helper 부착 (옵셔널).
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from local_agent import browser_launcher as bl  # noqa: E402
from local_agent import browser_manual_handoff as bmh  # noqa: E402


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
    env: dict[str, str] = {}
    for k in bl._FORBIDDEN_ENV_VARS:
        env.pop(k, None)
    return env


class _SleepRecorder:
    """sleep 호출을 기록만 하고 실제로 잠들지 않는다."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(float(seconds))


# ═════════════════════════════════════════════════════════════════════════
# A) AST 보안 회귀
# ═════════════════════════════════════════════════════════════════════════

_FORBIDDEN_CALL_ATTRS = {
    # 입력/조작 — manual handoff observer 도 자동 클릭/입력 금지.
    "fill", "press", "click", "type", "select_option", "set_input_files",
    # 쿠키 / 스토리지 — 절대 금지.
    "cookies", "add_cookies", "storage_state",
    # JS 실행 — 절대 금지.
    "evaluate", "evaluate_handle",
}
_FORBIDDEN_ATTR_USAGE = {"keyboard", "mouse"}
_FORBIDDEN_NAMES = {"localStorage", "sessionStorage"}
_FORBIDDEN_STRING_LITERALS = (
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
            if node.func.attr in _FORBIDDEN_CALL_ATTRS:
                offenders.append((f"call:.{node.func.attr}(", node.lineno))
        if isinstance(node, ast.Attribute) and \
                node.attr in _FORBIDDEN_ATTR_USAGE:
            offenders.append((f"attr:.{node.attr}", node.lineno))
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            offenders.append((f"name:{node.id}", node.lineno))
    return offenders


def test_handoff_module_has_no_forbidden_apis() -> None:
    src = Path(bmh.__file__).read_text(encoding="utf-8")
    offenders = _scan_forbidden_apis(src)
    assert offenders == [], (
        f"forbidden API patterns in browser_manual_handoff: {offenders}"
    )


def _collect_non_docstring_str_constants(src: str) -> list[str]:
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


def test_handoff_module_has_no_forbidden_string_literals() -> None:
    src = Path(bmh.__file__).read_text(encoding="utf-8")
    code_strings = _collect_non_docstring_str_constants(src)
    offenders: list[tuple[str, str]] = []
    for s in code_strings:
        for lit in _FORBIDDEN_STRING_LITERALS:
            if lit in s and (s, lit) not in offenders:
                offenders.append((s, lit))
    assert offenders == [], (
        f"forbidden literals in browser_manual_handoff code paths: {offenders}"
    )


# ═════════════════════════════════════════════════════════════════════════
# B) Google open-only 정책
# ═════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "url,expected_host_path",
    [
        ("https://accounts.google.com/signin?continue=secret-state",
         "accounts.google.com/signin"),
        ("https://www.youtube.com/watch?v=SECRETID",
         "www.youtube.com/watch"),
        ("https://drive.google.com/drive/folders/SECRET?usp=sharing",
         "drive.google.com/drive/folders/SECRET"),
    ],
)
def test_handoff_blocks_google_open_only_before_launch(
    url: str, expected_host_path: str,
) -> None:
    page = _FakePage()
    factory = _make_factory(page)
    sleep = _SleepRecorder()
    result = bmh.observe_after_manual_handoff(
        url, _browser_factory=factory, _env=_empty_env(), _sleep=sleep,
    )

    assert result["success"] is False
    assert result["error_code"] == "GOOGLE_OPEN_ONLY"
    assert "google_open_only_use_open_local_browser" in result["warnings"]
    # launch 0회, sleep 0회.
    assert factory.chromium.launch_calls == []
    assert sleep.calls == []
    # raw query/fragment 미노출.
    blob = str(result)
    for tok in ("?continue=", "secret-state", "?v=SECRETID",
                "SECRETID", "?usp=sharing"):
        assert tok not in blob, (tok, blob)


# ═════════════════════════════════════════════════════════════════════════
# C) 파라미터 검증
# ═════════════════════════════════════════════════════════════════════════

def test_handoff_seconds_default_is_20() -> None:
    """observe_after_manual_handoff 의 keyword default 가 20."""
    import inspect
    sig = inspect.signature(bmh.observe_after_manual_handoff)
    assert sig.parameters["handoff_seconds"].default == 20


def test_dwell_after_capture_default_is_zero() -> None:
    import inspect
    sig = inspect.signature(bmh.observe_after_manual_handoff)
    assert sig.parameters["dwell_after_capture_seconds"].default == 0


def test_handoff_seconds_negative_rejected() -> None:
    page = _FakePage()
    factory = _make_factory(page)
    sleep = _SleepRecorder()
    r = bmh.observe_after_manual_handoff(
        "https://example.com/",
        handoff_seconds=-1,
        _browser_factory=factory, _env=_empty_env(), _sleep=sleep,
    )
    assert r["success"] is False
    assert r["error_code"] == "HANDOFF_SECONDS_INVALID"
    assert factory.chromium.launch_calls == []
    assert sleep.calls == []


def test_handoff_seconds_over_max_rejected() -> None:
    page = _FakePage()
    factory = _make_factory(page)
    sleep = _SleepRecorder()
    r = bmh.observe_after_manual_handoff(
        "https://example.com/",
        handoff_seconds=61,
        _browser_factory=factory, _env=_empty_env(), _sleep=sleep,
    )
    assert r["success"] is False
    assert r["error_code"] == "HANDOFF_SECONDS_INVALID"
    assert factory.chromium.launch_calls == []


def test_handoff_seconds_bool_rejected() -> None:
    """isinstance(True, int) == True 이므로 bool 은 명시 차단."""
    page = _FakePage()
    factory = _make_factory(page)
    r = bmh.observe_after_manual_handoff(
        "https://example.com/",
        handoff_seconds=True,  # type: ignore[arg-type]
        _browser_factory=factory, _env=_empty_env(),
        _sleep=_SleepRecorder(),
    )
    assert r["success"] is False
    assert r["error_code"] == "HANDOFF_SECONDS_INVALID"


def test_dwell_after_capture_negative_rejected() -> None:
    page = _FakePage()
    factory = _make_factory(page)
    r = bmh.observe_after_manual_handoff(
        "https://example.com/",
        dwell_after_capture_seconds=-1,
        _browser_factory=factory, _env=_empty_env(),
        _sleep=_SleepRecorder(),
    )
    assert r["success"] is False
    assert r["error_code"] == "DWELL_AFTER_CAPTURE_INVALID"


def test_dwell_after_capture_over_max_rejected() -> None:
    page = _FakePage()
    factory = _make_factory(page)
    r = bmh.observe_after_manual_handoff(
        "https://example.com/",
        dwell_after_capture_seconds=31,
        _browser_factory=factory, _env=_empty_env(),
        _sleep=_SleepRecorder(),
    )
    assert r["success"] is False
    assert r["error_code"] == "DWELL_AFTER_CAPTURE_INVALID"


@pytest.mark.parametrize(
    "wait_until",
    ["domcontentloaded", "load", "networkidle", "commit"],
)
def test_wait_until_allowed_values(wait_until: str) -> None:
    page = _FakePage(
        url="about:blank", title="OK",
        html="<html><body><h1>Hello</h1></body></html>", status=200,
    )
    factory = _make_factory(page)
    r = bmh.observe_after_manual_handoff(
        "https://example.com/",
        wait_until=wait_until,
        handoff_seconds=0,
        _browser_factory=factory, _env=_empty_env(),
        _sleep=_SleepRecorder(),
    )
    assert r["success"] is True
    assert page.goto_calls
    assert page.goto_calls[0][1]["wait_until"] == wait_until


def test_wait_until_invalid_rejected() -> None:
    page = _FakePage()
    factory = _make_factory(page)
    r = bmh.observe_after_manual_handoff(
        "https://example.com/",
        wait_until="bogus",
        _browser_factory=factory, _env=_empty_env(),
        _sleep=_SleepRecorder(),
    )
    assert r["success"] is False
    assert r["error_code"] == "WAIT_UNTIL_INVALID"
    assert factory.chromium.launch_calls == []


# ═════════════════════════════════════════════════════════════════════════
# D) 정상 흐름 — handoff sleep, schema, sanitize
# ═════════════════════════════════════════════════════════════════════════

_BASIC_HTML = """<!DOCTYPE html>
<html><head><title>홈택스</title></head>
<body>
  <h1>홈택스 메인</h1>
  <a href='javascript:void(0)'>로그인</a>
  <p>국세청 홈택스</p>
</body></html>"""


def test_handoff_normal_flow_returns_full_schema() -> None:
    page = _FakePage(
        url="about:blank", title="홈택스", html=_BASIC_HTML, status=200,
    )
    factory = _make_factory(page)
    sleep = _SleepRecorder()

    r = bmh.observe_after_manual_handoff(
        "https://www.hometax.go.kr/",
        wait_until="networkidle",
        handoff_seconds=20,
        dwell_after_capture_seconds=0,
        _browser_factory=factory, _env=_empty_env(), _sleep=sleep,
    )

    # 스키마 키.
    for k in (
        "success", "error_code", "warnings",
        "target_url", "final_url_host_path", "title", "status_code",
        "page_state", "handoff",
        "text_excerpt", "text_length",
        "links_count", "buttons_count", "forms_count", "inputs_count",
        "links", "buttons", "forms", "input_types",
        "security_program_signals", "hometax_login_candidates",
    ):
        assert k in r, k

    # handoff 블록.
    assert r["handoff"]["mode"] == "manual"
    assert r["handoff"]["handoff_seconds"] == 20
    assert r["handoff"]["instruction"] == "click_login_only_no_credentials"
    assert r["handoff"]["captured_after_handoff"] is True

    # sleep 호출은 정확히 한 번 (handoff_seconds=20). dwell=0 이므로 추가 sleep 없음.
    assert sleep.calls == [20]

    # launch 옵션은 headless=False, fresh new_context.
    assert factory.chromium.launch_calls
    assert factory.chromium.launch_calls[0].get("headless") is False
    assert factory.browser.new_context_calls == [{}]

    # goto 1회.
    assert page.goto_calls
    assert page.goto_calls[0][0] == "https://www.hometax.go.kr/"
    assert page.goto_calls[0][1]["wait_until"] == "networkidle"

    # target_url query/fragment 제거.
    assert r["target_url"] == "https://www.hometax.go.kr"


def test_handoff_query_fragment_stripped_in_target_url() -> None:
    page = _FakePage(
        url="about:blank", title="홈택스", html=_BASIC_HTML, status=200,
    )
    factory = _make_factory(page)

    r = bmh.observe_after_manual_handoff(
        "https://www.hometax.go.kr/?ref=secret-token#frag",
        handoff_seconds=0,
        _browser_factory=factory, _env=_empty_env(),
        _sleep=_SleepRecorder(),
    )

    blob = str(r)
    assert "secret-token" not in blob
    assert "?ref=" not in blob
    assert "#frag" not in blob
    assert "?" not in r["final_url_host_path"]


def test_handoff_dwell_sleeps_after_capture() -> None:
    page = _FakePage(
        url="about:blank", title="홈택스", html=_BASIC_HTML, status=200,
    )
    factory = _make_factory(page)
    sleep = _SleepRecorder()

    r = bmh.observe_after_manual_handoff(
        "https://www.hometax.go.kr/",
        handoff_seconds=10,
        dwell_after_capture_seconds=5,
        _browser_factory=factory, _env=_empty_env(), _sleep=sleep,
    )
    assert r["success"] is True
    # handoff sleep 후 dwell sleep — 정확히 두 번.
    assert sleep.calls == [10, 5]


def test_handoff_input_value_not_collected() -> None:
    """password input 의 value 는 절대 결과 dict 에 들어가지 않는다."""
    html = """<html><head><title>로그인</title></head>
    <body>
      <form action='/login'>
        <input type='text' name='id' value='SUPER_SECRET_ID'/>
        <input type='password' name='pw' value='SUPER_SECRET_PW'/>
      </form>
    </body></html>"""
    page = _FakePage(
        url="about:blank", title="로그인", html=html, status=200,
    )
    factory = _make_factory(page)

    r = bmh.observe_after_manual_handoff(
        "https://www.hometax.go.kr/",
        handoff_seconds=0,
        _browser_factory=factory, _env=_empty_env(),
        _sleep=_SleepRecorder(),
    )
    assert r["success"] is True
    blob = str(r)
    assert "SUPER_SECRET_ID" not in blob
    assert "SUPER_SECRET_PW" not in blob
    # password type 토큰만 카운트.
    types_blob = ",".join(r["input_types"])
    assert "password" in types_blob
    assert any(f.get("has_password") for f in r["forms"])


def test_handoff_goto_failed_returns_empty_result() -> None:
    page = _FakePage(goto_raises=RuntimeError("navigation timeout"))
    factory = _make_factory(page)
    sleep = _SleepRecorder()
    r = bmh.observe_after_manual_handoff(
        "https://www.hometax.go.kr/",
        handoff_seconds=10,
        _browser_factory=factory, _env=_empty_env(), _sleep=sleep,
    )
    assert r["success"] is False
    assert r["error_code"] == "GOTO_FAILED"
    # goto 실패 시 handoff sleep 도 하지 않는다.
    assert sleep.calls == []
    # handoff 블록은 메타데이터만 표기 (captured_after_handoff=False).
    assert r["handoff"]["mode"] == "manual"
    assert r["handoff"]["captured_after_handoff"] is False


# ═════════════════════════════════════════════════════════════════════════
# E) 금지 환경변수
# ═════════════════════════════════════════════════════════════════════════

def test_forbidden_env_present_blocks_launch() -> None:
    env = _empty_env()
    env["GOOGLE_PASSWORD"] = "x"
    page = _FakePage()
    factory = _make_factory(page)
    sleep = _SleepRecorder()
    r = bmh.observe_after_manual_handoff(
        "https://example.com/",
        _browser_factory=factory, _env=env, _sleep=sleep,
    )
    assert r["success"] is False
    assert r["error_code"] == "FORBIDDEN_ENV_PRESENT"
    assert any(w.startswith("forbidden_env_present:") for w in r["warnings"])
    # launch / sleep 0회.
    assert factory.chromium.launch_calls == []
    assert sleep.calls == []


# ═════════════════════════════════════════════════════════════════════════
# F) helper 부착 — security_program_signals / hometax_login_candidates
# ═════════════════════════════════════════════════════════════════════════

def test_security_program_signals_attached_when_required() -> None:
    """보안프로그램 토큰이 노출된 페이지에서 manual_action_required=True."""
    html = """<html><head><title>보안프로그램 안내</title></head>
    <body>
      <h1>보안프로그램 통합설치</h1>
      <p>홈택스 이용을 위해 필수 프로그램 설치가 필요합니다.</p>
      <a href='/install/sec'>통합설치하기</a>
    </body></html>"""
    page = _FakePage(
        url="about:blank", title="보안프로그램 안내",
        html=html, status=200,
    )
    factory = _make_factory(page)
    r = bmh.observe_after_manual_handoff(
        "https://www.hometax.go.kr/",
        handoff_seconds=0,
        _browser_factory=factory, _env=_empty_env(),
        _sleep=_SleepRecorder(),
    )
    sps = r["security_program_signals"]
    assert isinstance(sps, dict)
    assert sps["manual_action_required"] is True


def test_hometax_candidates_attached_for_hometax_host() -> None:
    """홈택스 호스트면 hometax_login_candidates 가 dict 로 부착."""
    page = _FakePage(
        url="about:blank", title="홈택스",
        html=_BASIC_HTML, status=200,
    )
    factory = _make_factory(page)
    r = bmh.observe_after_manual_handoff(
        "https://www.hometax.go.kr/",
        handoff_seconds=0,
        _browser_factory=factory, _env=_empty_env(),
        _sleep=_SleepRecorder(),
    )
    cand = r["hometax_login_candidates"]
    assert isinstance(cand, dict)
    # candidate dict 의 핵심 키.
    for k in ("login_links", "login_buttons", "login_forms",
              "auth_signals", "candidate_count", "warnings"):
        assert k in cand


def test_hometax_candidates_attached_when_final_url_has_path() -> None:
    """final_url_host_path 가 'host/path' 꼴일 때 host 부분만으로 게이팅."""
    page = _FakePage(
        url="https://www.hometax.go.kr/websquare/websquare.html?w=blah",
        title="홈택스",
        html=_BASIC_HTML, status=200,
    )
    factory = _make_factory(page)
    r = bmh.observe_after_manual_handoff(
        "https://www.hometax.go.kr/",
        handoff_seconds=0,
        _browser_factory=factory, _env=_empty_env(),
        _sleep=_SleepRecorder(),
    )
    assert "/" in r["final_url_host_path"]
    cand = r["hometax_login_candidates"]
    assert isinstance(cand, dict)


def test_hometax_candidates_none_for_non_hometax_host() -> None:
    page = _FakePage(
        url="about:blank", title="Example",
        html="<html><body><h1>Hi</h1></body></html>", status=200,
    )
    factory = _make_factory(page)
    r = bmh.observe_after_manual_handoff(
        "https://example.com/",
        handoff_seconds=0,
        _browser_factory=factory, _env=_empty_env(),
        _sleep=_SleepRecorder(),
    )
    assert r["hometax_login_candidates"] is None


# ═════════════════════════════════════════════════════════════════════════
# G) F-4G-3 — observe_after_user_ready (post-login wrapper)
# ═════════════════════════════════════════════════════════════════════════

def test_user_ready_wrapper_signature_defaults() -> None:
    """user_ready_seconds default 60 / max_text_chars default 10000."""
    import inspect
    sig = inspect.signature(bmh.observe_after_user_ready)
    assert sig.parameters["user_ready_seconds"].default == 60
    assert sig.parameters["max_text_chars"].default == 10_000
    assert sig.parameters["wait_until"].default == "networkidle"
    assert sig.parameters["dwell_after_capture_seconds"].default == 0


def test_user_ready_wrapper_exposed_in_all() -> None:
    assert "observe_after_user_ready" in bmh.__all__


def test_user_ready_seconds_negative_rejected() -> None:
    page = _FakePage()
    factory = _make_factory(page)
    sleep = _SleepRecorder()
    r = bmh.observe_after_user_ready(
        "https://example.com/",
        user_ready_seconds=-1,
        _browser_factory=factory, _env=_empty_env(), _sleep=sleep,
    )
    assert r["success"] is False
    assert r["error_code"] == "USER_READY_SECONDS_INVALID"
    assert factory.chromium.launch_calls == []
    assert sleep.calls == []


def test_user_ready_seconds_over_max_rejected() -> None:
    page = _FakePage()
    factory = _make_factory(page)
    r = bmh.observe_after_user_ready(
        "https://example.com/",
        user_ready_seconds=181,  # max=180
        _browser_factory=factory, _env=_empty_env(),
        _sleep=_SleepRecorder(),
    )
    assert r["success"] is False
    assert r["error_code"] == "USER_READY_SECONDS_INVALID"
    assert factory.chromium.launch_calls == []


def test_user_ready_seconds_at_max_180_accepted() -> None:
    """경계값 180 은 정상 통과 (manual_handoff 의 60 보다 길다)."""
    page = _FakePage(
        url="about:blank", title="홈택스", html=_BASIC_HTML, status=200,
    )
    factory = _make_factory(page)
    sleep = _SleepRecorder()
    r = bmh.observe_after_user_ready(
        "https://www.hometax.go.kr/",
        user_ready_seconds=180,
        _browser_factory=factory, _env=_empty_env(), _sleep=sleep,
    )
    assert r["success"] is True
    assert r["handoff"]["handoff_seconds"] == 180
    assert sleep.calls == [180]


def test_user_ready_seconds_bool_rejected() -> None:
    page = _FakePage()
    factory = _make_factory(page)
    r = bmh.observe_after_user_ready(
        "https://example.com/",
        user_ready_seconds=True,  # type: ignore[arg-type]
        _browser_factory=factory, _env=_empty_env(),
        _sleep=_SleepRecorder(),
    )
    assert r["success"] is False
    assert r["error_code"] == "USER_READY_SECONDS_INVALID"


def test_user_ready_normal_flow_uses_dedicated_instruction() -> None:
    """handoff.instruction 이 user_completes_login_and_navigation_no_credentials.
    기존 manual_handoff 의 click_login_only_no_credentials 와 다른 값."""
    page = _FakePage(
        url="about:blank", title="홈택스", html=_BASIC_HTML, status=200,
    )
    factory = _make_factory(page)
    sleep = _SleepRecorder()

    r = bmh.observe_after_user_ready(
        "https://www.hometax.go.kr/",
        user_ready_seconds=60,
        dwell_after_capture_seconds=0,
        _browser_factory=factory, _env=_empty_env(), _sleep=sleep,
    )

    assert r["success"] is True
    assert r["handoff"]["mode"] == "manual"
    assert r["handoff"]["handoff_seconds"] == 60
    assert (
        r["handoff"]["instruction"]
        == "user_completes_login_and_navigation_no_credentials"
    )
    assert r["handoff"]["captured_after_handoff"] is True
    assert sleep.calls == [60]


def test_user_ready_propagates_instruction_on_validation_failure() -> None:
    """validation 실패 (잘못된 wait_until) 에서도 instruction 이 user_ready 값."""
    page = _FakePage()
    factory = _make_factory(page)
    r = bmh.observe_after_user_ready(
        "https://example.com/",
        wait_until="bogus",
        _browser_factory=factory, _env=_empty_env(),
        _sleep=_SleepRecorder(),
    )
    assert r["success"] is False
    assert r["error_code"] == "WAIT_UNTIL_INVALID"
    assert (
        r["handoff"]["instruction"]
        == "user_completes_login_and_navigation_no_credentials"
    )


def test_user_ready_url_invalid_rejected() -> None:
    r = bmh.observe_after_user_ready(
        "ftp://nope/",
        _env=_empty_env(),
    )
    assert r["success"] is False
    assert r["error_code"] != ""
    assert (
        r["handoff"]["instruction"]
        == "user_completes_login_and_navigation_no_credentials"
    )


def test_user_ready_google_open_only_blocked() -> None:
    r = bmh.observe_after_user_ready(
        "https://drive.google.com/drive/folders/X",
        _env=_empty_env(),
    )
    assert r["success"] is False
    assert r["error_code"] == "GOOGLE_OPEN_ONLY"


def test_user_ready_forbidden_env_blocked() -> None:
    env = _empty_env()
    env["GOOGLE_PASSWORD"] = "x"
    r = bmh.observe_after_user_ready(
        "https://www.hometax.go.kr/",
        _env=env,
    )
    assert r["success"] is False
    assert r["error_code"] == "FORBIDDEN_ENV_PRESENT"


def test_user_ready_dwell_after_capture_invalid_rejected() -> None:
    page = _FakePage()
    factory = _make_factory(page)
    r = bmh.observe_after_user_ready(
        "https://example.com/",
        dwell_after_capture_seconds=31,
        _browser_factory=factory, _env=_empty_env(),
        _sleep=_SleepRecorder(),
    )
    assert r["success"] is False
    assert r["error_code"] == "DWELL_AFTER_CAPTURE_INVALID"


def test_user_ready_attaches_security_signals_and_login_candidates() -> None:
    """홈택스 호스트일 때 helper 결과가 부착되는지."""
    page = _FakePage(
        url="https://www.hometax.go.kr/",
        title="국세청 홈택스",
        html=_BASIC_HTML,
        status=200,
    )
    factory = _make_factory(page)
    r = bmh.observe_after_user_ready(
        "https://www.hometax.go.kr/",
        user_ready_seconds=0,
        _browser_factory=factory, _env=_empty_env(),
        _sleep=_SleepRecorder(),
    )
    assert r["success"] is True
    # helper 부착 — 홈택스 host 이므로 None 아님.
    assert r["security_program_signals"] is not None
    assert r["hometax_login_candidates"] is not None


def test_existing_manual_handoff_still_uses_original_instruction() -> None:
    """regression — observe_after_manual_handoff 의 instruction 은 변경되지 않음."""
    page = _FakePage(
        url="about:blank", title="홈택스", html=_BASIC_HTML, status=200,
    )
    factory = _make_factory(page)
    r = bmh.observe_after_manual_handoff(
        "https://www.hometax.go.kr/",
        handoff_seconds=0,
        _browser_factory=factory, _env=_empty_env(),
        _sleep=_SleepRecorder(),
    )
    assert r["handoff"]["instruction"] == "click_login_only_no_credentials"


# ═════════════════════════════════════════════════════════════════════════
# H) F-4G-3E — fresh hometax goto reset 대응 (warmup + retry)
# ═════════════════════════════════════════════════════════════════════════

class _SequencedFakePage(_FakePage):
    """goto 호출 순서별로 각각 다른 동작을 시뮬레이션.

    ``goto_outcomes`` : 각 항목이 None(=성공) 또는 raise 할 Exception.
    리스트가 소진되면 마지막 동작을 반복한다.
    """

    def __init__(
        self,
        *,
        url: str = "about:blank",
        title: str = "",
        html: str = "",
        status: int = 200,
        goto_outcomes: list[Any] | None = None,
    ) -> None:
        super().__init__(
            url=url, title=title, html=html, status=status,
        )
        self._goto_outcomes = list(goto_outcomes or [])

    def goto(
        self, target: str, *, timeout: int | None = None,
        wait_until: str | None = None,
    ) -> _FakeResponse | None:
        self.goto_calls.append(
            (target, {"timeout": timeout, "wait_until": wait_until}),
        )
        if self._goto_outcomes:
            outcome = self._goto_outcomes.pop(0)
        else:
            outcome = None
        if isinstance(outcome, BaseException):
            raise outcome
        if self.url == "about:blank":
            self.url = target
        return _FakeResponse(self._status)


def test_user_ready_default_signature_has_warmup_retry_params() -> None:
    """observe_after_user_ready 에 신규 옵션 기본값이 보장된다 — backward compat."""
    import inspect
    sig = inspect.signature(bmh.observe_after_user_ready)
    assert sig.parameters["warmup_url"].default is None
    assert sig.parameters["warmup_wait_until"].default == "load"
    assert sig.parameters["goto_retries"].default == 1
    assert sig.parameters["goto_retry_delay_seconds"].default == 1.0
    assert sig.parameters["goto_timeout_ms"].default is None


def test_user_ready_default_no_warmup_no_retry() -> None:
    """default 호출은 warmup 도, 재시도도 하지 않는다."""
    page = _SequencedFakePage(
        url="about:blank", title="홈택스", html=_BASIC_HTML, status=200,
    )
    factory = _make_factory(page)
    sleep = _SleepRecorder()
    r = bmh.observe_after_user_ready(
        "https://www.hometax.go.kr/",
        user_ready_seconds=0,
        _browser_factory=factory, _env=_empty_env(), _sleep=sleep,
    )
    assert r["success"] is True
    # goto 1회만 (warmup 없음, retry 없음).
    assert len(page.goto_calls) == 1
    assert page.goto_calls[0][0] == "https://www.hometax.go.kr/"
    assert r["warmup_attempted"] is False
    assert r["warmup_success"] is False
    assert r["warmup_url"] == ""
    assert r["goto_attempts_used"] == 1


def test_user_ready_warmup_called_before_target() -> None:
    page = _SequencedFakePage(
        url="about:blank", title="홈택스", html=_BASIC_HTML, status=200,
    )
    factory = _make_factory(page)
    sleep = _SleepRecorder()
    r = bmh.observe_after_user_ready(
        "https://www.hometax.go.kr/",
        warmup_url="https://example.com/",
        user_ready_seconds=0,
        _browser_factory=factory, _env=_empty_env(), _sleep=sleep,
    )
    assert r["success"] is True
    assert len(page.goto_calls) == 2
    # warmup goto 가 target goto 보다 먼저 호출.
    assert page.goto_calls[0][0] == "https://example.com/"
    assert page.goto_calls[0][1]["wait_until"] == "load"
    assert page.goto_calls[1][0] == "https://www.hometax.go.kr/"
    assert page.goto_calls[1][1]["wait_until"] == "networkidle"
    assert r["warmup_attempted"] is True
    assert r["warmup_success"] is True
    assert r["warmup_url"] == "https://example.com/"
    assert r["goto_attempts_used"] == 1


def test_user_ready_warmup_failure_does_not_block_target() -> None:
    """warmup goto 실패는 치명 오류 아님 — target goto 계속 시도."""
    warmup_err = RuntimeError("warmup boom")
    page = _SequencedFakePage(
        url="about:blank", title="홈택스", html=_BASIC_HTML, status=200,
        goto_outcomes=[warmup_err, None],
    )
    factory = _make_factory(page)
    sleep = _SleepRecorder()
    r = bmh.observe_after_user_ready(
        "https://www.hometax.go.kr/",
        warmup_url="https://example.com/",
        user_ready_seconds=0,
        _browser_factory=factory, _env=_empty_env(), _sleep=sleep,
    )
    # target goto 는 성공.
    assert r["success"] is True
    assert len(page.goto_calls) == 2
    assert any(w.startswith("warmup_failed:") for w in r["warnings"])
    assert r["warmup_attempted"] is True
    assert r["warmup_success"] is False
    assert r["goto_attempts_used"] == 1


def test_user_ready_target_goto_retry_succeeds_on_second_attempt() -> None:
    """첫 goto 가 ERR_CONNECTION_RESET 류 실패, 두 번째 goto 가 성공."""
    err = RuntimeError("net::ERR_CONNECTION_RESET")
    page = _SequencedFakePage(
        url="about:blank", title="홈택스", html=_BASIC_HTML, status=200,
        goto_outcomes=[err, None],
    )
    factory = _make_factory(page)
    sleep = _SleepRecorder()
    r = bmh.observe_after_user_ready(
        "https://www.hometax.go.kr/",
        goto_retries=2,
        goto_retry_delay_seconds=0.5,
        user_ready_seconds=0,
        _browser_factory=factory, _env=_empty_env(), _sleep=sleep,
    )
    assert r["success"] is True
    # target goto 만 두 번 호출 (warmup 없음).
    assert len(page.goto_calls) == 2
    assert page.goto_calls[0][0] == "https://www.hometax.go.kr/"
    assert page.goto_calls[1][0] == "https://www.hometax.go.kr/"
    assert any(
        w.startswith("goto_attempt_failed:1:") for w in r["warnings"]
    )
    assert r["goto_attempts_used"] == 2
    # retry delay sleep 1회 + user_ready_seconds=0 이라 sleep 추가 없음.
    assert 0.5 in sleep.calls


def test_user_ready_target_goto_all_attempts_fail() -> None:
    err = RuntimeError("net::ERR_CONNECTION_RESET")
    page = _SequencedFakePage(
        url="about:blank", title="홈택스", html=_BASIC_HTML, status=200,
        goto_outcomes=[err, err, err],
    )
    factory = _make_factory(page)
    sleep = _SleepRecorder()
    r = bmh.observe_after_user_ready(
        "https://www.hometax.go.kr/",
        goto_retries=3,
        goto_retry_delay_seconds=0.0,
        user_ready_seconds=0,
        _browser_factory=factory, _env=_empty_env(), _sleep=sleep,
    )
    assert r["success"] is False
    assert r["error_code"] == "GOTO_FAILED"
    assert len(page.goto_calls) == 3
    # 모든 attempt 실패가 warnings 에 남는다.
    failed_warnings = [
        w for w in r["warnings"]
        if w.startswith("goto_attempt_failed:")
    ]
    assert len(failed_warnings) == 3
    assert r["goto_attempts_used"] == 3


def test_user_ready_warmup_meta_included_in_failed_goto_result() -> None:
    """target goto 가 모두 실패해도 warmup_attempted/warmup_success 가 포함."""
    err = RuntimeError("boom")
    page = _SequencedFakePage(
        url="about:blank", title="홈택스", html=_BASIC_HTML, status=200,
        goto_outcomes=[None, err],  # warmup ok, target fail
    )
    factory = _make_factory(page)
    sleep = _SleepRecorder()
    r = bmh.observe_after_user_ready(
        "https://www.hometax.go.kr/",
        warmup_url="https://example.com/",
        goto_retries=1,
        user_ready_seconds=0,
        _browser_factory=factory, _env=_empty_env(), _sleep=sleep,
    )
    assert r["success"] is False
    assert r["error_code"] == "GOTO_FAILED"
    assert r["warmup_attempted"] is True
    assert r["warmup_success"] is True
    assert r["warmup_url"] == "https://example.com/"
    assert r["goto_attempts_used"] == 1


def test_user_ready_invalid_warmup_url_falls_back_with_warning() -> None:
    """잘못된 warmup_url 은 치명 오류가 아니라 warning + skip."""
    page = _SequencedFakePage(
        url="about:blank", title="홈택스", html=_BASIC_HTML, status=200,
    )
    factory = _make_factory(page)
    sleep = _SleepRecorder()
    r = bmh.observe_after_user_ready(
        "https://www.hometax.go.kr/",
        warmup_url="ftp://nope/",  # invalid scheme
        user_ready_seconds=0,
        _browser_factory=factory, _env=_empty_env(), _sleep=sleep,
    )
    # warmup 은 skip 되고 target goto 만 1회.
    assert r["success"] is True
    assert len(page.goto_calls) == 1
    assert page.goto_calls[0][0] == "https://www.hometax.go.kr/"
    assert "warmup_url_invalid" in r["warnings"]
    assert r["warmup_attempted"] is False
    assert r["warmup_success"] is False


def test_user_ready_goto_timeout_ms_overrides_timeout_ms() -> None:
    """goto_timeout_ms 는 page.goto(timeout=...) 에 그대로 전달된다."""
    page = _SequencedFakePage(
        url="about:blank", title="홈택스", html=_BASIC_HTML, status=200,
    )
    factory = _make_factory(page)
    sleep = _SleepRecorder()
    r = bmh.observe_after_user_ready(
        "https://www.hometax.go.kr/",
        goto_timeout_ms=90_000,
        user_ready_seconds=0,
        _browser_factory=factory, _env=_empty_env(), _sleep=sleep,
    )
    assert r["success"] is True
    assert page.goto_calls[0][1]["timeout"] == 90_000


def test_user_ready_warmup_meta_default_in_validation_error() -> None:
    """validation 실패 결과에도 warmup_attempted=False / goto_attempts_used=0
    가 포함되어야 한다 — 호출자가 안전하게 dict.get 으로 접근 가능."""
    r = bmh.observe_after_user_ready(
        "ftp://nope/",
        _env=_empty_env(),
    )
    assert r["success"] is False
    assert r["warmup_attempted"] is False
    assert r["warmup_success"] is False
    assert r["warmup_url"] == ""
    assert r["goto_attempts_used"] == 0


def test_user_ready_goto_retries_clipped_to_max() -> None:
    """goto_retries 가 cap 을 초과하면 _MAX 로 클립."""
    err = RuntimeError("boom")
    page = _SequencedFakePage(
        url="about:blank", title="홈택스", html=_BASIC_HTML, status=200,
        goto_outcomes=[err] * 10,
    )
    factory = _make_factory(page)
    sleep = _SleepRecorder()
    r = bmh.observe_after_user_ready(
        "https://www.hometax.go.kr/",
        goto_retries=999,  # clip to _MAX_GOTO_RETRIES
        goto_retry_delay_seconds=0.0,
        user_ready_seconds=0,
        _browser_factory=factory, _env=_empty_env(), _sleep=sleep,
    )
    assert r["success"] is False
    # max attempts == _MAX_GOTO_RETRIES (5)
    assert r["goto_attempts_used"] == bmh._MAX_GOTO_RETRIES
    assert len(page.goto_calls) == bmh._MAX_GOTO_RETRIES

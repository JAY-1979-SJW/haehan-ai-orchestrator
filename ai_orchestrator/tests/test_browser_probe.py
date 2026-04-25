"""local_agent.browser_probe + action_open_local_browser_probe 검증 (E-2).

원칙:
  - local_agent 에서만 Playwright 사용 — server 코드는 import 도 금지.
  - headless=False 고정.
  - dedicated HaehanAI 프로필만 사용. 기본 Chrome/Edge 프로필 차단.
  - page.fill / click / type / press / keyboard / mouse / page.content /
    cookies / storage_state / localStorage / sessionStorage / evaluate
    호출 없음 (AST 검사).
  - raw URL / raw title / 절대경로 미반환.
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
from local_agent import browser_probe as bp  # noqa: E402


# ─── Playwright 가짜 객체 ─────────────────────────────────────────────────

class _FakePage:
    """허용 API 만 노출하는 fake page."""

    def __init__(
        self, *, url: str = "about:blank", title: str = "",
    ) -> None:
        self.url = url
        self._title = title
        self.goto_calls: list[tuple[str, dict]] = []
        self.bring_to_front_calls = 0
        self.wait_for_load_state_calls: list[str] = []

    def goto(
        self, url: str, *, timeout: int | None = None,
        wait_until: str | None = None,
    ) -> None:
        self.goto_calls.append(
            (url, {"timeout": timeout, "wait_until": wait_until}),
        )
        self.url = url

    def title(self) -> str:
        return self._title

    def bring_to_front(self) -> None:
        self.bring_to_front_calls += 1

    def wait_for_load_state(self, state: str = "load") -> None:
        self.wait_for_load_state_calls.append(state)


class _FakeContext:
    def __init__(self, pages: list[_FakePage] | None = None) -> None:
        self.pages: list[_FakePage] = pages or []
        self.closed = False
        self.new_page_calls = 0

    def new_page(self) -> _FakePage:
        self.new_page_calls += 1
        page = _FakePage()
        self.pages.append(page)
        return page

    def close(self) -> None:
        self.closed = True


class _FakeChromium:
    def __init__(
        self,
        *,
        context: _FakeContext | None = None,
        raise_on_launch: Exception | None = None,
    ) -> None:
        self._context = context if context is not None else _FakeContext()
        self._raise = raise_on_launch
        self.launch_calls: list[dict[str, Any]] = []

    def launch_persistent_context(self, **kwargs: Any) -> _FakeContext:
        self.launch_calls.append(dict(kwargs))
        if self._raise is not None:
            raise self._raise
        return self._context


class _FakePlaywright:
    def __init__(self, chromium: _FakeChromium) -> None:
        self.chromium = chromium


class _FakePlaywrightCM:
    """``with sync_playwright() as pw:`` 패턴을 흉내내는 context manager."""

    def __init__(self, chromium: _FakeChromium) -> None:
        self._pw = _FakePlaywright(chromium)
        self.entered = False
        self.exited = False

    def __enter__(self) -> _FakePlaywright:
        self.entered = True
        return self._pw

    def __exit__(self, *exc: Any) -> None:
        self.exited = True


def _make_factory(chromium: _FakeChromium):
    def _factory():
        return _FakePlaywrightCM(chromium)
    return _factory


class _ImmediateClock:
    """단조 시계 fake — sleep 즉시 시간 진행."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(float(seconds))
        self.now += float(seconds)


def _make_env(tmp_path: Path, **overrides: str) -> dict:
    env = {
        "LOCALAPPDATA": str(tmp_path / "AppData" / "Local"),
        "USERPROFILE": str(tmp_path),
        "PATH": "",
        "HAEHAN_BROWSER_PROFILE_ROOT": str(tmp_path / "BrowserProfiles"),
    }
    for k in bl._FORBIDDEN_ENV_VARS:
        env.pop(k, None)
    env.update(overrides)
    return env


def _install_chrome_pf(monkeypatch: pytest.MonkeyPatch) -> None:
    chrome_pf = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    monkeypatch.setattr(
        bl, "_candidate_exists", lambda p: p == chrome_pf,
    )
    monkeypatch.setattr(bl, "_which_command", lambda c, env: None)
    monkeypatch.setattr(bl, "_iter_ms_playwright_chromium", lambda env: ())


# ═════════════════════════════════════════════════════════════════════════
# 1) 등록 / 디스패처
# ═════════════════════════════════════════════════════════════════════════

def test_action_open_local_browser_probe_is_registered() -> None:
    assert "open_local_browser_probe" in actions._ACTIONS
    assert actions._ACTIONS["open_local_browser_probe"] is \
        actions.action_open_local_browser_probe
    assert "open_local_browser_probe" not in actions.FORBIDDEN_ACTIONS


def test_existing_open_local_browser_action_unchanged() -> None:
    """E단계에서 만든 open_local_browser action 은 그대로 유지되어야 한다."""
    assert "open_local_browser" in actions._ACTIONS
    assert actions._ACTIONS["open_local_browser"] is \
        actions.action_open_local_browser


def test_action_meta_registered() -> None:
    from agent import action_registry as ar

    meta = ar.get_meta("open_local_browser_probe")
    assert meta is not None
    assert meta.category == ar.CATEGORY_LOCAL_BROWSER
    assert meta.risk_level == ar.RISK_MEDIUM
    assert meta.requires_browser is True
    assert meta.requires_secret is False
    assert meta.read_only is True


def test_action_in_policy_allowlist() -> None:
    from agent import policy

    assert "open_local_browser_probe" in policy.ALLOWED_ACTIONS


# ═════════════════════════════════════════════════════════════════════════
# 2) Playwright 사용 범위 — server 는 import 금지
# ═════════════════════════════════════════════════════════════════════════

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SERVER_ROOT = _REPO_ROOT / "ai_orchestrator"


def _iter_server_py() -> list[Path]:
    out: list[Path] = []
    for p in _SERVER_ROOT.rglob("*.py"):
        if "tests" in p.parts:
            continue
        out.append(p)
    return out


def test_server_does_not_import_browser_probe() -> None:
    offenders: list[Path] = []
    for py in _iter_server_py():
        text = py.read_text(encoding="utf-8", errors="replace")
        if re.search(
            r"^\s*(from\s+local_agent\s+import\s+browser_probe|"
            r"from\s+local_agent\.browser_probe\s+import|"
            r"import\s+local_agent\.browser_probe)\b",
            text,
            re.M,
        ):
            offenders.append(py)
    assert offenders == [], \
        f"server code must not import browser_probe: {offenders}"


def test_browser_probe_is_local_agent_only() -> None:
    """E-2 신규 모듈인 browser_probe 는 local_agent 트리에만 존재해야 한다.
    기존 서버측 Playwright 경로(playwright_connector / sites/browser) 는
    E-2 와 무관하므로 검사 대상에서 제외하지만, 신규 probe 가 서버 코드에
    스며들었는지는 별도 검사한다 (test_server_does_not_import_browser_probe)."""
    expected = _REPO_ROOT / "local_agent" / "browser_probe.py"
    assert expected.is_file(), f"browser_probe must live under local_agent/: {expected}"
    # 서버 트리에 같은 이름의 파일이 새로 생기면 즉시 거절.
    server_offender = _SERVER_ROOT / "browser_probe.py"
    assert not server_offender.exists(), \
        f"browser_probe must not exist in server tree: {server_offender}"


# ═════════════════════════════════════════════════════════════════════════
# 3) AST 검사 — 금지된 Playwright API 호출 없음
# ═════════════════════════════════════════════════════════════════════════

_FORBIDDEN_CALL_ATTRS = {
    "fill", "press", "click", "type", "select_option",
    "set_input_files",
    "content",                                # page.content() 금지
    "cookies", "add_cookies",
    "evaluate", "evaluate_handle",
    "storage_state",
}
_FORBIDDEN_ATTR_USAGE = {"keyboard", "mouse"}
_FORBIDDEN_NAMES = {"localStorage", "sessionStorage"}


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


def test_browser_probe_module_has_no_forbidden_apis() -> None:
    src = Path(bp.__file__).read_text(encoding="utf-8")
    offenders = _scan_forbidden_apis(src)
    assert offenders == [], \
        f"forbidden API patterns in browser_probe: {offenders}"


def test_action_function_has_no_forbidden_apis() -> None:
    src = Path(actions.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    target = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and \
                node.name == "action_open_local_browser_probe":
            target = node
            break
    assert target is not None, "action_open_local_browser_probe not found"

    offenders: list[tuple[str, int]] = []
    for node in ast.walk(target):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in _FORBIDDEN_CALL_ATTRS:
                offenders.append((f"call:.{node.func.attr}(", node.lineno))
        if isinstance(node, ast.Attribute) and \
                node.attr in _FORBIDDEN_ATTR_USAGE:
            offenders.append((f"attr:.{node.attr}", node.lineno))
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            offenders.append((f"name:{node.id}", node.lineno))
    assert offenders == [], \
        f"forbidden API in action_open_local_browser_probe: {offenders}"


# ═════════════════════════════════════════════════════════════════════════
# 4) headless / launch 인자 검증
# ═════════════════════════════════════════════════════════════════════════

def test_launch_persistent_context_is_called_with_headless_false(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _install_chrome_pf(monkeypatch)
    chromium = _FakeChromium()
    env = _make_env(tmp_path)

    result = bp.probe_visible_browser(
        "https://example.com/",
        site_policy=bl.SITE_POLICY_GOOGLE,
        wait_seconds=1,
        poll_interval_seconds=1,
        _browser_factory=_make_factory(chromium),
        _clock=_ImmediateClock(),
        _env=env,
    )

    assert result["success"] is True, result
    assert chromium.launch_calls, "launch_persistent_context not called"
    call = chromium.launch_calls[0]
    assert call.get("headless") is False, call
    # user_data_dir 는 dedicated 프로필 루트 내부.
    udd = str(call.get("user_data_dir", ""))
    expected_root = str(tmp_path / "BrowserProfiles" / "chrome")
    assert expected_root in udd, (udd, expected_root)
    # chrome 은 channel="chrome".
    assert call.get("channel") == "chrome"
    # args 에 --headless / --remote-debugging-port 절대 없음.
    args = call.get("args") or []
    assert not any(a.startswith("--headless") for a in args)
    assert not any(a.startswith("--remote-debugging-port") for a in args)


def test_msedge_uses_msedge_channel(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    monkeypatch.setattr(bl, "_candidate_exists", lambda p: p == edge)
    monkeypatch.setattr(bl, "_which_command", lambda c, env: None)
    monkeypatch.setattr(bl, "_iter_ms_playwright_chromium", lambda env: ())
    chromium = _FakeChromium()
    env = _make_env(tmp_path)

    result = bp.probe_visible_browser(
        "https://example.gov.kr/",
        site_policy=bl.SITE_POLICY_AUTO,
        wait_seconds=1,
        _browser_factory=_make_factory(chromium),
        _clock=_ImmediateClock(),
        _env=env,
    )

    assert result["success"] is True
    assert result["browser_provider"] == "msedge"
    assert chromium.launch_calls[0].get("channel") == "msedge"


def test_chromium_uses_executable_path_not_channel(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    bundled = str(
        tmp_path / "AppData" / "Local" / "ms-playwright"
        / "chromium-1234" / "chrome-win" / "chrome.exe"
    )
    monkeypatch.setattr(bl, "_candidate_exists", lambda p: p == bundled)
    monkeypatch.setattr(bl, "_which_command", lambda c, env: None)
    monkeypatch.setattr(
        bl, "_iter_ms_playwright_chromium", lambda env: (bundled,),
    )
    chromium = _FakeChromium()
    env = _make_env(tmp_path)

    result = bp.probe_visible_browser(
        "https://example.com/",
        provider_override="chromium",
        wait_seconds=1,
        _browser_factory=_make_factory(chromium),
        _clock=_ImmediateClock(),
        _env=env,
    )

    assert result["success"] is True
    assert result["browser_provider"] == "chromium"
    call = chromium.launch_calls[0]
    assert "channel" not in call
    # executable_path 는 launch 인자에는 들어가지만 반환 dict 에는 노출되지 않음.
    assert call.get("executable_path") == bundled
    assert bundled not in str(result), \
        "chromium executable path must not leak into result"


# ═════════════════════════════════════════════════════════════════════════
# 5) dedicated 프로필 / 기본 프로필 차단
# ═════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "marker_root",
    [
        r"C:\Users\user\AppData\Local\Google\Chrome\User Data",
        r"C:\Users\user\AppData\Local\Microsoft\Edge\User Data",
    ],
)
def test_default_profile_root_is_blocked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, marker_root: str,
) -> None:
    _install_chrome_pf(monkeypatch)
    chromium = _FakeChromium()
    env = _make_env(tmp_path, HAEHAN_BROWSER_PROFILE_ROOT=marker_root)

    result = bp.probe_visible_browser(
        "https://example.com/",
        site_policy=bl.SITE_POLICY_GOOGLE,
        _browser_factory=_make_factory(chromium),
        _clock=_ImmediateClock(),
        _env=env,
    )

    assert result["success"] is False
    assert chromium.launch_calls == [], \
        "Playwright launch must not be invoked for blocked profile"
    assert any("default_profile_blocked" in w for w in result["warnings"])


def test_dedicated_profile_dir_is_under_haehan_root_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _install_chrome_pf(monkeypatch)
    chromium = _FakeChromium()
    env = _make_env(tmp_path)

    result = bp.probe_visible_browser(
        "https://example.com/",
        site_policy=bl.SITE_POLICY_GOOGLE,
        profile_name="haehan_google",
        wait_seconds=1,
        _browser_factory=_make_factory(chromium),
        _clock=_ImmediateClock(),
        _env=env,
    )

    assert result["success"] is True
    udd = str(chromium.launch_calls[0].get("user_data_dir", ""))
    assert "BrowserProfiles" in udd
    assert udd.endswith("haehan_google") or "haehan_google" in udd
    # 절대 경로는 결과에 노출되지 않음.
    assert udd not in str(result)


def test_profile_name_with_separator_is_rejected(tmp_path: Path) -> None:
    env = _make_env(tmp_path)
    for bad in ("foo/bar", "..", "../x", "C:/x", "~home"):
        result = bp.probe_visible_browser(
            "https://example.com/",
            profile_name=bad,
            _browser_factory=_make_factory(_FakeChromium()),
            _clock=_ImmediateClock(),
            _env=env,
        )
        assert result["success"] is False, bad
        assert any(
            w.startswith("profile_name_") for w in result["warnings"]
        ), (bad, result["warnings"])


# ═════════════════════════════════════════════════════════════════════════
# 6) 민감 환경변수 차단 — Playwright launch 호출 없음
# ═════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("forbidden_key", list(bl._FORBIDDEN_ENV_VARS))
def test_forbidden_env_var_blocks_probe_before_playwright_launch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, forbidden_key: str,
) -> None:
    _install_chrome_pf(monkeypatch)
    chromium = _FakeChromium()
    env = _make_env(tmp_path)
    env[forbidden_key] = "do-not-leak-this"

    result = bp.probe_visible_browser(
        "https://example.com/",
        _browser_factory=_make_factory(chromium),
        _clock=_ImmediateClock(),
        _env=env,
    )

    assert result["success"] is False
    assert chromium.launch_calls == []
    assert any(
        w == f"forbidden_env_present:{forbidden_key}"
        for w in result["warnings"]
    ), result["warnings"]
    assert "do-not-leak-this" not in str(result)


# ═════════════════════════════════════════════════════════════════════════
# 7) 입력 검증
# ═════════════════════════════════════════════════════════════════════════

def test_empty_url_is_rejected(tmp_path: Path) -> None:
    env = _make_env(tmp_path)
    result = bp.probe_visible_browser(
        "", _browser_factory=_make_factory(_FakeChromium()),
        _clock=_ImmediateClock(), _env=env,
    )
    assert result["success"] is False
    assert "invalid_target_url" in result["warnings"]


@pytest.mark.parametrize(
    "bad_url",
    ["file:///etc/passwd", "javascript:alert(1)", "data:text/html,",
     "ftp://example.com"],
)
def test_non_http_scheme_rejected(tmp_path: Path, bad_url: str) -> None:
    env = _make_env(tmp_path)
    result = bp.probe_visible_browser(
        bad_url, _browser_factory=_make_factory(_FakeChromium()),
        _clock=_ImmediateClock(), _env=env,
    )
    assert result["success"] is False
    assert "target_url_scheme_forbidden" in result["warnings"]


def test_unsupported_provider_override(tmp_path: Path) -> None:
    env = _make_env(tmp_path)
    result = bp.probe_visible_browser(
        "https://example.com/",
        provider_override="firefox",
        _browser_factory=_make_factory(_FakeChromium()),
        _clock=_ImmediateClock(), _env=env,
    )
    assert result["success"] is False
    assert any(
        w.startswith("unsupported_provider:") for w in result["warnings"]
    )


# ═════════════════════════════════════════════════════════════════════════
# 8) context.pages 전수 관찰 + raw URL/title 미노출
# ═════════════════════════════════════════════════════════════════════════

def test_context_pages_observation_aggregates_across_tabs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """OAuth/popup 흐름: main 탭은 target 으로 이동, 별도 popup 탭에 로그인
    화면이 떠 있는 상태. context.pages 전수 관찰로 popup 도 집계되는지 확인.

    주: F-2 정책 도입 이후 ``studio.youtube.com`` 등 Google 계열은 probe
    대상에서 제외되므로, 본 테스트의 target_url 은 일반 도메인을 쓴다.
    popup 의 raw URL 은 fake _FakePage 에 직접 주입된 값이므로 probe 의
    Google block 과 무관하게 popup 분류 / 토큰 미노출만 검증한다."""
    _install_chrome_pf(monkeypatch)
    # main page — goto 후 target URL 로 갱신됨.
    main_page = _FakePage(url="about:blank", title="Example Portal Login")
    # popup — OAuth/login flow. URL 에 secret 토큰 포함, title 에 raw 문자열 포함.
    popup = _FakePage(
        url="https://accounts.google.com/signin?continue=secret-token-xyz",
        title="Sign in - Google Accounts",
    )
    ctx = _FakeContext(pages=[main_page, popup])
    chromium = _FakeChromium(context=ctx)
    env = _make_env(tmp_path)

    result = bp.probe_visible_browser(
        "https://example.com/",
        site_policy=bl.SITE_POLICY_GOOGLE,
        wait_seconds=1,
        poll_interval_seconds=1,
        _browser_factory=_make_factory(chromium),
        _clock=_ImmediateClock(),
        _env=env,
    )

    assert result["success"] is True
    assert result["pages_observed_count"] >= 2
    # main 탭이 goto 로 target host 에 도달했으므로 across_pages 도 True.
    assert result["success_url_observed_across_pages"] is True
    # popup 이 accounts.google.com 이므로 observed_login_page=True.
    assert result["observed_login_page"] is True

    blob = str(result)
    # raw URL / raw title / 토큰 노출 없음 — host+path / category 만.
    assert "Sign in - Google Accounts" not in blob
    assert "secret-token-xyz" not in blob
    assert "?continue=" not in blob
    # final_url_host_path 는 main page (= goto 후 target host).
    assert result["final_url_host_path"] == "example.com"
    # title_category 는 main page title 기준.
    assert result["title_category"] == "login_required"


def test_result_keys_are_whitelisted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _install_chrome_pf(monkeypatch)
    page = _FakePage(url="https://example.com/", title="Example Domain")
    ctx = _FakeContext(pages=[page])
    chromium = _FakeChromium(context=ctx)
    env = _make_env(tmp_path)

    result = bp.probe_visible_browser(
        "https://example.com/",
        site_policy=bl.SITE_POLICY_GOOGLE,
        wait_seconds=1,
        _browser_factory=_make_factory(chromium),
        _clock=_ImmediateClock(),
        _env=env,
    )

    expected = {
        "success", "target_url", "browser_provider", "title_category",
        "final_url_host_path", "pages_observed_count",
        "success_url_observed_across_pages", "observed_login_page",
        "warnings",
    }
    assert set(result.keys()) == expected
    # 절대 노출되지 않아야 할 키.
    assert "cookies" not in result
    assert "storage_state" not in result
    assert "title" not in result  # raw title 키 자체가 없어야 함
    # raw page title 문자열 자체도 결과에 들어가지 않음 (generic 카테고리만).
    assert result["title_category"] == "generic"
    assert "Example Domain" not in str(result)


# ═════════════════════════════════════════════════════════════════════════
# 9) action 디스패처 통합 테스트
# ═════════════════════════════════════════════════════════════════════════

def test_action_dispatch_routes_to_probe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _install_chrome_pf(monkeypatch)
    page = _FakePage(url="https://example.com/", title="Example")
    ctx = _FakeContext(pages=[page])
    chromium = _FakeChromium(context=ctx)
    env = _make_env(tmp_path)

    result = actions.execute_action(
        "open_local_browser_probe",
        {
            "url": "https://example.com/",
            "site_policy": "google",
            "wait_seconds": 1,
            "_browser_factory": _make_factory(chromium),
            "_clock": _ImmediateClock(),
            "_env": env,
        },
    )

    assert result.success is True, (result.error_code, result.error)
    assert result.data["success"] is True
    assert result.data["title_category"] == "generic"
    assert result.data["final_url_host_path"].startswith("example.com")
    assert "Example" not in str(result.data)


def test_action_missing_url_returns_fail() -> None:
    result = actions.action_open_local_browser_probe({})
    assert result.success is False
    assert result.error_code == "MISSING_URL"


@pytest.mark.parametrize(
    "bad_url",
    ["file:///x", "javascript:1", "data:,", "ftp://x", "about:blank"],
)
def test_action_non_http_url_rejected(bad_url: str) -> None:
    result = actions.action_open_local_browser_probe({"url": bad_url})
    assert result.success is False
    assert result.error_code == "URL_SCHEME_NOT_ALLOWED"


def test_action_invalid_provider_override(tmp_path: Path) -> None:
    result = actions.action_open_local_browser_probe({
        "url": "https://example.com/",
        "provider_override": "firefox",
    })
    assert result.success is False
    assert result.error_code == "UNSUPPORTED_PROVIDER"


def test_action_invalid_wait_seconds() -> None:
    result = actions.action_open_local_browser_probe({
        "url": "https://example.com/",
        "wait_seconds": "not-int",
    })
    assert result.success is False
    assert result.error_code == "INVALID_PARAM"


def test_action_propagates_probe_failure_as_fail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """browser_probe.probe_visible_browser 가 launched=False 로 거절하면
    action 도 BROWSER_PROBE_FAILED 로 전파해야 한다."""
    monkeypatch.setattr(bl, "_candidate_exists", lambda p: False)
    monkeypatch.setattr(bl, "_which_command", lambda c, env: None)
    monkeypatch.setattr(bl, "_iter_ms_playwright_chromium", lambda env: ())

    env = _make_env(tmp_path)
    result = actions.action_open_local_browser_probe({
        "url": "https://example.com/",
        "_env": env,
        "_browser_factory": _make_factory(_FakeChromium()),
        "_clock": _ImmediateClock(),
    })
    assert result.success is False
    assert result.error_code == "BROWSER_PROBE_FAILED"
    assert "no_browser_found" in result.error
    assert result.data["success"] is False
    assert result.data["pages_observed_count"] == 0


# ═════════════════════════════════════════════════════════════════════════
# 10) helper unit — title category / url host_path
# ═════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "title,expected",
    [
        ("", "empty"),
        ("   ", "empty"),
        ("Sign in - Google Accounts", "login_required"),
        ("로그인 - 네이버", "login_required"),
        ("YouTube Studio", "youtube_studio"),
        ("YouTube", "youtube"),
        ("내 Google 계정", "google_account"),
        ("네이버", "naver"),
        ("Example Domain", "generic"),
    ],
)
def test_title_category(title: str, expected: str) -> None:
    assert bp._title_category(title) == expected


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://example.com/", "example.com"),
        ("https://example.com/path/sub?q=secret#frag", "example.com/path/sub"),
        # host 만 lowercase, path case 는 보존.
        ("https://STUDIO.youtube.com/channel/UC-secret",
         "studio.youtube.com/channel/UC-secret"),
        ("", ""),
        ("not-a-url", ""),
    ],
)
def test_url_host_path(url: str, expected: str) -> None:
    assert bp._url_host_path(url) == expected


# ═════════════════════════════════════════════════════════════════════════
# 11) F-2 — Google / YouTube open-only 정책
#
#     accounts.google.com / google.com / studio.youtube.com / youtube.com /
#     gmail.com / drive.google.com 은 ``probe_visible_browser`` 가
#     Playwright launch 전에 거절해야 한다. raw URL query/fragment 는
#     결과 어디에도 노출되지 않는다.
# ═════════════════════════════════════════════════════════════════════════


def test_is_google_open_only_url_classifier() -> None:
    """browser_launcher 에 노출된 host 분류 헬퍼 단위 검증."""
    positive = [
        "https://accounts.google.com/signin",
        "https://google.com/",
        "https://www.google.com/",
        "https://studio.youtube.com/",
        "https://www.youtube.com/",
        "https://m.youtube.com/",
        "https://mail.google.com/",
        "https://gmail.com/",
        "https://drive.google.com/",
        "HTTPS://STUDIO.YOUTUBE.COM/abc",
    ]
    for u in positive:
        assert bl.is_google_open_only_url(u) is True, u

    negative = [
        "https://example.com/",
        "https://googleblog.com/",
        "https://notyoutube.com/",
        "https://google.com.attacker.test/",
        "https://example.com/?next=https://accounts.google.com/",
        "",
        "not-a-url",
        "ftp://google.com/",
    ]
    for u in negative:
        assert bl.is_google_open_only_url(u) is False, u


def test_google_policy_constants_are_exposed() -> None:
    """F-2 분류 토큰이 browser_launcher 에 명시적으로 노출되어야 한다."""
    assert bl.SITE_POLICY_GOOGLE_OPEN_ONLY == "google_open_only"
    assert bl.SITE_POLICY_YOUTUBE_OPEN_ONLY == "youtube_open_only"
    assert bl.SITE_POLICY_GENERIC == "generic"
    assert bl.SITE_POLICY_PUBLIC_FETCH == "public_fetch"
    assert bl.SITE_POLICY_LOCAL_PROBE_ALLOWED == "local_probe_allowed"
    # 필수 도메인 모두 포함.
    expected = {
        "accounts.google.com", "google.com", "studio.youtube.com",
        "youtube.com", "gmail.com", "drive.google.com",
    }
    assert expected.issubset(set(bl.GOOGLE_OPEN_ONLY_DOMAINS))


@pytest.mark.parametrize(
    "google_url,expected_host_path,forbidden_query_tokens",
    [
        # raw query / fragment 가 결과에 흘러들면 안 된다 (path 는 _url_host_path
        # 정책상 host+path 까지 유지됨).
        ("https://studio.youtube.com/?next=secret-redirect#frag",
         "studio.youtube.com",
         ["?next=", "secret-redirect", "#frag"]),
        ("https://accounts.google.com/signin?continue=secret-state-token",
         "accounts.google.com/signin",
         ["?continue=", "secret-state-token"]),
        ("https://drive.google.com/drive/folders/Folder1?usp=sharing&token=ZZZ",
         "drive.google.com/drive/folders/Folder1",
         ["?usp=sharing", "token=ZZZ"]),
        ("https://www.youtube.com/watch?v=SECRETVID",
         "www.youtube.com/watch",
         ["?v=SECRETVID", "SECRETVID"]),
        ("https://mail.google.com/mail/u/0/?dashboard=AAA",
         "mail.google.com/mail/u/0",
         ["?dashboard=", "AAA"]),
        ("https://gmail.com/?session=AAA",
         "gmail.com",
         ["?session=", "session=AAA"]),
    ],
)
def test_google_url_blocked_before_playwright_launch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    google_url: str, expected_host_path: str,
    forbidden_query_tokens: list[str],
) -> None:
    """probe_visible_browser 는 Google/YouTube URL 을 Playwright launch
    전에 거절해야 한다. fake chromium 의 launch_persistent_context 는
    절대 호출되지 않아야 한다."""
    _install_chrome_pf(monkeypatch)
    chromium = _FakeChromium()
    env = _make_env(tmp_path)

    result = bp.probe_visible_browser(
        google_url,
        site_policy=bl.SITE_POLICY_GOOGLE,
        wait_seconds=1,
        _browser_factory=_make_factory(chromium),
        _clock=_ImmediateClock(),
        _env=env,
    )

    # 1) 차단 결과
    assert result["success"] is False
    assert result.get("error_code") == "GOOGLE_OPEN_ONLY"
    assert "google_open_only_use_open_local_browser" in result["warnings"]

    # 2) Playwright 는 호출되지 않아야 한다.
    assert chromium.launch_calls == [], \
        "Playwright launch_persistent_context must not be invoked"

    # 3) target_url 은 raw 입력을 그대로 echo 하지 않는다 (query/fragment
    #    유출 금지). final_url_host_path 만 host+path 로 노출.
    assert result["target_url"] == ""
    assert result["final_url_host_path"] == expected_host_path

    # 4) raw query / fragment 토큰이 결과 어디에도 들어가지 않는다.
    blob = str(result)
    for tok in forbidden_query_tokens:
        assert tok not in blob, (tok, blob)


@pytest.mark.parametrize(
    "google_url",
    [
        "https://studio.youtube.com/",
        "https://accounts.google.com/",
        "https://drive.google.com/",
        "https://www.youtube.com/",
        "https://gmail.com/",
        "https://mail.google.com/",
    ],
)
def test_action_propagates_google_open_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, google_url: str,
) -> None:
    """action_open_local_browser_probe 가 GOOGLE_OPEN_ONLY 를 그대로 전파."""
    _install_chrome_pf(monkeypatch)
    chromium = _FakeChromium()
    env = _make_env(tmp_path)

    result = actions.action_open_local_browser_probe({
        "url": google_url,
        "_browser_factory": _make_factory(chromium),
        "_clock": _ImmediateClock(),
        "_env": env,
    })

    assert result.success is False
    assert result.error_code == "GOOGLE_OPEN_ONLY"
    assert "google_open_only_use_open_local_browser" in result.data["warnings"]
    assert result.data["error_code"] == "GOOGLE_OPEN_ONLY"
    # action 단에서도 raw URL 이 data 에 echo 되지 않는다.
    assert result.data["target_url"] == ""
    # Playwright 는 호출되지 않았다.
    assert chromium.launch_calls == []


def test_non_google_url_still_passes_after_block_added(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """example.com 은 기존처럼 Playwright launch 가 일어나야 한다 — F-2
    block 이 일반 URL 까지 잡지 않는지 회귀 검증."""
    _install_chrome_pf(monkeypatch)
    page = _FakePage(url="https://example.com/", title="Example")
    ctx = _FakeContext(pages=[page])
    chromium = _FakeChromium(context=ctx)
    env = _make_env(tmp_path)

    result = bp.probe_visible_browser(
        "https://example.com/",
        site_policy=bl.SITE_POLICY_GOOGLE,
        wait_seconds=1,
        _browser_factory=_make_factory(chromium),
        _clock=_ImmediateClock(),
        _env=env,
    )

    assert result["success"] is True
    assert result.get("error_code") in (None, "")
    assert chromium.launch_calls, "non-google URL must still launch"


def test_open_local_browser_action_allows_google_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """F-2: subprocess 기반 ``open_local_browser`` 는 Google URL 을 그대로
    허용해야 한다 (block 은 Playwright probe 쪽에만 적용)."""
    seen: list[dict] = []

    def _fake_open(**kwargs: Any) -> dict:
        seen.append(dict(kwargs))
        return {
            "launched": True,
            "target_url": kwargs.get("url", ""),
            "browser_provider": "chrome",
            "browser_channel": "chrome",
            "browser_path_category": "program_files",
            "profile_dir_category": "haehan_dedicated_named",
            "pid": 1234,
            "warnings": [],
        }

    monkeypatch.setattr(bl, "open_local_browser", _fake_open)

    google_urls = [
        "https://studio.youtube.com/",
        "https://accounts.google.com/",
        "https://drive.google.com/",
        "https://www.youtube.com/",
    ]
    for u in google_urls:
        result = actions.execute_action(
            "open_local_browser",
            {
                "url": u,
                "site_policy": bl.SITE_POLICY_GOOGLE,
                "profile_name": "google_main",
                "provider_override": "chrome",
            },
        )
        assert result.success is True, (u, result.error_code, result.error)
        assert result.data["launched"] is True
        # Google URL 이 launcher 에 그대로 전달됐는지 확인.
        assert seen[-1]["url"] == u
        assert seen[-1]["site_policy"] == bl.SITE_POLICY_GOOGLE
        assert seen[-1]["profile_name"] == "google_main"
        assert seen[-1]["provider_override"] == "chrome"

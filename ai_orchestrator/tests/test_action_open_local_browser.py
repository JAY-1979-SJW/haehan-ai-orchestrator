"""local_agent.actions.action_open_local_browser 검증 (E단계).

- action registry 등록 여부 확인
- browser_launcher.open_local_browser 가 monkeypatch 로 호출되는지 검증
- 입력 검증 (URL / scheme / provider_override)
- 반환 data 에 chrome.exe 절대경로 / 전용 프로필 절대경로가 절대 노출되지
  않는지 확인
- _FORBIDDEN_ENV_VARS 환경변수 존재 시 action 결과 FAIL
- action 실행 경로에서 Playwright import / headless / remote-debugging-port
  사용이 없음을 정적 스캔
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


# ─── helpers ────────────────────────────────────────────────────────────

class _FakeProc:
    def __init__(self, pid: int = 7777) -> None:
        self.pid = pid


def _success_launcher_result(url: str = "https://example.com/") -> dict:
    return {
        "launched": True,
        "target_url": url,
        "browser_provider": "msedge",
        "browser_channel": "msedge",
        "browser_path_category": "program_files_x86",
        "profile_dir_category": "haehan_dedicated",
        "pid": 4242,
        "warnings": [],
    }


# ─── 1. registry 등록 ─────────────────────────────────────────────────────

def test_open_local_browser_action_is_registered() -> None:
    assert "open_local_browser" in actions._ACTIONS
    assert actions._ACTIONS["open_local_browser"] is actions.action_open_local_browser
    # FORBIDDEN_ACTIONS 와 충돌 없음.
    assert "open_local_browser" not in actions.FORBIDDEN_ACTIONS


def test_dispatcher_routes_to_open_local_browser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[dict] = []

    def _fake(**kwargs: Any) -> dict:
        seen.append(dict(kwargs))
        return _success_launcher_result(kwargs.get("url", ""))

    monkeypatch.setattr(bl, "open_local_browser", _fake)

    result = actions.execute_action(
        "open_local_browser",
        {"url": "https://example.com/"},
    )

    assert result.success is True
    assert result.data["launched"] is True
    assert seen and seen[0]["url"] == "https://example.com/"


def test_action_meta_registered_in_registry() -> None:
    """agent/action_registry.py 에 open_local_browser 메타데이터가 있는지."""
    from agent import action_registry as ar

    meta = ar.get_meta("open_local_browser")
    assert meta is not None
    assert meta.category == ar.CATEGORY_LOCAL_BROWSER
    assert meta.risk_level == ar.RISK_MEDIUM
    assert meta.requires_secret is False
    assert meta.requires_browser is True
    assert meta.read_only is True


# ─── 2. browser_launcher 호출 경로 검증 ─────────────────────────────────

def test_action_calls_browser_launcher_with_normalized_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[dict] = []

    def _fake(**kwargs: Any) -> dict:
        seen.append(dict(kwargs))
        return _success_launcher_result(kwargs.get("url", ""))

    monkeypatch.setattr(bl, "open_local_browser", _fake)

    result = actions.action_open_local_browser({
        "url": "https://example.com/",
        "site_policy": "google",
        "profile_name": "haehan_google",
        "provider_override": "chrome",
    })

    assert result.success is True
    assert len(seen) == 1
    call = seen[0]
    assert call["url"] == "https://example.com/"
    assert call["site_policy"] == "google"
    assert call["profile_name"] == "haehan_google"
    assert call["provider_override"] == "chrome"


def test_action_defaults_when_optional_fields_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[dict] = []

    def _fake(**kwargs: Any) -> dict:
        seen.append(dict(kwargs))
        return _success_launcher_result(kwargs.get("url", ""))

    monkeypatch.setattr(bl, "open_local_browser", _fake)

    result = actions.action_open_local_browser({
        "url": "https://example.com/",
    })

    assert result.success is True
    call = seen[0]
    assert call["site_policy"] == bl.SITE_POLICY_AUTO
    assert call["profile_name"] == "default"
    assert call["provider_override"] is None


# ─── 3. 입력 검증 FAIL 케이스 ──────────────────────────────────────────

def test_missing_url_returns_fail() -> None:
    result = actions.action_open_local_browser({})
    assert result.success is False
    assert result.error_code == "MISSING_URL"


def test_blank_url_returns_fail() -> None:
    result = actions.action_open_local_browser({"url": "   "})
    assert result.success is False
    assert result.error_code == "MISSING_URL"


@pytest.mark.parametrize(
    "bad_url",
    [
        "file:///C:/etc/passwd",
        "javascript:alert(1)",
        "data:text/html,<script>",
        "ftp://example.com/x",
        "about:blank",  # http/https 만 허용
    ],
)
def test_non_http_scheme_returns_fail(bad_url: str) -> None:
    result = actions.action_open_local_browser({"url": bad_url})
    assert result.success is False
    assert result.error_code == "URL_SCHEME_NOT_ALLOWED"


@pytest.mark.parametrize(
    "bad_provider",
    ["firefox", "safari", "opera", "", "EDGE", "Chrome"],
)
def test_invalid_provider_override_returns_fail(bad_provider: str) -> None:
    result = actions.action_open_local_browser({
        "url": "https://example.com/",
        "provider_override": bad_provider,
    })
    assert result.success is False
    assert result.error_code == "UNSUPPORTED_PROVIDER"


# ─── 4. 반환 data 에서 절대경로/프로필 경로 노출 없음 ─────────────────

def test_action_result_does_not_expose_chrome_path_or_profile_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    leaked_chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    leaked_profile_path = (
        r"C:\Users\someone\AppData\Local\HaehanAI\BrowserProfiles\chrome\default"
    )

    # 만에 하나 launcher 가 실수로 절대경로를 섞어 보내도 action 단에서
    # 화이트리스트로 제거되어야 한다.
    def _fake(**kwargs: Any) -> dict:
        return {
            "launched": True,
            "target_url": kwargs["url"],
            "browser_provider": "chrome",
            "browser_channel": "chrome",
            "browser_path_category": "program_files",
            "profile_dir_category": "haehan_dedicated",
            "pid": 1234,
            "warnings": [],
            # 가짜 누설 시뮬레이션
            "executable_path": leaked_chrome_path,
            "profile_dir": leaked_profile_path,
        }

    monkeypatch.setattr(bl, "open_local_browser", _fake)

    result = actions.action_open_local_browser({"url": "https://example.com/"})

    assert result.success is True
    blob = repr(result.data) + "|" + result.summary
    assert leaked_chrome_path not in blob
    assert leaked_profile_path not in blob
    assert "chrome.exe" not in blob.lower()
    assert "appdata" not in blob.lower()
    # 카테고리 토큰만 노출.
    assert result.data["browser_path_category"] == "program_files"
    assert result.data["profile_dir_category"] == "haehan_dedicated"


def test_action_result_keys_are_whitelisted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        bl, "open_local_browser",
        lambda **kw: _success_launcher_result(kw["url"]),
    )

    result = actions.action_open_local_browser({"url": "https://example.com/"})

    assert result.success is True
    expected_keys = {
        "launched", "target_url",
        "browser_provider", "browser_channel",
        "browser_path_category", "profile_dir_category",
        "pid", "pid_present", "warnings",
    }
    assert set(result.data.keys()) == expected_keys


# ─── 5. 민감 환경변수 존재 시 action 결과 FAIL ───────────────────────

@pytest.mark.parametrize("forbidden_key", list(bl._FORBIDDEN_ENV_VARS))
def test_forbidden_env_var_makes_action_fail(
    monkeypatch: pytest.MonkeyPatch, forbidden_key: str,
) -> None:
    """browser_launcher 가 환경변수를 보고 launched=False 로 거절하면
    action 도 FAIL 로 변환되어야 한다."""
    # 실제 환경에 영향을 주지 않도록 monkeypatch 로 주입.
    monkeypatch.setenv(forbidden_key, "do-not-leak-this-secret")
    # 다른 forbidden 변수는 비워두기.
    for k in bl._FORBIDDEN_ENV_VARS:
        if k != forbidden_key:
            monkeypatch.delenv(k, raising=False)

    # browser_launcher.open_local_browser 는 실제 함수를 그대로 호출하되
    # spawn / which / candidate 만 deterministic 하게 만든다.
    # 사실 forbidden env 검사는 spawn 도달 전에 끝나므로 fake 가 필요 없다.
    result = actions.action_open_local_browser({
        "url": "https://example.com/",
    })

    assert result.success is False
    assert result.error_code == "BROWSER_LAUNCH_FAILED"
    # 비밀 값은 어떤 필드에도 노출되어선 안 된다.
    blob = repr(result.data) + "|" + result.summary + "|" + result.error
    assert "do-not-leak-this-secret" not in blob
    # warnings 에는 키 이름만 (값 없음) 들어가야 함.
    assert any(
        w == f"forbidden_env_present:{forbidden_key}"
        for w in result.data.get("warnings", [])
    ), result.data.get("warnings")


# ─── 6. 정적 스캔: Playwright / headless / debug-port 사용 없음 ──────

def _read_module_source(mod) -> str:
    return Path(mod.__file__).read_text(encoding="utf-8")


def test_action_module_does_not_import_playwright() -> None:
    """local_agent.actions 자체가 playwright 를 import 하지 않아야 한다."""
    src = _read_module_source(actions)
    assert not re.search(r"^\s*(from|import)\s+playwright", src, re.M), \
        "local_agent.actions must not import playwright"


def test_browser_launcher_module_does_not_import_playwright() -> None:
    src = _read_module_source(bl)
    assert not re.search(r"^\s*(from|import)\s+playwright", src, re.M), \
        "browser_launcher must not import playwright"


def test_browser_launcher_module_has_no_headless_or_debug_port_args() -> None:
    """browser_launcher 의 _build_launch_args 가 만들어내는 인자에는
    --headless / --remote-debugging-port 가 절대 포함되지 않아야 한다."""
    args = bl._build_launch_args(
        exe_path=r"C:\fake\chrome.exe",
        profile_dir=Path(r"C:\fake\profile"),
        url="https://example.com/",
    )
    assert not any(a.startswith("--headless") for a in args)
    assert not any(a.startswith("--remote-debugging-port") for a in args)


def _action_function_node() -> ast.FunctionDef:
    src = _read_module_source(actions)
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and \
                node.name == "action_open_local_browser":
            return node
    raise AssertionError("action_open_local_browser not found")


def test_action_string_literals_have_no_headless_or_debug_port() -> None:
    """action 코드의 **문자열 리터럴** (Constant) 안에 --headless 또는
    --remote-debugging-port 가 들어가지 않는지 검사. docstring 은 첫 번째
    Expr→Constant 위치에 있으므로 본문 시작부의 docstring 만 제외."""
    fn = _action_function_node()
    body = list(fn.body)
    if (
        body and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]  # skip docstring

    offenders: list[tuple[str, int]] = []
    for stmt in body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                v = node.value
                if "--headless" in v or "--remote-debugging-port" in v:
                    offenders.append((v, node.lineno))
    assert offenders == [], \
        f"forbidden CLI flag literals in action body: {offenders}"


def test_action_does_not_call_browser_input_or_storage_apis() -> None:
    """action 함수 본문이 cookies / storage_state / localStorage /
    sessionStorage / fill / click / type / press / keyboard 를 호출/참조
    하지 않는지 AST 로 검사 (docstring/주석은 검사 대상 아님)."""
    fn = _action_function_node()

    forbidden_call_attrs = {
        "fill", "press",
        "cookies", "storage_state", "add_cookies",
        "set_input_files", "evaluate",
        # "click" 은 일반 단어라 호출만, "type" 은 빌트인이라 호출만 검사.
        "click", "type",
    }
    forbidden_attr_usage = {"keyboard"}
    forbidden_names = {"localStorage", "sessionStorage"}

    offenders: list[tuple[str, int]] = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in forbidden_call_attrs:
                offenders.append(
                    (f"call:.{node.func.attr}(", node.lineno)
                )
        if isinstance(node, ast.Attribute) and node.attr in forbidden_attr_usage:
            offenders.append((f"attr:.{node.attr}", node.lineno))
        if isinstance(node, ast.Name) and node.id in forbidden_names:
            offenders.append((f"name:{node.id}", node.lineno))
    assert offenders == [], \
        f"forbidden API patterns in action_open_local_browser: {offenders}"


# ─── 7. launcher 가 거절하면 action 도 거절 ──────────────────────────

def test_launcher_failure_propagates_as_action_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake(**kwargs: Any) -> dict:
        return {
            "launched": False,
            "target_url": kwargs["url"],
            "browser_provider": "",
            "browser_channel": None,
            "browser_path_category": "",
            "profile_dir_category": "",
            "pid": None,
            "warnings": ["no_browser_found"],
        }

    monkeypatch.setattr(bl, "open_local_browser", _fake)

    result = actions.action_open_local_browser({"url": "https://example.com/"})
    assert result.success is False
    assert result.error_code == "BROWSER_LAUNCH_FAILED"
    assert "no_browser_found" in result.error
    assert result.data["launched"] is False
    assert result.data["pid"] is None
    assert result.data["pid_present"] is False

"""local_agent.browser_launcher 검증.

실제 chrome/msedge 실행 금지. 모든 테스트는 ``_candidate_exists``,
``_which_command``, ``spawn`` hook 을 주입해 deterministic 하게 수행한다.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from local_agent import browser_launcher as bl  # noqa: E402


# ─── fixtures / helpers ────────────────────────────────────────────────

class _FakeProc:
    def __init__(self, pid: int = 4242) -> None:
        self.pid = pid


def _make_env(tmp_path: Path, **overrides: str) -> dict:
    """기본 환경변수 세트 — 민감 변수 제거 + 전용 프로필 루트 지정."""
    env = {
        "LOCALAPPDATA": str(tmp_path / "AppData" / "Local"),
        "USERPROFILE": str(tmp_path),
        "PATH": "",
        "HAEHAN_BROWSER_PROFILE_ROOT": str(tmp_path / "BrowserProfiles"),
    }
    # 민감 변수는 명시적으로 제거된 상태를 가정.
    for k in bl._FORBIDDEN_ENV_VARS:
        env.pop(k, None)
    env.update(overrides)
    return env


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")


def _install_candidate_exists(
    monkeypatch: pytest.MonkeyPatch, existing: set[str]
) -> list[str]:
    """``_candidate_exists`` 를 화이트리스트 기반 fake 로 교체."""
    checked: list[str] = []

    def _fake(path: str) -> bool:
        checked.append(path)
        return path in existing

    monkeypatch.setattr(bl, "_candidate_exists", _fake)
    return checked


def _install_which(
    monkeypatch: pytest.MonkeyPatch, mapping: dict[str, str] | None = None
) -> None:
    mapping = mapping or {}

    def _fake_which(cmd: str, env: dict) -> str | None:
        return mapping.get(cmd)

    monkeypatch.setattr(bl, "_which_command", _fake_which)


def _install_no_ms_playwright(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bl, "_iter_ms_playwright_chromium", lambda env: ())


# ─── 1. chrome.exe 경로 탐색 PASS ─────────────────────────────────────

def test_chrome_program_files_is_discovered(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    chrome_pf = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    _install_candidate_exists(monkeypatch, {chrome_pf})
    _install_which(monkeypatch)
    _install_no_ms_playwright(monkeypatch)

    captured: list[list[str]] = []

    def _spawn(args):
        captured.append(list(args))
        return _FakeProc(pid=1001)

    env = _make_env(tmp_path)
    result = bl.open_local_browser(
        "https://studio.youtube.com/",
        site_policy=bl.SITE_POLICY_GOOGLE,
        spawn=_spawn,
        env=env,
    )

    assert result["launched"] is True, result
    assert result["browser_provider"] == "chrome"
    assert result["browser_channel"] == "chrome"
    assert result["browser_path_category"] == "program_files"
    assert result["pid"] == 1001
    assert result["warnings"] == []
    # chrome.exe 전체 경로는 반환값에 노출되지 않아야 한다.
    assert chrome_pf not in str(result)


def test_chrome_env_override_takes_precedence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    custom = tmp_path / "tools" / "chrome.exe"
    _touch(custom)
    pf_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    _install_candidate_exists(monkeypatch, {str(custom), pf_path})
    _install_which(monkeypatch)
    _install_no_ms_playwright(monkeypatch)

    env = _make_env(tmp_path, HAEHAN_CHROME_EXE=str(custom))
    result = bl.open_local_browser(
        "https://studio.youtube.com/",
        site_policy=bl.SITE_POLICY_GOOGLE,
        spawn=lambda args: _FakeProc(pid=1),
        env=env,
    )

    assert result["launched"] is True
    assert result["browser_path_category"] == "env_override"


# ─── 2. 전용 프로필 경로 사용 PASS ────────────────────────────────────

def test_dedicated_profile_is_used_and_not_exposed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    chrome_pf = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    _install_candidate_exists(monkeypatch, {chrome_pf})
    _install_which(monkeypatch)
    _install_no_ms_playwright(monkeypatch)

    captured: list[list[str]] = []

    def _spawn(args):
        captured.append(list(args))
        return _FakeProc()

    env = _make_env(tmp_path)
    result = bl.open_local_browser(
        "https://studio.youtube.com/",
        site_policy=bl.SITE_POLICY_GOOGLE,
        spawn=_spawn,
        env=env,
    )

    assert result["launched"] is True
    assert result["profile_dir_category"] == "haehan_dedicated"

    # 실행 인자에 전용 프로필 루트 내부 경로가 들어가야 함.
    args = captured[0]
    joined = " ".join(args)
    expected_root = str(tmp_path / "BrowserProfiles" / "chrome" / "default")
    assert f"--user-data-dir={expected_root}" in joined
    assert "--profile-directory=Default" in args
    # 기본 사용자 프로필 경로 문자열은 절대 포함 불가.
    assert "google\\chrome\\user data" not in joined.lower().replace("/", "\\")

    # 반환 dict에 절대 경로는 없어야 함 (카테고리만).
    assert expected_root not in str(result)

    # 전용 프로필 디렉터리는 자동 생성되어야 한다.
    assert (tmp_path / "BrowserProfiles" / "chrome" / "default").is_dir()


def test_named_profile_distinguished(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    chrome_pf = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    _install_candidate_exists(monkeypatch, {chrome_pf})
    _install_which(monkeypatch)
    _install_no_ms_playwright(monkeypatch)

    env = _make_env(tmp_path)
    result = bl.open_local_browser(
        "https://studio.youtube.com/",
        profile_name="haehan_google",
        site_policy=bl.SITE_POLICY_GOOGLE,
        spawn=lambda args: _FakeProc(),
        env=env,
    )

    assert result["launched"] is True
    assert result["profile_dir_category"] == "haehan_dedicated_named"


# ─── 3. 기본 Chrome / Edge 프로필 차단 PASS ───────────────────────────

@pytest.mark.parametrize(
    "marker_path",
    [
        r"C:\Users\user\AppData\Local\Google\Chrome\User Data",
        r"C:\Users\user\AppData\Local\Microsoft\Edge\User Data",
    ],
)
def test_default_user_profile_root_is_blocked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, marker_path: str
) -> None:
    chrome_pf = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    _install_candidate_exists(monkeypatch, {chrome_pf})
    _install_which(monkeypatch)
    _install_no_ms_playwright(monkeypatch)

    spawn_called: list[list[str]] = []

    def _spawn(args):  # pragma: no cover — 호출되면 실패.
        spawn_called.append(list(args))
        return _FakeProc()

    env = _make_env(tmp_path, HAEHAN_BROWSER_PROFILE_ROOT=marker_path)
    result = bl.open_local_browser(
        "https://studio.youtube.com/",
        site_policy=bl.SITE_POLICY_GOOGLE,
        spawn=_spawn,
        env=env,
    )

    assert result["launched"] is False
    assert spawn_called == []
    joined = "|".join(result["warnings"])
    assert "default_profile_blocked" in joined


def test_profile_name_with_separator_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    chrome_pf = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    _install_candidate_exists(monkeypatch, {chrome_pf})
    _install_which(monkeypatch)
    _install_no_ms_playwright(monkeypatch)

    env = _make_env(tmp_path)
    for bad in ("foo/bar", "foo\\bar", "..", "../x", "C:/x", "~home"):
        result = bl.open_local_browser(
            "https://studio.youtube.com/",
            profile_name=bad,
            site_policy=bl.SITE_POLICY_GOOGLE,
            spawn=lambda args: _FakeProc(),
            env=env,
        )
        assert result["launched"] is False, bad
        assert any(w.startswith("profile_name_") for w in result["warnings"]), \
            (bad, result["warnings"])


# ─── 4. 민감 환경변수 차단 ──────────────────────────────────────────

@pytest.mark.parametrize("forbidden_key", list(bl._FORBIDDEN_ENV_VARS))
def test_forbidden_env_vars_block_launch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, forbidden_key: str
) -> None:
    chrome_pf = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    _install_candidate_exists(monkeypatch, {chrome_pf})
    _install_which(monkeypatch)
    _install_no_ms_playwright(monkeypatch)

    spawn_called: list[list[str]] = []

    def _spawn(args):  # pragma: no cover — 호출되면 실패.
        spawn_called.append(list(args))
        return _FakeProc()

    env = _make_env(tmp_path)
    env[forbidden_key] = "nonblank-secret-do-not-log"
    result = bl.open_local_browser(
        "https://studio.youtube.com/",
        site_policy=bl.SITE_POLICY_GOOGLE,
        spawn=_spawn,
        env=env,
    )

    assert result["launched"] is False
    assert spawn_called == []
    assert any(
        w == f"forbidden_env_present:{forbidden_key}"
        for w in result["warnings"]
    ), result["warnings"]
    # 실제 값은 어떤 필드에도 절대 노출되지 않아야 한다.
    assert "nonblank-secret-do-not-log" not in str(result)


def test_forbidden_env_var_empty_value_is_not_blocked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    chrome_pf = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    _install_candidate_exists(monkeypatch, {chrome_pf})
    _install_which(monkeypatch)
    _install_no_ms_playwright(monkeypatch)

    env = _make_env(tmp_path)
    env["GOOGLE_PASSWORD"] = ""
    result = bl.open_local_browser(
        "https://studio.youtube.com/",
        site_policy=bl.SITE_POLICY_GOOGLE,
        spawn=lambda args: _FakeProc(),
        env=env,
    )
    assert result["launched"] is True


# ─── 5. cookies / storage_state / 자동입력 관련 호출 없음 (정적 스캔) ─

def test_module_has_no_forbidden_api_calls() -> None:
    """browser_launcher 는 cookies / storage_state / localStorage / 자동
    입력 API 를 **호출하지 않아야** 한다.

    문자열/docstring 안에 언급되는 것은 허용. AST 로 실제 **호출/식별자**
    사용만 검사한다.
    """
    import ast

    src = Path(bl.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)

    forbidden_call_attrs = {
        "click", "fill", "press",
        "cookies", "storage_state", "add_cookies",
        "set_input_files", "evaluate",
        # "type" 은 Python 빌트인 이므로 Call 중 Attribute.attr 매치만 검사.
        "type",
    }
    forbidden_attr_usage = {"keyboard"}
    forbidden_names = {"localStorage", "sessionStorage"}

    offenders: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in forbidden_call_attrs:
                offenders.append((f"call:.{node.func.attr}(", node.lineno))
        if isinstance(node, ast.Attribute) and node.attr in forbidden_attr_usage:
            offenders.append((f"attr:.{node.attr}", node.lineno))
        if isinstance(node, ast.Name) and node.id in forbidden_names:
            offenders.append((f"name:{node.id}", node.lineno))

    assert offenders == [], \
        f"forbidden API patterns in browser_launcher: {offenders}"


def test_module_does_not_import_playwright() -> None:
    src = Path(bl.__file__).read_text(encoding="utf-8")
    # import playwright / from playwright ... 가 등장해서는 안 된다.
    assert not re.search(r"^\s*(from|import)\s+playwright", src, re.M), \
        "browser_launcher must not import playwright"


# ─── 6. 서버 코드에서 신규 런처를 호출하지 않음 / chrome.exe 리터럴 없음 ─

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SERVER_ROOT = _REPO_ROOT / "ai_orchestrator"


def _iter_server_py() -> list[Path]:
    out: list[Path] = []
    for p in _SERVER_ROOT.rglob("*.py"):
        # 테스트 자체는 제외.
        if "tests" in p.parts:
            continue
        out.append(p)
    return out


def test_server_has_no_hardcoded_chrome_or_edge_exe_paths() -> None:
    bad_literals = [
        "chrome.exe",
        "msedge.exe",
        "Google/Chrome/Application",
        "Google\\Chrome\\Application",
        "Microsoft/Edge/Application",
        "Microsoft\\Edge\\Application",
    ]
    offenders: list[tuple[Path, str]] = []
    for py in _iter_server_py():
        text = py.read_text(encoding="utf-8", errors="replace")
        for lit in bad_literals:
            if lit in text:
                offenders.append((py, lit))
    assert offenders == [], f"hardcoded browser paths in server code: {offenders}"


def test_server_code_does_not_import_browser_launcher() -> None:
    offenders: list[Path] = []
    for py in _iter_server_py():
        text = py.read_text(encoding="utf-8", errors="replace")
        if re.search(
            r"^\s*(from\s+local_agent\s+import\s+browser_launcher|"
            r"from\s+local_agent\.browser_launcher\s+import|"
            r"import\s+local_agent\.browser_launcher)\b",
            text,
            re.M,
        ):
            offenders.append(py)
    assert offenders == [], \
        f"server code must not import browser_launcher: {offenders}"


# ─── 7. 실행 인자 / 금지 플래그 / provider 우선순위 ─────────────────

def test_launch_args_contain_no_headless_or_debug_port(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    chrome_pf = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    _install_candidate_exists(monkeypatch, {chrome_pf})
    _install_which(monkeypatch)
    _install_no_ms_playwright(monkeypatch)

    captured: list[list[str]] = []
    def _spawn(args):
        captured.append(list(args))
        return _FakeProc()

    env = _make_env(tmp_path)
    result = bl.open_local_browser(
        "https://studio.youtube.com/",
        site_policy=bl.SITE_POLICY_GOOGLE,
        spawn=_spawn, env=env,
    )
    assert result["launched"] is True
    args = captured[0]
    assert not any(a.startswith("--headless") for a in args)
    assert not any(a.startswith("--remote-debugging-port") for a in args)
    assert "--no-first-run" in args
    assert "--no-default-browser-check" in args
    # target URL 은 마지막 인자.
    assert args[-1] == "https://studio.youtube.com/"


def test_auto_policy_prefers_msedge_over_chrome(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    edge_pf_x86 = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    chrome_pf = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    _install_candidate_exists(monkeypatch, {edge_pf_x86, chrome_pf})
    _install_which(monkeypatch)
    _install_no_ms_playwright(monkeypatch)

    env = _make_env(tmp_path)
    result = bl.open_local_browser(
        "https://example.gov.kr/",
        site_policy=bl.SITE_POLICY_AUTO,
        spawn=lambda args: _FakeProc(),
        env=env,
    )
    assert result["launched"] is True
    assert result["browser_provider"] == "msedge"
    assert result["browser_path_category"] == "program_files_x86"


def test_google_policy_prefers_chrome_over_msedge(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    edge_pf_x86 = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    chrome_pf = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    _install_candidate_exists(monkeypatch, {edge_pf_x86, chrome_pf})
    _install_which(monkeypatch)
    _install_no_ms_playwright(monkeypatch)

    env = _make_env(tmp_path)
    result = bl.open_local_browser(
        "https://studio.youtube.com/",
        site_policy=bl.SITE_POLICY_GOOGLE,
        spawn=lambda args: _FakeProc(),
        env=env,
    )
    assert result["launched"] is True
    assert result["browser_provider"] == "chrome"


def test_no_browser_found_returns_fail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_candidate_exists(monkeypatch, set())
    _install_which(monkeypatch)
    _install_no_ms_playwright(monkeypatch)

    env = _make_env(tmp_path)
    result = bl.open_local_browser(
        "https://studio.youtube.com/",
        site_policy=bl.SITE_POLICY_GOOGLE,
        spawn=lambda args: _FakeProc(),
        env=env,
    )
    assert result["launched"] is False
    assert "no_browser_found" in result["warnings"]


def test_invalid_url_scheme_is_rejected(tmp_path: Path) -> None:
    env = _make_env(tmp_path)
    result = bl.open_local_browser(
        "file:///C:/etc/passwd",
        spawn=lambda args: _FakeProc(),
        env=env,
    )
    assert result["launched"] is False
    assert "target_url_scheme_forbidden" in result["warnings"]


def test_empty_url_is_rejected(tmp_path: Path) -> None:
    env = _make_env(tmp_path)
    result = bl.open_local_browser(
        "",
        spawn=lambda args: _FakeProc(),
        env=env,
    )
    assert result["launched"] is False
    assert "invalid_target_url" in result["warnings"]


def test_unsupported_provider_override_returns_fail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_candidate_exists(monkeypatch, set())
    _install_which(monkeypatch)
    _install_no_ms_playwright(monkeypatch)

    env = _make_env(tmp_path)
    result = bl.open_local_browser(
        "https://example.com/",
        provider_override="firefox",
        spawn=lambda args: _FakeProc(),
        env=env,
    )
    assert result["launched"] is False
    assert any(w.startswith("unsupported_provider:") for w in result["warnings"])

"""ORCHESTRATOR_BROWSER_GUARD_NAVIGATE_AND_CLEAN_START_FIX_01 — 라이브 결함 보수 검증.

L1: Chrome 자식 프로세스(--type=...) 카운트 제외
L2: navigate raw URL(about:/http:/...) 지원
L3: browser_start 후 stale 탭 정리 계획
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.agent_runtime.browser import browser_action_executor as bx
from core.agent_runtime.browser import browser_instance_guard as guard


@pytest.fixture()
def paths(tmp_path: Path) -> guard.GuardPaths:
    profile = tmp_path / "ai_chrome"
    profile.mkdir()
    return guard.resolve_paths(profile_dir=profile, state_dir=tmp_path / "rt", cdp_port=9222)


@pytest.fixture(autouse=True)
def _reset_probes():
    guard.set_cdp_probe(lambda _p: False)
    yield
    guard.set_cdp_probe(None)
    guard.reset_process_enumerator()


def _parent_cmd(profile: Path, port: int = 9222) -> str:
    return f"chrome.exe --user-data-dir={profile} --remote-debugging-port={port}"


def _child_cmd(profile: Path, child_type: str, port: int = 9222) -> str:
    return (
        f"chrome.exe --user-data-dir={profile} --remote-debugging-port={port} "
        f"--type={child_type} --field-trial-handle=..."
    )


# ── L1: Chrome 자식 프로세스 제외 ─────────────────────────────────────


def test_l1_child_processes_excluded_from_count(paths):
    """parent 1개 + child 11개 → automation count = 1."""
    procs = [
        (100, _parent_cmd(paths.profile_dir)),
        (101, _child_cmd(paths.profile_dir, "renderer")),
        (102, _child_cmd(paths.profile_dir, "renderer")),
        (103, _child_cmd(paths.profile_dir, "renderer")),
        (104, _child_cmd(paths.profile_dir, "gpu-process")),
        (105, _child_cmd(paths.profile_dir, "utility")),
        (106, _child_cmd(paths.profile_dir, "utility")),
        (107, _child_cmd(paths.profile_dir, "zygote")),
        (108, _child_cmd(paths.profile_dir, "crashpad-handler")),
        (109, _child_cmd(paths.profile_dir, "renderer")),
        (110, _child_cmd(paths.profile_dir, "renderer")),
        (111, _child_cmd(paths.profile_dir, "renderer")),
    ]
    guard.set_process_enumerator(lambda: procs)
    full, _partial, pids = guard.count_automation_browsers(paths)
    assert full == 1
    assert pids == [100]


def test_l1_decide_attach_existing_when_parent_only(paths):
    procs = [
        (100, _parent_cmd(paths.profile_dir)),
        (101, _child_cmd(paths.profile_dir, "renderer")),
        (102, _child_cmd(paths.profile_dir, "gpu-process")),
    ]
    guard.set_process_enumerator(lambda: procs)
    d = guard.decide_browser_start(paths)
    assert d.action == guard.ACTION_ATTACH_EXISTING
    assert d.count == 1


def test_l1_user_chrome_with_type_still_not_counted(paths):
    """사용자의 일반 Chrome 일부 (예: 별도 인스턴스의 renderer) — 매치되지도 않지만,
    혹시 매치되더라도 --type 으로 제외됨."""
    procs = [
        (50, "chrome.exe --user-data-dir=C:/Users/me/Chrome/Default"),  # 일반
    ]
    guard.set_process_enumerator(lambda: procs)
    full, _, _ = guard.count_automation_browsers(paths)
    assert full == 0


def test_l1_helper_is_chrome_child_process():
    assert guard._is_chrome_child_process("chrome.exe --type=renderer") is True
    assert guard._is_chrome_child_process("chrome.exe --type=gpu-process") is True
    assert guard._is_chrome_child_process("chrome.exe --user-data-dir=...") is False


# ── L2: navigate raw URL 지원 ─────────────────────────────────────────


def test_l2_is_raw_url_detects_supported_schemes():
    for url in (
        "about:blank",
        "http://example.com",
        "https://example.com/path",
        "data:text/html,<h1>x</h1>",
        "file:///C:/tmp/index.html",
    ):
        assert bx._is_raw_url(url) is True, url


def test_l2_alias_not_treated_as_raw_url():
    for alias in ("gmail", "google", "blog"):
        assert bx._is_raw_url(alias) is False


def test_l2_navigate_with_raw_url_uses_page_goto(monkeypatch):
    """ACT_NAVIGATE 의 default_runner 가 raw URL 분기에서 scripts.browser.cdp.connection.get_page
    를 호출하고, page.goto 결과를 ok=True 로 반환한다."""
    goto_calls: list[str] = []

    class _FakePage:
        def goto(self, url, timeout=None):
            goto_calls.append(url)

    from scripts.browser.cdp import connection

    monkeypatch.setattr(connection, "get_page", lambda: _FakePage())

    out = bx.default_runner(bx.ACT_NAVIGATE, {"url": "about:blank"})
    assert out["ok"] is True
    assert goto_calls == ["about:blank"]


def test_l2_navigate_with_alias_still_uses_navigator(monkeypatch):
    """raw URL 이 아니면 기존 navigator.goto(alias resolver) 경로 유지."""
    calls: list[str] = []
    import types

    fake_nav = types.SimpleNamespace(
        goto=lambda url, timeout_ms=60000: calls.append(url),
    )
    monkeypatch.setitem(__import__("sys").modules, "scripts.browser.navigator.navigator", fake_nav)

    out = bx.default_runner(bx.ACT_NAVIGATE, {"url": "gmail"})
    assert out["ok"] is True
    assert calls == ["gmail"]


# ── L3: stale tab cleanup 계획 ────────────────────────────────────────


def test_l3_quit_closes_all_targets_first(monkeypatch, paths):
    """browser_quit 가 CDP /json/close 로 모든 page target 을 닫고 그 다음
    Chrome 프로세스를 종료해야 한다 (세션 복원 방지)."""
    from core.agent_runtime.browser import browser_instance_guard as g

    monkeypatch.setattr(g, "close_all_cdp_targets", lambda port: ["T-1", "T-2", "T-3"])
    g.set_process_enumerator(lambda: [])  # 프로세스 없는 상태
    result = g.quit_automation_browsers(
        paths,  # 실제 상태 디렉터리(pid/lock/snapshot 삭제) 대신 tmp 경로
        kill_fn=lambda pid: True,
    )
    assert result["closed_targets"] == ["T-1", "T-2", "T-3"]


def test_l3_quit_close_targets_first_can_be_disabled(monkeypatch, paths):
    from core.agent_runtime.browser import browser_instance_guard as g

    called = []

    def fake_close(port):
        called.append(port)
        return []

    monkeypatch.setattr(g, "close_all_cdp_targets", fake_close)
    g.set_process_enumerator(lambda: [])
    g.quit_automation_browsers(
        paths,  # 실제 상태 디렉터리(pid/lock/snapshot 삭제) 대신 tmp 경로
        kill_fn=lambda pid: True,
        close_targets_first=False,
    )
    assert called == []


# ── L3 wiring: browser_start 응답에 stale_tabs_* 키 포함 확인 ─────────

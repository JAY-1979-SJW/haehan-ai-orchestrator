"""ORCHESTRATOR_BROWSER_FIXED_PROFILE_AND_INSTANCE_GUARD_01 — 필수 13종 테스트.

실제 Chrome/CDP 를 실행하지 않는다. 프로세스 enumerator 와 CDP probe 는
주입(injection) 으로 시뮬레이션한다.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.agent_runtime.browser import browser_instance_guard as guard
from core.agent_runtime.browser import browser_session_store as bss


@pytest.fixture()
def paths(tmp_path: Path) -> guard.GuardPaths:
    profile = tmp_path / "automation-chrome-profile"
    profile.mkdir()
    state = tmp_path / "runtime" / "browser"
    return guard.resolve_paths(profile_dir=profile, state_dir=state, cdp_port=9222)


@pytest.fixture(autouse=True)
def _reset_probes():
    guard.set_cdp_probe(lambda _port: False)
    yield
    guard.set_cdp_probe(None)
    guard.reset_process_enumerator()


def _cmd_for(profile: Path, port: int = 9222) -> str:
    return (
        f"chrome.exe --user-data-dir={profile} "
        f"--remote-debugging-port={port} --no-first-run"
    )


# 1. 고정 profile dir 식별 — cmdline 매칭

def test_identification_requires_both_profile_and_port(paths):
    user_chrome = "chrome.exe --user-data-dir=C:/Users/me/Chrome/Default"
    auto_chrome = _cmd_for(paths.profile_dir)
    partial = f"chrome.exe --user-data-dir={paths.profile_dir}"  # port 없음

    guard.set_process_enumerator(lambda: [(100, user_chrome), (200, auto_chrome), (300, partial)])
    procs = guard.list_automation_chrome_processes(paths)
    pids = {p.pid for p in procs if p.is_automation}
    partials = {p.pid for p in procs if p.is_orphan_partial}
    assert pids == {200}
    assert partials == {300}


# 2. count=0 → start_new

def test_decide_start_new_when_count_zero(paths):
    guard.set_process_enumerator(lambda: [])
    d = guard.decide_browser_start(paths)
    assert d.action == guard.ACTION_START_NEW
    assert d.count == 0


# 3. count=1 → attach

def test_decide_attach_when_count_one(paths):
    guard.set_process_enumerator(lambda: [(200, _cmd_for(paths.profile_dir))])
    d = guard.decide_browser_start(paths)
    assert d.action == guard.ACTION_ATTACH_EXISTING
    assert d.count == 1
    assert d.matched_pids == [200]


# 4. count>=2 → MULTIPLE_AUTOMATION_BROWSERS

def test_decide_error_when_multiple(paths):
    cmd = _cmd_for(paths.profile_dir)
    guard.set_process_enumerator(lambda: [(201, cmd), (202, cmd)])
    d = guard.decide_browser_start(paths)
    assert d.action == guard.ACTION_ERROR_MULTIPLE
    assert d.error == guard.ERROR_MULTIPLE_BROWSERS
    assert d.count == 2


# 5. stale pid 정리

def test_stale_pid_cleaned(paths):
    guard.write_pid_file(paths, 999999)  # 살아있을 가능성 거의 없는 pid
    # 만일 살아있다면 환경 의존 — 그 경우 건너뛴다
    if guard._pid_alive(999999):
        pytest.skip("pid 999999 actually alive in this environment")
    pid_before, cleaned = guard.cleanup_stale_pid(paths)
    assert pid_before == 999999
    assert cleaned is True
    assert not paths.pid_file.exists()


# 6. 살아있는 pid 는 재사용

def test_live_pid_kept(paths):
    pid = os.getpid()
    guard.write_pid_file(paths, pid)
    pid_in_file, cleaned = guard.cleanup_stale_pid(paths)
    assert pid_in_file == pid
    assert cleaned is False
    assert paths.pid_file.exists()


# 7. CDP /json/list 살아있으면 start_new 대신 attach_orphan_cdp 또는 attach_existing

def test_cdp_alive_prevents_start_new(paths):
    guard.set_process_enumerator(lambda: [])
    guard.set_cdp_probe(lambda _port: True)
    d = guard.decide_browser_start(paths)
    assert d.action == guard.ACTION_ATTACH_ORPHAN_CDP
    assert d.cdp_alive is True


# 8. browser_quit 은 자동화 Chrome 만 종료

def test_quit_only_kills_automation_browsers(paths, monkeypatch):
    # 실제 CDP(/json/list·/json/close) 접속으로 사용자 Chrome 탭을 닫지 않도록 가짜로 대체
    close_calls: list[int] = []
    monkeypatch.setattr(guard, "close_all_cdp_targets", lambda port: close_calls.append(port) or [])
    user_chrome = "chrome.exe --user-data-dir=C:/Users/me/Chrome/Default"
    auto_chrome = _cmd_for(paths.profile_dir)
    guard.set_process_enumerator(lambda: [(100, user_chrome), (200, auto_chrome)])
    killed_call_args: list[int] = []

    def _fake_kill(pid: int) -> bool:
        killed_call_args.append(pid)
        return True

    result = guard.quit_automation_browsers(paths, kill_fn=_fake_kill)
    assert killed_call_args == [200]  # user_chrome (pid 100) 은 미포함
    assert result["killed_pids"] == [200]
    assert result["ok"] is True
    assert close_calls == [9222]  # 가짜 호출만 일어남(실제 CDP 접속 없음)


# 9. 일반 Chrome 은 count/quit 대상 제외 — list 에서 분리

def test_user_chrome_excluded_from_count(paths):
    user_chromes = [
        (101, "chrome.exe --user-data-dir=C:/Users/me/Chrome/Default"),
        (102, "chrome.exe"),
        (103, "chrome.exe --remote-debugging-port=9333"),  # 다른 포트
    ]
    auto_chrome = (200, _cmd_for(paths.profile_dir))
    guard.set_process_enumerator(lambda: user_chromes + [auto_chrome])

    full, partial, pids = guard.count_automation_browsers(paths)
    assert full == 1
    assert pids == [200]
    # 다른 포트 user-chrome 은 partial 도 아님
    assert partial == 0


# 10. tab_list 는 CDP target_id 를 그대로 사용 (session_store target 등록)

def test_session_store_tab_id_matches_cdp_target():
    store = bss.BrowserSessionStore()
    store.start_session()
    store.upsert_tab("T-aabbcc", url="https://example.com", title="ex")
    tabs = store.list_tabs()
    assert len(tabs) == 1
    assert tabs[0].tab_id == "T-aabbcc"
    assert tabs[0].status == bss.TAB_OPEN


# 11. tab_close 는 해당 target 만 닫고 나머지 유지

def test_tab_close_isolates_to_target():
    store = bss.BrowserSessionStore()
    store.start_session()
    store.upsert_tab("T-1", url="https://a")
    store.upsert_tab("T-2", url="https://b")
    closed = store.mark_tab_closed("T-1")
    assert closed is not None and closed.status == bss.TAB_CLOSED
    living = store.list_tabs()
    living_ids = {t.tab_id for t in living}
    assert living_ids == {"T-2"}
    # closed 탭은 include_closed=True 일 때만 보임
    all_tabs = store.list_tabs(include_closed=True)
    assert {t.tab_id for t in all_tabs} == {"T-1", "T-2"}


# 12. target diff 로 popup/new window 감지

def test_diff_targets_detects_added_and_removed():
    store = bss.BrowserSessionStore()
    store.start_session()
    store.upsert_tab("T-1")
    store.upsert_tab("T-2")
    diff = store.diff_targets(["T-2", "T-3"])
    assert diff["added"] == ["T-3"]
    assert diff["removed"] == ["T-1"]


# 13. lock 살아있으면 새 Chrome 실행 차단

def test_active_lock_blocks_start(paths):
    guard.set_process_enumerator(lambda: [])
    guard.write_lock_file(paths, os.getpid())  # 현재 프로세스 = 살아있음
    d = guard.decide_browser_start(paths)
    assert d.action == guard.ACTION_BLOCKED_BY_LOCK
    assert d.lock_active is True


# 추가: stale lock 자동 정리

def test_stale_lock_cleared(paths):
    guard.set_process_enumerator(lambda: [])
    guard.write_lock_file(paths, 999999)
    if guard._pid_alive(999999):
        pytest.skip("pid 999999 alive in this env")
    assert guard.is_lock_active(paths) is False
    assert not paths.lock_file.exists()


# 추가(T4 R11): try_acquire_lock — 원자적 획득, 두 번째 시도는 실패

def test_try_acquire_lock_succeeds_once(paths):
    assert guard.try_acquire_lock(paths, os.getpid()) is True
    assert guard.is_lock_active(paths) is True
    assert guard.try_acquire_lock(paths, os.getpid()) is False


def test_try_acquire_lock_after_stale_lock_cleared(paths):
    guard.write_lock_file(paths, 999999)
    if guard._pid_alive(999999):
        pytest.skip("pid 999999 alive in this env")
    assert guard.try_acquire_lock(paths, os.getpid()) is True
    assert guard.is_lock_active(paths) is True


def test_write_lock_file_leaves_no_tmp_leftover(paths):
    guard.write_lock_file(paths, os.getpid())
    leftover_tmp = list(paths.lock_file.parent.glob(f"{paths.lock_file.name}.tmp.*"))
    assert leftover_tmp == []  # replace()로 바로 치워짐
    assert paths.lock_file.exists()


# 추가: 닫힌 탭에 명령이 도달하면 store 가 TAB_CLOSED 응답을 유지하고
#       새 탭을 만들지 않는다 (호출자 책임).

def test_closed_tab_state_persists():
    store = bss.BrowserSessionStore()
    store.start_session()
    store.upsert_tab("T-1")
    store.mark_tab_closed("T-1")
    rec = store.get_tab("T-1")
    assert rec is not None
    assert rec.status == bss.TAB_CLOSED

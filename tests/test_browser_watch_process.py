"""브라우저 프로세스 감시 — 출현·소멸 기록과 소멸 직전 프로세스 목록(이름·스크립트 파일명만). 2026-10-05: 검증 중 9222 Chrome 이 사라졌으나 원인 기록이 없었다."""

from __future__ import annotations

from scripts.ops import browser_watch as bw

PORT = 9222
NOW = 1_000_000.0


def _proc(pid, name="python.exe", cmd=None, age=5, ppid=1):
    return {"pid": pid, "ppid": ppid, "name": name, "cmdline": cmd or [name], "create_time": NOW - age}


def test_script_name_keeps_only_file_name_never_arguments():
    cmd = ["python.exe", "-u", "scripts/cdp_daemon.py", "--token=SECRET123", "run"]
    assert bw.script_name(cmd) == "cdp_daemon.py"
    assert bw.script_name(["chrome.exe", "--flag=1"]) == ""
    assert "SECRET" not in str(bw.recent_processes([_proc(7, cmd=cmd)], NOW))


def test_is_browser_main_excludes_children_and_other_ports():
    main = ["chrome.exe", f"--remote-debugging-port={PORT}", "--user-data-dir=x"]
    assert bw.is_browser_main(main, PORT)
    assert not bw.is_browser_main([*main, "--type=renderer"], PORT)
    assert not bw.is_browser_main(["chrome.exe", "--remote-debugging-port=9333"], PORT)
    assert not bw.is_browser_main(["chrome.exe"], PORT)


def test_recent_processes_filters_window_children_and_sorts_newest_first():
    procs = [
        _proc(1, age=10),
        _proc(2, age=200),  # 창 밖
        _proc(3, name="conhost.exe", age=1),  # 제외
        _proc(4, name="chrome.exe", cmd=["chrome.exe", "--type=gpu-process"], age=2),  # 브라우저 자식 제외
        _proc(5, age=3),
        _proc(6, age=-5),  # 미래(시계 어긋남) 제외
    ]
    assert [r["pid"] for r in bw.recent_processes(procs, NOW)] == [5, 1]
    assert len(bw.recent_processes([_proc(i, age=1) for i in range(100)], NOW)) == bw.RECENT_MAX


def test_process_state_records_appear_vanish_and_reappear_with_parent():
    st = bw.ProcessState()
    parent = _proc(50, cmd=["pythonw.exe", "cdp_daemon.py", "_run"], ppid=1)
    main = {"pid": 100, "ppid": 50}
    first = st.observe(main, [parent], NOW)
    assert first == [
        {
            "event": "browser_process",
            "state": "appeared",
            "pid": 100,
            "initial": True,
            "parent": {"pid": 50, "name": "python.exe", "script": "cdp_daemon.py"},
        }
    ]
    assert st.observe(main, [parent], NOW + 1) == []  # 변화 없음
    killer = _proc(60, name="taskkill.exe", age=2)
    gone = st.observe(None, [parent, killer], NOW + 2)
    assert len(gone) == 1 and gone[0]["state"] == "vanished" and gone[0]["pid"] == 100
    assert [r["name"] for r in gone[0]["recent_processes"]] == [
        "taskkill.exe",
        "python.exe",
    ]  # 소멸 직전 시작된 프로세스가 원인 후보로 남는다
    assert st.observe(None, [parent], NOW + 3) == []  # 계속 없음 — 반복 기록 없음
    back = st.observe({"pid": 200, "ppid": 50}, [parent], NOW + 4)
    assert back[0]["state"] == "appeared" and back[0]["pid"] == 200 and back[0]["initial"] is False


def test_process_state_first_observation_without_browser_logs_nothing():
    assert bw.ProcessState().observe(None, [], NOW) == []


def test_poll_process_swallows_errors(monkeypatch, tmp_path):
    def boom():
        raise RuntimeError("psutil 실패")

    monkeypatch.setattr(bw, "_snapshot_processes", boom)
    monkeypatch.setattr(bw, "_find_browser_main", lambda _port: {"pid": 100, "ppid": 50})
    bw.poll_process(
        bw.ProcessState(), PORT, bw.RotatingLog(tmp_path / "w.jsonl"), NOW
    )  # 예외가 감시 루프를 죽이지 않는다
    assert not (tmp_path / "w.jsonl").exists()


def test_poll_process_writes_jsonl_for_a_found_browser(monkeypatch, tmp_path):
    procs = [_proc(100, name="chrome.exe", cmd=["chrome.exe", f"--remote-debugging-port={PORT}"], ppid=50), _proc(50)]
    monkeypatch.setattr(bw, "_snapshot_processes", lambda: procs)
    monkeypatch.setattr(bw, "_find_browser_main", lambda _port: {"pid": 100, "ppid": 50})
    log = bw.RotatingLog(tmp_path / "w.jsonl")
    bw.poll_process(bw.ProcessState(), PORT, log, NOW)
    text = (tmp_path / "w.jsonl").read_text(encoding="utf-8")
    assert '"state": "appeared"' in text and '"pid": 100' in text


def test_poll_skips_the_heavy_snapshot_while_nothing_changes(monkeypatch, tmp_path):
    """평소 점검은 가벼워야 한다 — 전체 스냅샷(실측 3초)은 출현·소멸 때만 찍는다."""
    calls = []
    monkeypatch.setattr(bw, "_snapshot_processes", lambda: calls.append(1) or [_proc(50)])
    monkeypatch.setattr(bw, "_find_browser_main", lambda _port: {"pid": 100, "ppid": 50})
    st, log = bw.ProcessState(), bw.RotatingLog(tmp_path / "w.jsonl")
    for i in range(5):
        bw.poll_process(st, PORT, log, NOW + i)
    assert len(calls) == 1  # 처음 한 번만
    monkeypatch.setattr(bw, "_find_browser_main", lambda _port: None)
    bw.poll_process(st, PORT, log, NOW + 6)
    assert len(calls) == 2  # 사라질 때 한 번 더


def test_find_browser_main_reads_command_line_only_for_chrome(monkeypatch):
    import psutil

    class FakeProc:
        def __init__(self, pid, name, cmd, ppid=1):
            self.info, self._cmd, self._ppid = {"pid": pid, "name": name}, cmd, ppid

        def cmdline(self):
            if self.info["name"] != "chrome.exe":
                raise AssertionError("chrome 이 아닌 프로세스의 명령줄을 읽었다")
            return self._cmd

        def ppid(self):
            return self._ppid

    fakes = [
        FakeProc(1, "python.exe", []),
        FakeProc(2, "chrome.exe", ["chrome.exe", "--type=gpu-process"]),
        FakeProc(3, "chrome.exe", ["chrome.exe", f"--remote-debugging-port={PORT}"], ppid=9),
    ]
    monkeypatch.setattr(psutil, "process_iter", lambda _attrs=None: iter(fakes))
    assert bw._find_browser_main(PORT) == {"pid": 3, "ppid": 9}

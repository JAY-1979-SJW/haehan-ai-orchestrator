"""scripts/browser/cdp/browser_watch.py — 탭 생성·이동·종료 감시 로그 시험."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import websocket

from scripts.browser.cdp import browser_watch as bw

ROOT = Path(__file__).resolve().parents[2]


def _created(tid, url="about:blank", ttype="page", title="", opener=None):
    info = {"targetId": tid, "type": ttype, "url": url, "title": title}
    if opener:
        info["openerId"] = opener
    return {"method": "Target.targetCreated", "params": {"targetInfo": info}}


def _changed(tid, url, title="", ttype="page"):
    info = {"targetId": tid, "type": ttype, "url": url, "title": title}
    return {"method": "Target.targetInfoChanged", "params": {"targetInfo": info}}


def _destroyed(tid):
    return {"method": "Target.targetDestroyed", "params": {"targetId": tid}}


def test_mask_url_hides_query_values_and_fragment():
    masked = bw.mask_url("https://a.com/p/q?token=SECRET&code=123#frag")
    assert masked == "https://a.com/p/q?token=***&code=***"
    assert "SECRET" not in masked and "123" not in masked and "frag" not in masked


def test_mask_url_without_query_is_unchanged_path():
    assert bw.mask_url("https://a.com/x/y") == "https://a.com/x/y"


def test_mask_url_truncates_to_300_chars():
    assert len(bw.mask_url("https://a.com/" + "p" * 500)) <= 300


def test_open_navigate_close_are_recorded():
    st = bw.WatchState()
    opened = st.handle(_created("T1", "about:blank", opener="T0"), 0)
    assert [r["event"] for r in opened] == ["opened"]
    assert opened[0]["opener_id"] == "T0" and opened[0]["target_id"] == "T1"
    nav = st.handle(_changed("T1", "https://example.com/?k=v", "Example"), 1)
    assert nav[0]["event"] == "navigated" and nav[0]["url"] == "https://example.com/?k=***"
    assert st.handle(_destroyed("T1"), 2) == [{"event": "closed", "target_id": "T1"}]


def test_title_only_change_is_not_recorded():
    st = bw.WatchState()
    st.handle(_created("T1", "https://a.com/"), 0)
    assert st.handle(_changed("T1", "https://a.com/", "새 제목"), 1) == []


def test_non_page_targets_are_ignored():
    st = bw.WatchState()
    assert st.handle(_created("F1", "https://a.com/", ttype="iframe"), 0) == []
    assert st.handle(_created("W1", "https://a.com/sw.js", ttype="service_worker"), 0) == []
    assert st.handle(_destroyed("F1"), 1) == []  # 기록한 적 없는 대상의 종료는 무시


def test_unrelated_methods_are_ignored():
    assert bw.WatchState().handle({"id": 1, "result": {}}, 0) == []


def test_many_tabs_alert_fires_once_and_rearms_after_drop():
    st = bw.WatchState()
    events = []
    for i in range(bw.MAX_TABS + 2):
        events += st.handle(_created(f"T{i}", f"https://s{i}.com/"), i)
    alerts = [e for e in events if e.get("kind") == "many_tabs"]
    assert len(alerts) == 1 and alerts[0]["tabs"] == bw.MAX_TABS + 1
    for i in range(bw.MAX_TABS + 2):
        st.handle(_destroyed(f"T{i}"), 50)
    again = []
    for i in range(bw.MAX_TABS + 1):
        again += st.handle(_created(f"U{i}", f"https://u{i}.com/"), 60 + i)
    assert len([e for e in again if e.get("kind") == "many_tabs"]) == 1


def test_exactly_max_tabs_is_not_anomaly():
    st = bw.WatchState()
    events = []
    for i in range(bw.MAX_TABS):
        events += st.handle(_created(f"T{i}", f"https://s{i}.com/"), i)
    assert not [e for e in events if e["event"] == "anomaly"]


def _chain(st, hosts, start=0.0, step=1.0):
    st.handle(_created("T1", "about:blank"), start)
    out = []
    for i, host in enumerate(hosts):
        out += st.handle(_changed("T1", f"https://{host}/"), start + step * (i + 1))
    return out


def test_chain_navigation_alert_when_enough_domains_within_window():
    hosts = [f"site{i}.com" for i in range(bw.CHAIN_MIN_DOMAINS)]
    out = _chain(bw.WatchState(), hosts)
    alerts = [e for e in out if e.get("kind") == "chain_navigation"]
    assert len(alerts) == 1 and alerts[0]["domains"] == sorted(hosts)


def test_chain_below_threshold_is_not_alert():
    out = _chain(bw.WatchState(), [f"site{i}.com" for i in range(bw.CHAIN_MIN_DOMAINS - 1)])
    assert not [e for e in out if e["event"] == "anomaly"]


def test_same_domain_repeats_do_not_count_as_chain():
    hosts = ["a.com/x", "a.com/y", "a.com/z", "a.com/w", "a.com/v", "a.com/u"]
    st = bw.WatchState()
    st.handle(_created("T1", "about:blank"), 0)
    out = []
    for i, path in enumerate(hosts):
        out += st.handle(_changed("T1", f"https://{path}"), i + 1)
    assert not [e for e in out if e["event"] == "anomaly"]


def test_chain_outside_window_is_not_alert():
    step = bw.CHAIN_WINDOW_SEC / 2 + 1  # 도메인은 충분하지만 창(60초) 안에 5개가 모이지 않음
    out = _chain(bw.WatchState(), [f"site{i}.com" for i in range(bw.CHAIN_MIN_DOMAINS)], step=step)
    assert not [e for e in out if e["event"] == "anomaly"]


def test_chain_alert_has_cooldown_then_rearms():
    st = bw.WatchState()
    hosts = [f"site{i}.com" for i in range(bw.CHAIN_MIN_DOMAINS)]
    _chain(st, hosts)
    extra = st.handle(_changed("T1", "https://extra1.com/"), 6)
    assert not [e for e in extra if e["event"] == "anomaly"]  # 쿨다운 안: 재경고 없음
    later = 6 + bw.CHAIN_WINDOW_SEC + 1
    out = []
    for i in range(bw.CHAIN_MIN_DOMAINS):
        out += st.handle(_changed("T1", f"https://again{i}.com/"), later + i)
    assert [e for e in out if e.get("kind") == "chain_navigation"]


def test_chain_state_is_per_tab():
    st = bw.WatchState()
    st.handle(_created("A", "about:blank"), 0)
    st.handle(_created("B", "about:blank"), 0)
    out = []
    for i in range(bw.CHAIN_MIN_DOMAINS):  # 탭마다 절반씩 → 어느 탭도 임계 미달
        tid = "A" if i % 2 == 0 else "B"
        out += st.handle(_changed(tid, f"https://s{i}.com/"), i + 1)
    assert not [e for e in out if e["event"] == "anomaly"]


def test_rotating_log_rotates_and_keeps_one_generation(tmp_path):
    log = bw.RotatingLog(tmp_path / "w.jsonl", max_bytes=200)
    for i in range(40):
        log.write({"event": "opened", "n": i, "pad": "x" * 30})
    assert (tmp_path / "w.jsonl.1").exists()
    assert not (tmp_path / "w.jsonl.2").exists()
    assert (tmp_path / "w.jsonl").stat().st_size < 400
    row = json.loads((tmp_path / "w.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert "ts" in row and row["event"] == "opened"


def test_rotating_log_writes_korean_as_is(tmp_path):
    log = bw.RotatingLog(tmp_path / "k.jsonl")
    log.write({"event": "opened", "title": "네이버 블로그"})
    assert "네이버 블로그" in (tmp_path / "k.jsonl").read_text(encoding="utf-8")


class _FakeWS:
    """준비된 메시지를 내보낸 뒤 연결이 끊긴 것처럼 예외를 던진다."""

    def __init__(self, messages):
        self.sent = []
        self._messages = list(messages)

    def send(self, data):
        self.sent.append(json.loads(data))

    def recv(self):
        if self._messages:
            return json.dumps(self._messages.pop(0))
        raise websocket.WebSocketConnectionClosedException("closed")


def test_run_logs_events_and_reconnects_after_drop(tmp_path, monkeypatch):
    monkeypatch.setattr(bw, "poll_process", lambda *_a, **_k: None)  # 이 시험은 탭 이벤트만 본다 — 실제 프로세스 점검(실측 3초)을 타지 않게 격리
    conns = [
        _FakeWS([_created("T1", "https://a.com/?t=SECRET", title="A")]),
        _FakeWS([_created("T2", "https://b.com/")]),
    ]
    monkeypatch.setattr(bw, "_browser_ws_url", lambda port: "ws://fake")
    monkeypatch.setattr(bw, "RECONNECT_SEC", 0.0)
    monkeypatch.setattr(websocket, "create_connection", lambda *a, **k: conns.pop(0) if conns else _FakeWS([]))
    bw.run(log_path=tmp_path / "w.jsonl", stop_after=0.3)
    rows = [json.loads(x) for x in (tmp_path / "w.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["target_id"] for r in rows if r["event"] == "opened"] == ["T1", "T2"]
    assert "SECRET" not in json.dumps(rows)


def test_run_subscribes_to_target_discovery(tmp_path, monkeypatch):
    ws = _FakeWS([])
    monkeypatch.setattr(bw, "_browser_ws_url", lambda port: "ws://fake")
    monkeypatch.setattr(bw, "RECONNECT_SEC", 0.0)
    monkeypatch.setattr(websocket, "create_connection", lambda *a, **k: ws)
    bw.run(log_path=tmp_path / "w.jsonl", stop_after=0.1)
    assert ws.sent[0]["method"] == "Target.setDiscoverTargets" and ws.sent[0]["params"] == {"discover": True}


def test_run_waits_quietly_when_browser_is_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(bw, "poll_process", lambda *_a, **_k: None)  # 이 시험은 탭 이벤트만 본다 — 실제 프로세스 점검(실측 3초)을 타지 않게 격리
    monkeypatch.setattr(bw, "_browser_ws_url", lambda port: None)
    monkeypatch.setattr(bw, "RECONNECT_SEC", 0.01)
    bw.run(log_path=tmp_path / "w.jsonl", stop_after=0.1)
    assert not (tmp_path / "w.jsonl").exists()


def test_is_running_false_without_pid_file(tmp_path, monkeypatch):
    monkeypatch.setattr(bw, "PID_PATH", tmp_path / "pid.json")
    assert bw.is_running() is False


def test_is_running_rejects_reused_pid_of_other_process(tmp_path, monkeypatch):
    pid_file = tmp_path / "pid.json"
    pid_file.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")  # 살아 있지만 감시 프로세스가 아님
    monkeypatch.setattr(bw, "PID_PATH", pid_file)
    assert bw.is_running() is False


def test_is_running_false_for_dead_pid(tmp_path, monkeypatch):
    pid_file = tmp_path / "pid.json"
    pid_file.write_text(json.dumps({"pid": 2**22 + 12345}), encoding="utf-8")
    monkeypatch.setattr(bw, "PID_PATH", pid_file)
    assert bw.is_running() is False


def test_is_running_false_for_corrupt_pid_file(tmp_path, monkeypatch):
    pid_file = tmp_path / "pid.json"
    pid_file.write_text("not json", encoding="utf-8")
    monkeypatch.setattr(bw, "PID_PATH", pid_file)
    assert bw.is_running() is False


def test_stop_without_process_returns_false_and_clears_pid_file(tmp_path, monkeypatch):
    pid_file = tmp_path / "pid.json"
    pid_file.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
    monkeypatch.setattr(bw, "PID_PATH", pid_file)
    assert bw.stop() is False  # 다른 프로세스(이 시험 자신)는 절대 종료하지 않는다
    assert not pid_file.exists()


def test_start_launches_detached_and_second_start_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(bw, "PID_PATH", tmp_path / "pid.json")
    monkeypatch.setattr(bw, "LOG_PATH", tmp_path / "w.jsonl")
    launched = []

    class _Proc:
        pid = 4242

    def fake_popen(cmd, **kwargs):
        launched.append((cmd, kwargs))
        return _Proc()

    monkeypatch.setattr(bw.subprocess, "Popen", fake_popen)
    assert bw.start() is True
    assert json.loads((tmp_path / "pid.json").read_text(encoding="utf-8"))["pid"] == 4242
    cmd, kwargs = launched[0]
    assert cmd[1].endswith("browser_watch.py") and cmd[2] == "run"
    assert kwargs["stdout"] == subprocess.DEVNULL
    monkeypatch.setattr(bw, "is_running", lambda: True)
    assert bw.start() is False and len(launched) == 1


def test_script_runs_as_subprocess_status_and_bad_command():
    # browser_watch.py 가 콘솔에 한글을 출력한다 — Windows 콘솔 기본 코드페이지(cp949)로
    # 적히면 이쪽에서 utf-8 로 디코드하다 깨진다. 자식 프로세스 stdio 를 utf-8 로 강제한다.
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    ok = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "browser" / "cdp" / "browser_watch.py"), "status"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
        env=env,
    )
    assert ok.returncode == 0 and "browser_watch:" in ok.stdout
    bad = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "browser" / "cdp" / "browser_watch.py"), "nope"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
        env=env,
    )
    assert bad.returncode == 1


def test_cdp_force_start_survives_watch_failures(monkeypatch, capsys):
    from scripts.browser.cdp import cdp_force_start as cfs

    def boom():
        raise RuntimeError("watch broke")

    monkeypatch.setattr(bw, "start", boom)
    monkeypatch.setattr(bw, "stop", boom)
    cfs._start_watch()  # 예외를 밖으로 내보내면 브라우저 시작이 막힌다
    cfs._stop_watch()
    out = capsys.readouterr().out
    assert "시작 실패" in out and "종료 실패" in out


@pytest.mark.parametrize("fn", ["_start_watch", "_stop_watch"])
def test_cdp_force_start_has_watch_hooks(fn):
    from scripts.browser.cdp import cdp_force_start as cfs

    assert callable(getattr(cfs, fn))


def test_is_running_true_for_real_watch_process(tmp_path, monkeypatch):
    """실제로 browser_watch.py 를 실행 중인 프로세스는 감시 프로세스로 인식하고 stop 이 종료시킨다."""
    monkeypatch.setattr(bw, "PID_PATH", tmp_path / "pid.json")
    monkeypatch.setattr(bw, "_browser_ws_url", lambda port: None)
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "scripts" / "browser" / "cdp" / "browser_watch.py"), "run"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        (tmp_path / "pid.json").write_text(json.dumps({"pid": proc.pid}), encoding="utf-8")
        assert bw.is_running() is True
        assert bw.stop() is True
        proc.wait(timeout=10)
        assert bw.is_running() is False
    finally:
        if proc.poll() is None:
            proc.kill()


@pytest.mark.parametrize("exc_name", ["NoSuchProcess", "AccessDenied"])
def test_is_running_false_when_process_info_unreadable(tmp_path, monkeypatch, exc_name):
    """확인하는 사이 프로세스가 사라졌거나 권한이 없으면 예외 없이 '실행 중 아님'."""
    import psutil

    pid_file = tmp_path / "pid.json"
    pid_file.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
    monkeypatch.setattr(bw, "PID_PATH", pid_file)

    def raiser(pid):
        raise getattr(psutil, exc_name)(pid)

    monkeypatch.setattr(psutil, "Process", raiser)
    assert bw.is_running() is False


def test_mask_title_hides_query_of_url_shaped_title():
    """로드 전 제목은 URL 문자열이라 토큰이 새어 나갈 수 있다(실제 브라우저 확인에서 발견)."""
    assert bw.mask_title("example.com/?token=SECRET123") == "example.com/?token=***"
    assert "SECRET" not in bw.mask_title("a.com/p?x=SECRET&y=2")


def test_mask_title_keeps_normal_titles_and_truncates():
    assert bw.mask_title("네이버 블로그") == "네이버 블로그"
    assert bw.mask_title("검색 결과: a?b=c") == "검색 결과: a?b=c"  # 공백이 있으면 URL 이 아니라 문장
    assert len(bw.mask_title("가" * 200)) == 80


def test_state_masks_title_in_records():
    rec = bw.WatchState().handle(_created("T1", "https://e.com/?t=S", title="e.com/?t=SECRET"), 0)[0]
    assert "SECRET" not in json.dumps(rec)

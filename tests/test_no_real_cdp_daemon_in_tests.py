"""시험 부작용 방지 — 시험 중에는 실제 CDP 데몬·Chrome 을 띄울 수 없다(tests/conftest.py _no_real_cdp_daemon)."""

import subprocess
import sys

import pytest


def test_cdp_daemon_launch_is_blocked():
    with pytest.raises(RuntimeError, match="CDP 데몬"):
        subprocess.Popen([sys.executable, "scripts/browser/cdp/cdp_daemon.py", "start"])


def test_chrome_remote_debugging_launch_is_blocked():
    with pytest.raises(RuntimeError, match="CDP 데몬"):
        subprocess.Popen(["chrome.exe", "--remote-debugging-port=9222"])


def test_other_processes_still_run():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    assert proc.wait(timeout=30) == 0


def test_test_can_override_with_its_own_fake(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda args, *a, **k: calls.append(args))
    subprocess.Popen(["x", "cdp_daemon.py"])
    assert calls == [["x", "cdp_daemon.py"]]


def test_mentioning_the_name_is_not_a_launch():
    # git show / grep 처럼 파일 이름만 언급하는 호출은 막지 않는다(test_root_calc_gate 가 git show 를 쓴다)
    proc = subprocess.Popen(["git", "--version"], stdout=subprocess.PIPE)
    proc.communicate(timeout=30)
    from tests.conftest import _is_cdp_launch

    assert not _is_cdp_launch(["git", "show", "HEAD:tests/test_x_cdp_daemon.py"])
    assert _is_cdp_launch([sys.executable, "scripts/browser/cdp/cdp_daemon.py", "start"])

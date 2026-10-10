import json

import pytest

from scripts.browser.session import browser_sandbox_gate as gate


def test_sandbox_gate_detects_codex_sandbox(monkeypatch):
    monkeypatch.delenv("CODEX_SANDBOX_NETWORK_DISABLED", raising=False)
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.delenv("CODEX_MANAGED_BY_NPM", raising=False)
    monkeypatch.delenv("HAEHAN_NO_BROWSER_LAUNCH", raising=False)
    assert gate.is_sandboxed_runtime() is False

    monkeypatch.setenv("CODEX_SANDBOX_NETWORK_DISABLED", "1")
    assert gate.is_sandboxed_runtime() is True


def test_sandbox_gate_raises_structured_payload(monkeypatch):
    monkeypatch.setenv("CODEX_SANDBOX_NETWORK_DISABLED", "1")

    with pytest.raises(RuntimeError) as exc:
        gate.assert_browser_launch_allowed(component="unit.test", action="browser_launch")

    payload = json.loads(str(exc.value))
    assert payload["ok"] is False
    assert payload["code"] == gate.SANDBOX_BROWSER_LAUNCH_BLOCKED
    assert payload["component"] == "unit.test"
    assert "CODEX_SANDBOX_NETWORK_DISABLED" in payload["markers"]


def test_cdp_launcher_blocks_scheduler_start_in_sandbox(monkeypatch):
    from scripts.browser.agent import cdp_launcher

    monkeypatch.setenv("CODEX_SANDBOX_NETWORK_DISABLED", "1")
    monkeypatch.setattr(cdp_launcher, "probe_cdp", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(
        cdp_launcher,
        "is_task_registered",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("scheduler must not be queried")),
    )

    with pytest.raises(RuntimeError) as exc:
        cdp_launcher.ensure_cdp()

    assert gate.SANDBOX_BROWSER_LAUNCH_BLOCKED in str(exc.value)


def test_connection_never_autostarts_daemon_and_raises_clear_error(tmp_path, monkeypatch):
    """CDP 가 꺼져 있으면 라이브러리는 어떤 프로세스도 띄우지 않고 명확한 오류를 낸다(2026-10-08)."""
    import subprocess

    from scripts.browser.cdp import connection

    monkeypatch.setattr(connection, "_DAEMON_STATE", tmp_path / "cdp_daemon_state.json")
    monkeypatch.setattr(connection, "_is_cdp_live", lambda _port: False)

    def _fail(*_a, **_k):
        raise AssertionError("subprocess must not be called")

    monkeypatch.setattr(subprocess, "Popen", _fail)
    monkeypatch.setattr(subprocess, "run", _fail)
    assert not hasattr(connection, "_ensure_cdp_daemon")

    with pytest.raises(connection.CdpNotRunningError) as exc:
        connection._get_cdp_port()

    assert "cdp_daemon.py start" in str(exc.value)


def test_connection_uses_state_file_port_only_when_live(tmp_path, monkeypatch):
    from scripts.browser.cdp import connection

    state = tmp_path / "cdp_daemon_state.json"
    state.write_text('{"cdp_port": 9555}', encoding="utf-8")
    monkeypatch.setattr(connection, "_DAEMON_STATE", state)
    monkeypatch.setattr(connection, "_is_cdp_live", lambda port: port == 9555)

    assert connection._get_cdp_port() == 9555


def test_cdp_daemon_blocks_chrome_launch_in_sandbox(monkeypatch):
    from scripts.browser.cdp import cdp_daemon

    monkeypatch.setenv("CODEX_SANDBOX_NETWORK_DISABLED", "1")
    monkeypatch.setattr(
        cdp_daemon,
        "_find_browser",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("browser lookup must not run")),
    )

    with pytest.raises(RuntimeError) as exc:
        cdp_daemon._launch_chrome()

    assert gate.SANDBOX_BROWSER_LAUNCH_BLOCKED in str(exc.value)

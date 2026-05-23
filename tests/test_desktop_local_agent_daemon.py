from __future__ import annotations

import subprocess
from pathlib import Path

from desktop import local_agent_daemon as daemon
from desktop import tray_runtime


class FakeProc:
    pid = 12345

    def __init__(self) -> None:
        self.terminated = False
        self.killed = False

    def poll(self):
        return None if not self.terminated and not self.killed else 0

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.killed = True


def test_build_agent_command_has_no_token():
    cmd = daemon.build_agent_command("https://haehan-ai.kr/orchestrator")
    joined = " ".join(cmd)
    assert "local_agent.agent" in joined
    assert "--run" in cmd
    assert "--server" in cmd
    assert "device_token" not in joined.lower()
    assert "registration_code" not in joined.lower()


def test_build_agent_env_enables_ws():
    env = daemon.build_agent_env({})
    assert env["HAEHAN_AGENT_WS_ENABLED"] == "true"
    assert env["HAEHAN_AGENT_POLL_SEC"] == "2"


def test_daemon_does_not_start_when_unregistered(tmp_path: Path):
    d = daemon.LocalAgentDaemon(app_root=tmp_path, popen=lambda *a, **k: FakeProc())
    state = d.start(tray_runtime.RegistrationStatus(registered=False))
    assert state.started is False
    assert state.reason == "not_registered"


def test_daemon_start_and_stop(tmp_path: Path):
    calls = {}

    def fake_popen(command, **kwargs):
        calls["command"] = command
        calls["kwargs"] = kwargs
        return FakeProc()

    d = daemon.LocalAgentDaemon(app_root=tmp_path, popen=fake_popen)
    status = tray_runtime.RegistrationStatus(
        registered=True,
        server_url="https://haehan-ai.kr/orchestrator",
        agent_id="la-1234567890ab",
    )
    state = d.start(status)
    assert state.started is True
    assert state.pid == 12345
    assert state.agent_id_masked == "la-123***90ab"
    assert calls["command"] == daemon.build_agent_command(status.server_url)
    assert calls["kwargs"]["cwd"] == str(tmp_path)
    assert calls["kwargs"]["stderr"] == subprocess.STDOUT
    d.stop()
    assert d.running is False


def test_run_tray_mode_full_can_disable_legacy_heartbeat():
    status = tray_runtime.RegistrationStatus(
        registered=True,
        server_url="https://haehan-ai.kr/orchestrator",
        agent_id="la-1234567890ab",
    )
    result = tray_runtime.run_tray_mode_full(
        skip_gui=False,
        start_heartbeat=False,
        plaintext_fallback=False,
    )
    assert "heartbeat_started" in result
    assert result["start_heartbeat"] is False

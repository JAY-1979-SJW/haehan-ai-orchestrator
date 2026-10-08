import json

import pytest

from scripts.browser.session import browser_sandbox_gate as gate


def test_sandbox_gate_detects_codex_sandbox(monkeypatch):
    monkeypatch.delenv("CODEX_SANDBOX_NETWORK_DISABLED", raising=False)
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.delenv("CODEX_MANAGED_BY_NPM", raising=False)
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
    from ai_orchestrator.local_agent.browser import cdp_launcher

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


def test_web_connector_blocks_daemon_autostart_in_sandbox(tmp_path, monkeypatch):
    from scripts.browser.cdp import connection

    state_file = tmp_path / "cdp_daemon_state.json"
    monkeypatch.setattr(connection, "_DAEMON_STATE", state_file)
    monkeypatch.setenv("CODEX_SANDBOX_NETWORK_DISABLED", "1")

    with pytest.raises(RuntimeError) as exc:
        connection._ensure_cdp_daemon()

    assert gate.SANDBOX_BROWSER_LAUNCH_BLOCKED in str(exc.value)


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

"""AGENT_GUI_TRAY_01 — 12+ 테스트."""

from __future__ import annotations

import json
from pathlib import Path

# ── 1) GUI state enum / transition ─────────────────────────────────


def test_state_enum_complete():
    from local_agent import gui_state as gs

    for s in (
        "STATE_NOT_REGISTERED",
        "STATE_CONNECTING",
        "STATE_AUTHENTICATING",
        "STATE_CONNECTED",
        "STATE_HEARTBEAT_OK",
        "STATE_DISCONNECTED",
        "STATE_AUTH_FAILED",
        "STATE_RECONNECTING",
    ):
        assert hasattr(gs, s), f"missing: {s}"


def test_transition_not_registered_to_connecting_on_register_started():
    from local_agent import gui_state as gs

    assert gs.transition(gs.STATE_NOT_REGISTERED, "register_started") == gs.STATE_CONNECTING


def test_transition_authenticating_to_connected_on_auth_ok():
    from local_agent import gui_state as gs

    assert gs.transition(gs.STATE_AUTHENTICATING, "auth_ok") == gs.STATE_CONNECTED


def test_transition_authenticating_to_auth_failed_on_4401():
    from local_agent import gui_state as gs

    assert gs.transition(gs.STATE_AUTHENTICATING, "auth_failed_4401") == gs.STATE_AUTH_FAILED


def test_transition_connected_to_heartbeat_ok_on_ack():
    from local_agent import gui_state as gs

    assert gs.transition(gs.STATE_CONNECTED, "heartbeat_ack") == gs.STATE_HEARTBEAT_OK


def test_transition_unknown_keeps_state():
    from local_agent import gui_state as gs

    assert gs.transition(gs.STATE_CONNECTED, "garbage_event") == gs.STATE_CONNECTED


# ── 2) GuiController ─────────────────────────────────────────────


def test_controller_initial_state():
    from local_agent import gui_state as gs

    c = gs.GuiController(server_url="https://x.example")
    m = c.model
    assert m.state == gs.STATE_NOT_REGISTERED
    assert m.agent_id == ""
    assert m.server_url == "https://x.example"


def test_controller_fire_updates_state():
    from local_agent import gui_state as gs

    c = gs.GuiController()
    c.fire("register_started")
    assert c.model.state == gs.STATE_CONNECTING
    c.fire("connect_failed", error_code="SERVER_NOT_REACHABLE")
    assert c.model.state == gs.STATE_SERVER_UNREACHABLE
    assert c.model.last_error_code == "SERVER_NOT_REACHABLE"


def test_controller_subscribe_listener_called():
    from local_agent import gui_state as gs

    c = gs.GuiController()
    seen = []
    c.subscribe(lambda snap: seen.append(snap.state))
    c.fire("register_started")
    assert gs.STATE_CONNECTING in seen


# ── 3) PII / token leak 방지 ─────────────────────────────────────


def test_model_to_dict_no_token_keys():
    from local_agent import gui_state as gs

    m = gs.GuiModel(server_url="https://x?device_token=SECRETXYZ", agent_id="la-abc123def456")
    d = m.to_dict()
    assert "device_token" not in d
    assert "token" not in d
    js = json.dumps(d, ensure_ascii=False)
    assert "SECRETXYZ" not in js
    # agent_id 원문 미노출
    assert "abc123def456" not in js
    # 마스킹은 포함
    assert "la-abc***f456" in d["agent_id_masked"]


def test_register_failed_4401_explanation_present():
    from local_agent import gui_state as gs

    c = gs.GuiController()
    c.fire("register_started")  # NOT_REGISTERED → CONNECTING
    c.fire("ws_open")  # CONNECTING → AUTHENTICATING
    c.fire("auth_failed_4401", error_code="AUTH_FAILED_4401")
    m = c.model
    assert m.state == gs.STATE_AUTH_FAILED
    assert "4401" in m.last_error_message_user
    assert "재등록" in m.last_error_message_user


# ── 4) diagnostics render ───────────────────────────────────────


def test_render_user_block_no_token_leak():
    from local_agent import gui_state as gs

    c = gs.GuiController(server_url="https://x.example/orchestrator?device_token=SECRET")
    c.set_agent_id("la-leak123test456")
    block = c.render_user_block()
    assert "SECRET" not in block
    assert "leak123test456" not in block  # raw agent_id
    # mask_agent_id: f"{agent_id[:6]}***{agent_id[-4:]}" → "la-lea***t456"
    assert "la-lea***t456" in block  # masked


# ── 5) gui_app imports ─────────────────────────────────────────


def test_desktop_launcher_diagnostics_includes_safe_recovery_plan(monkeypatch):
    import local_agent.desktop_config as dc
    from local_agent import desktop_launcher as dl
    from local_agent import token_store as ts

    class _Cfg:
        server_url = "https://x.example/orchestrator?device_token=SECRET"
        agent_id = "la-leak123test456"

    monkeypatch.setattr(ts, "describe_backend", lambda: (True, "test-backend"))
    monkeypatch.setattr(ts, "has_device_token", lambda **_: False)
    monkeypatch.setattr(dc, "load_config", lambda: _Cfg())

    data = dl.show_diagnostics("")
    assert data["recovery_plan"]["next_action"] == "REGISTER_REQUIRED"
    blob = json.dumps(data, ensure_ascii=False)
    assert "SECRET" not in blob
    assert "leak123test456" not in blob
    assert '"device_token"' not in blob


def test_gui_app_module_imports():
    from local_agent import gui_app

    assert hasattr(gui_app, "HaehanAgentGuiApp")
    assert hasattr(gui_app, "launch_gui")


def test_gui_tray_module_imports():
    from local_agent import gui_tray

    assert hasattr(gui_tray, "run_tray_with_app")


def test_gui_app_has_required_methods():
    from local_agent.gui_app import HaehanAgentGuiApp

    for m in ("on_register", "on_connect", "on_diagnostics", "on_reset", "on_quit", "_build_ui", "_poll_model"):
        assert hasattr(HaehanAgentGuiApp, m), f"missing: {m}"


# ── 6) desktop_launcher --gui 옵션 ──────────────────────────────


def test_desktop_launcher_supports_gui_flag():
    text = Path("local_agent/desktop_launcher.py").read_text(encoding="utf-8")
    assert "--gui" in text


def test_desktop_launcher_routes_gui_to_tray():
    """--gui 처리 분기가 desktop_launcher.main 안에 있는지."""
    text = Path("local_agent/desktop_launcher.py").read_text(encoding="utf-8")
    assert "gui_tray" in text


# ── 7) build script hidden imports ──────────────────────────────


def test_build_script_has_gui_hidden_imports():
    text = Path("scripts/build_desktop_agent_windows.py").read_text(encoding="utf-8")
    for imp in ("tkinter", "pystray", "PIL"):
        assert imp in text, f"build script missing hidden import: {imp}"


# ── 8) audit ────────────────────────────────────────────────────


def test_audit_warn_unsigned_or_warn_build_not_executed():
    from scripts.ops import audit_local_agent_gui_tray as a

    v = a.judge_gui(cli_regression_ok=True, gui_build_executed=False)
    assert v.code in (
        "PASS_AGENT_GUI_TRAY",
        "WARN_TRAY_LIBRARY_NOT_INSTALLED",
        "WARN_GUI_BUILD_NOT_EXECUTED",
        "WARN_UNSIGNED_BINARY",
    )


def test_audit_fail_cli_regression():
    from scripts.ops import audit_local_agent_gui_tray as a

    v = a.judge_gui(cli_regression_ok=False)
    assert v.code == "FAIL_CLI_REGRESSION"


# ── 9) 회귀 가드 ────────────────────────────────────────────────


def test_regression_desktop_launcher_cli_intact():
    from local_agent import desktop_launcher

    for sym in ("main", "self_test", "register_flow", "connect_flow"):
        assert hasattr(desktop_launcher, sym)


def test_regression_connection_diagnostics_intact():
    from local_agent import connection_diagnostics as cd

    assert hasattr(cd, "normalize_ws_url")
    assert hasattr(cd, "mask_agent_id")
    assert hasattr(cd, "explain_error")


def test_regression_token_store_intact():
    from local_agent import token_store as ts

    assert hasattr(ts, "save_device_token")
    assert hasattr(ts, "load_device_token")


def test_regression_existing_cli_self_test_runs():
    from local_agent import desktop_launcher

    r = desktop_launcher.self_test()
    assert r["ok"] is True

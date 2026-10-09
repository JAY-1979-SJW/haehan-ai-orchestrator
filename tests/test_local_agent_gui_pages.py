"""AGENT_GUI_DESIGN_IMPLEMENTATION_01 — 14+ 테스트."""

from __future__ import annotations

# ── 2) log buffer + redact ────────────────────────────────────


def test_log_redact_device_token_kv():
    from core.agent_runtime.gui.gui_log_buffer import redact

    r = redact("device_token=ABCDEFGH12345678 hello")
    assert "ABCDEFGH12345678" not in r
    assert "[REDACTED]" in r


def test_log_redact_registration_code_kv():
    from core.agent_runtime.gui.gui_log_buffer import redact

    r = redact("registration_code=XYZ987abc world")
    assert "XYZ987abc" not in r


def test_log_redact_authorization_bearer():
    from core.agent_runtime.gui.gui_log_buffer import redact

    r = redact("Authorization: Bearer abc123def456ghi789")
    assert "abc123def456ghi789" not in r


def test_log_redact_json_form():
    from core.agent_runtime.gui.gui_log_buffer import redact

    r = redact('{"device_token": "RAW_LONG_TOKEN_VALUE_HERE"}')
    assert "RAW_LONG_TOKEN_VALUE_HERE" not in r
    assert "REDACTED" in r


def test_log_buffer_stores_redacted_only():
    from core.agent_runtime.gui.gui_log_buffer import LogBuffer

    b = LogBuffer()
    b.info("device_token=SECRET_VALUE_8plus stored")
    tail = b.tail()
    assert tail
    assert all("SECRET_VALUE_8plus" not in e.msg for e in tail)


def test_log_buffer_export_redacts(tmp_path):
    from core.agent_runtime.gui.gui_log_buffer import LogBuffer

    b = LogBuffer()
    b.info("device_token=RAW_TOKEN_VALUE_22ch and more text")
    p = tmp_path / "out.jsonl"
    result = b.export_jsonl(p)
    assert result["count"] >= 1
    text = p.read_text(encoding="utf-8")
    assert "RAW_TOKEN_VALUE_22ch" not in text
    assert "[REDACTED]" in text


def test_log_buffer_filter_by_level():
    from core.agent_runtime.gui.gui_log_buffer import LogBuffer

    b = LogBuffer()
    b.info("info msg")
    b.warn("warn msg")
    b.err("err msg")
    assert len(b.tail(level_filter="WARN")) == 1
    assert len(b.tail(level_filter="ALL")) == 3


def test_log_buffer_ring_maxlen():
    from core.agent_runtime.gui.gui_log_buffer import LogBuffer

    b = LogBuffer(maxlen=10)
    for i in range(25):
        b.info(f"msg-{i}")
    assert len(b) == 10


# ── 3) 아이콘 ─────────────────────────────────────────────────


def test_sidebar_icons_present():
    from core.agent_runtime.gui.gui_icons import SIDEBAR_ICONS

    for k in ("dashboard", "registration", "logs", "settings"):
        assert k in SIDEBAR_ICONS


def test_make_sparkline_returns_image():
    from core.agent_runtime.gui.gui_icons import make_sparkline

    img = make_sparkline([0.1, 0.5, 0.8, 0.3, 0.9])
    assert img is not None
    assert img.size == (240, 36)


def test_make_dot_returns_image():
    from core.agent_runtime.gui.gui_icons import make_dot

    img = make_dot("#10B981")
    assert img is not None


# ── 7) 회귀 가드 ────────────────────────────────────────────


def test_regression_gui_state_unchanged():
    from core.agent_runtime.gui import gui_state as gs

    for s in ("GuiController", "GuiModel", "transition", "STATE_CONNECTED"):
        assert hasattr(gs, s)


def test_regression_connection_diagnostics_unchanged():
    from core.agent_runtime.connection import connection_diagnostics as cd

    for s in ("normalize_ws_url", "mask_agent_id", "explain_error", "find_token_leaks"):
        assert hasattr(cd, s)

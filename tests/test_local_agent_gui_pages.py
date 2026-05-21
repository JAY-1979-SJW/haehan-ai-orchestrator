"""AGENT_GUI_DESIGN_IMPLEMENTATION_01 — 14+ 테스트."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# ── 1) 페이지 enum ─────────────────────────────────────────────


def test_page_enum_all_four():
    """직전 4탭 구조 → 신 3탭 (Chat/Status/Diagnostics) + alias 유지.
    회귀 호환: 신 enum 3개 + 직전 alias 4개 모두 정의되어야 함."""
    from local_agent import gui_app
    # 신 3탭 enum
    for p in ("PAGE_CHAT", "PAGE_STATUS", "PAGE_DIAGNOSTICS"):
        assert hasattr(gui_app, p)
    # 직전 4 alias (회귀 호환)
    for p in ("PAGE_DASHBOARD", "PAGE_REGISTRATION",
              "PAGE_LOGS", "PAGE_SETTINGS"):
        assert hasattr(gui_app, p)
    assert len(gui_app.ALL_PAGES) == 3   # 신 구조 기준


def test_gui_app_has_page_builders():
    """신 구조: _build_chat_tab / _build_status_tab / _build_diagnostics_tab.
    직전: _build_ui alias 유지."""
    from local_agent.gui_app import HaehanAgentGuiApp
    for m in ("_build_chat_tab", "_build_status_tab",
              "_build_diagnostics_tab",
              "show_page", "_bind_shortcuts",
              "_build_ui"):
        assert hasattr(HaehanAgentGuiApp, m), f"missing: {m}"


# ── 2) log buffer + redact ────────────────────────────────────


def test_log_redact_device_token_kv():
    from local_agent.gui_log_buffer import redact
    r = redact("device_token=ABCDEFGH12345678 hello")
    assert "ABCDEFGH12345678" not in r
    assert "[REDACTED]" in r


def test_log_redact_registration_code_kv():
    from local_agent.gui_log_buffer import redact
    r = redact("registration_code=XYZ987abc world")
    assert "XYZ987abc" not in r


def test_log_redact_authorization_bearer():
    from local_agent.gui_log_buffer import redact
    r = redact("Authorization: Bearer abc123def456ghi789")
    assert "abc123def456ghi789" not in r


def test_log_redact_json_form():
    from local_agent.gui_log_buffer import redact
    r = redact('{"device_token": "RAW_LONG_TOKEN_VALUE_HERE"}')
    assert "RAW_LONG_TOKEN_VALUE_HERE" not in r
    assert "REDACTED" in r


def test_log_buffer_stores_redacted_only():
    from local_agent.gui_log_buffer import LogBuffer
    b = LogBuffer()
    b.info("device_token=SECRET_VALUE_8plus stored")
    tail = b.tail()
    assert tail
    assert all("SECRET_VALUE_8plus" not in e.msg for e in tail)


def test_log_buffer_export_redacts(tmp_path):
    from local_agent.gui_log_buffer import LogBuffer
    b = LogBuffer()
    b.info("device_token=RAW_TOKEN_VALUE_22ch and more text")
    p = tmp_path / "out.jsonl"
    result = b.export_jsonl(p)
    assert result["count"] >= 1
    text = p.read_text(encoding="utf-8")
    assert "RAW_TOKEN_VALUE_22ch" not in text
    assert "[REDACTED]" in text


def test_log_buffer_filter_by_level():
    from local_agent.gui_log_buffer import LogBuffer
    b = LogBuffer()
    b.info("info msg")
    b.warn("warn msg")
    b.err("err msg")
    assert len(b.tail(level_filter="WARN")) == 1
    assert len(b.tail(level_filter="ALL")) == 3


def test_log_buffer_ring_maxlen():
    from local_agent.gui_log_buffer import LogBuffer
    b = LogBuffer(maxlen=10)
    for i in range(25):
        b.info(f"msg-{i}")
    assert len(b) == 10


# ── 3) 아이콘 ─────────────────────────────────────────────────


def test_sidebar_icons_present():
    from local_agent.gui_icons import SIDEBAR_ICONS
    for k in ("dashboard", "registration", "logs", "settings"):
        assert k in SIDEBAR_ICONS


def test_make_sparkline_returns_image():
    from local_agent.gui_icons import make_sparkline
    img = make_sparkline([0.1, 0.5, 0.8, 0.3, 0.9])
    assert img is not None
    assert img.size == (240, 36)


def test_make_dot_returns_image():
    from local_agent.gui_icons import make_dot
    img = make_dot("#10B981")
    assert img is not None


# ── 4) 단축키 / tray sync ───────────────────────────────────


def test_gui_app_binds_shortcuts():
    src = Path("local_agent/gui_app.py").read_text(encoding="utf-8")
    for pat in ("Control-Key-1", "Control-Key-2", "Control-Key-3",
                "Control-Key-4", "Control-r", "F1", "Escape"):
        assert pat in src, f"missing shortcut: {pat}"


def test_tray_menu_synced_with_pages():
    """신 구조 — 트레이 메뉴는 한글 항목 (열기/Chat/상태/진단/AI 설정/재등록/종료)."""
    src = Path("local_agent/gui_tray.py").read_text(encoding="utf-8")
    for label in ("열기", "Chat 열기", "상태 보기", "진단 보기",
                   "AI 설정", "재등록", "종료"):
        assert label in src, f"tray missing: {label}"


# ── 5) PII 안전 ─────────────────────────────────────────────


def test_gui_app_source_no_hardcoded_token():
    import re
    text = Path("local_agent/gui_app.py").read_text(encoding="utf-8")
    matches = re.findall(r'"device_token"\s*:\s*"([A-Za-z0-9._\-]{20,})"',
                          text)
    real = [m for m in matches if "<" not in m and m != "[REDACTED]"]
    assert real == []


def test_state_source_unified_no_gui_model_duplicate():
    text = Path("local_agent/gui_app.py").read_text(encoding="utf-8")
    assert "class GuiModel" not in text, "GuiModel must only be in gui_state"


# ── 6) audit ────────────────────────────────────────────────


def test_audit_pass_on_real_source():
    from scripts.ops import audit_local_agent_gui_implementation as a
    v = a.judge_impl(cli_regression_ok=True)
    assert v.code == "PASS_AGENT_GUI_DESIGN_IMPLEMENTATION", v.reasons


def test_audit_fail_cli_regression_signal():
    from scripts.ops import audit_local_agent_gui_implementation as a
    v = a.judge_impl(cli_regression_ok=False)
    assert v.code == "FAIL_CLI_REGRESSION"


# ── 7) 회귀 가드 ────────────────────────────────────────────


def test_regression_gui_state_unchanged():
    from local_agent import gui_state as gs
    for s in ("GuiController", "GuiModel", "transition", "STATE_CONNECTED"):
        assert hasattr(gs, s)


def test_regression_connection_diagnostics_unchanged():
    from local_agent import connection_diagnostics as cd
    for s in ("normalize_ws_url", "mask_agent_id", "explain_error",
              "find_token_leaks"):
        assert hasattr(cd, s)


def test_regression_desktop_launcher_gui_flag():
    text = Path("local_agent/desktop_launcher.py").read_text(encoding="utf-8")
    assert "--gui" in text


def test_regression_cli_self_test_callable():
    from local_agent import desktop_launcher
    r = desktop_launcher.self_test()
    assert r["ok"] is True

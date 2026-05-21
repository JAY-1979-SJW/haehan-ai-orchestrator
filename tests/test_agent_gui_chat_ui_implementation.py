"""AGENT_GUI_CHAT_UI_IMPLEMENTATION_01 — 18+ 테스트."""
from __future__ import annotations

from pathlib import Path

import pytest


# ── 1) 3탭 enum ────────────────────────────────────────────


def test_three_tab_enums():
    from local_agent import gui_app
    assert gui_app.PAGE_CHAT == "chat"
    assert gui_app.PAGE_STATUS == "status"
    assert gui_app.PAGE_DIAGNOSTICS == "diagnostics"
    assert len(gui_app.ALL_PAGES) == 3


def test_chat_is_default_tab():
    from local_agent import gui_app
    assert gui_app.PAGE_CHAT == gui_app.ALL_PAGES[0]


def test_gui_app_has_required_methods():
    from local_agent.gui_app import HaehanAgentGuiApp
    for m in ("_build_chat_tab", "_build_status_tab",
              "_build_diagnostics_tab",
              "open_wizard", "open_ai_settings",
              "on_send_chat", "on_minimize_to_tray",
              "show_page", "_bind_shortcuts",
              "on_reconnect", "on_reset", "on_quit",
              "on_copy_diagnostics"):
        assert hasattr(HaehanAgentGuiApp, m), f"missing: {m}"


# ── 2) AI mode / 상태 enum ────────────────────────────────


def test_ai_mode_three_options():
    from local_agent import gui_chat_state as cs
    assert cs.MODE_DEV_TEST_KEY in cs.ALL_MODES
    assert cs.MODE_SERVER_PROXY in cs.ALL_MODES
    assert cs.MODE_USER_BYOK in cs.ALL_MODES
    assert len(cs.ALL_MODES) == 3


def test_ai_status_three_states():
    from local_agent import gui_chat_state as cs
    for s in (cs.AI_NOT_CONFIGURED, cs.AI_READY_PLACEHOLDER, cs.AI_ERROR):
        assert s in cs.ALL_AI_STATUSES


def test_chat_ui_controller_basic():
    from local_agent.gui_chat_state import (
        ChatUiController, ChatUiMessage,
        MODE_USER_BYOK, AI_READY_PLACEHOLDER,
    )
    c = ChatUiController()
    assert c.state.external_call_count == 0
    c.set_mode(MODE_USER_BYOK)
    c.set_ai_status(AI_READY_PLACEHOLDER)
    assert c.state.ai_mode.mode == MODE_USER_BYOK
    assert c.state.ai_status == AI_READY_PLACEHOLDER
    c.append_message(ChatUiMessage(role="user", text_redacted="hi"))
    assert len(c.state.messages) == 1


# ── 3) Placeholder adapter — 외부 호출 0 ──────────────────


def test_placeholder_adapter_not_configured():
    from local_agent.ai_chat_adapter import make_default_adapter
    a = make_default_adapter()
    assert a.is_configured() is False


def test_placeholder_adapter_send_returns_not_configured():
    from local_agent.ai_chat_adapter import make_default_adapter
    a = make_default_adapter()
    r = a.send_message(text_raw="hello")
    assert r.ok is True
    assert "설정되지 않" in r.text_redacted
    assert r.external_call_count == 0


def test_placeholder_adapter_validate_empty():
    from local_agent.ai_chat_adapter import make_default_adapter
    a = make_default_adapter()
    ok, _ = a.validate_message("")
    assert ok is False
    ok2, _ = a.validate_message("hi")
    assert ok2 is True


def test_placeholder_adapter_validate_too_long():
    from local_agent.ai_chat_adapter import make_default_adapter
    a = make_default_adapter()
    ok, _ = a.validate_message("x" * 9000)
    assert ok is False


def test_placeholder_adapter_detect_sensitive():
    from local_agent.ai_chat_adapter import make_default_adapter
    a = make_default_adapter()
    assert a.detect_sensitive_input(
        "OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz123456") is True
    assert a.detect_sensitive_input("안녕하세요") is False


def test_adapter_send_does_not_persist_or_call_external():
    """adapter 모듈 소스 정적 검사 — SDK import / 외부 호출 / 파일 쓰기 부재.

    `from . import openai_chat_client` 같은 로컬 모듈 import 는 허용.
    실제 SDK 호출 패턴만 검사.
    """
    import re
    src = Path("local_agent/ai_chat_adapter.py").read_text(encoding="utf-8")
    low = src.lower()
    for pat in ("openai.chat", "openai.completions",
                "anthropic.messages", "anthropic.completions",
                "https://api.openai.com", "https://api.anthropic.com",
                "requests.post", "httpx.post"):
        assert pat not in low, f"forbidden pattern: {pat}"
    # file write 부재
    assert not re.search(r"open\s*\([^)]*['\"][wa]", src)
    for pat in (".write_text", "json.dump", "set_password"):
        assert pat not in src, f"persistence call: {pat}"


# ── 4) gui_app 정적 검사 — 외부 호출 부재 ───────────────


def test_gui_app_no_external_ai_call():
    """gui_app 정적 검사 — SDK 호출/HTTPS API endpoint 부재.

    로컬 모듈 import (`from . import openai_chat_client`) 는 허용 —
    adapter 분기를 통해 외부 호출은 openai_chat_client.py 안에서만 발생.
    """
    src = Path("local_agent/gui_app.py").read_text(encoding="utf-8")
    low = src.lower()
    for pat in ("openai.chat", "openai.completions",
                "anthropic.messages",
                "https://api.openai.com", "https://api.anthropic.com",
                "requests.post", "httpx.post"):
        assert pat not in low, f"forbidden in gui_app: {pat}"


def test_gui_app_no_raw_key_or_token():
    import re
    src = Path("local_agent/gui_app.py").read_text(encoding="utf-8")
    assert not re.search(r"\bsk-[A-Za-z0-9]{20,}\b", src)
    assert not re.search(r'"device_token"\s*:\s*"[A-Za-z0-9._\-]{8,}"', src)
    assert not re.search(r'"registration_code"\s*:\s*"[A-Za-z0-9._\-]{8,}"',
                          src)


# ── 5) Tray 메뉴 ──────────────────────────────────────────


def test_tray_menu_has_seven_items():
    src = Path("local_agent/gui_tray.py").read_text(encoding="utf-8")
    for item in ("열기", "Chat 열기", "상태 보기", "진단 보기",
                  "AI 설정", "재등록", "종료"):
        assert item in src, f"tray missing: {item}"


# ── 6) Wizard 유지 ────────────────────────────────────────


def test_wizard_open_method_exists():
    from local_agent.gui_app import HaehanAgentGuiApp
    assert hasattr(HaehanAgentGuiApp, "open_wizard")


def test_wizard_step_keywords_in_source():
    src = Path("local_agent/gui_app.py").read_text(encoding="utf-8")
    assert "Step 1 of 3" in src
    assert "Step 2 of 3" in src
    assert "Step 3 of 3" in src


# ── 7) AI Settings modal placeholder ──────────────────────


def test_ai_settings_modal_three_modes_in_source():
    src = Path("local_agent/gui_app.py").read_text(encoding="utf-8")
    assert "MODE_DEV_TEST_KEY" in src
    assert "MODE_SERVER_PROXY" in src
    assert "MODE_USER_BYOK" in src


def test_ai_settings_modal_buttons_disabled_placeholder():
    src = Path("local_agent/gui_app.py").read_text(encoding="utf-8")
    # disabled 상태 명시
    assert 'state="disabled"' in src


def test_ai_settings_modal_states_no_real_save():
    """AI Settings modal 상태 안내 — 직전 공정 placeholder 또는
    본 공정 Developer Test Key 활성 둘 다 허용."""
    src = Path("local_agent/gui_app.py").read_text(encoding="utf-8")
    # placeholder/Dev Test 두 가지 표현 중 하나 이상
    has_placeholder_note = ("placeholder" in src.lower()
                              or "UI 만" in src)
    has_dev_mode_note = "Developer Test Key" in src
    assert has_placeholder_note or has_dev_mode_note


# ── 8) Chat 입력 / Shift+Enter ────────────────────────────


def test_chat_input_binds_enter_and_shift_enter():
    src = Path("local_agent/gui_app.py").read_text(encoding="utf-8")
    assert '"<Return>"' in src
    assert '"<Shift-Return>"' in src


# ── 9) [X] 닫기 → 트레이 ────────────────────────────────


def test_x_close_minimizes_to_tray():
    src = Path("local_agent/gui_app.py").read_text(encoding="utf-8")
    assert "WM_DELETE_WINDOW" in src
    assert "on_minimize_to_tray" in src


# ── 10) Diagnostics 복사 redact ──────────────────────────


def test_diagnostics_copy_uses_redact():
    src = Path("local_agent/gui_app.py").read_text(encoding="utf-8")
    # on_copy_diagnostics 안에서 redact_input 호출
    assert "on_copy_diagnostics" in src
    # 직전 라인 또는 함수 안에 redact_input 사용
    import re
    m = re.search(r"def on_copy_diagnostics.*?def ",
                   src, re.DOTALL)
    block = m.group(0) if m else src
    assert "redact_input" in block


# ── 11) audit verdict ────────────────────────────────────


def test_audit_warn_ai_not_connected():
    from scripts.ops import audit_agent_gui_chat_ui_implementation as a
    v = a.judge_gui_chat_ui(cli_regression_ok=True,
                              desktop_ui_unchanged=True)
    assert v.code in ("PASS_AGENT_GUI_CHAT_UI_IMPLEMENTATION",
                       "WARN_AI_API_NOT_CONNECTED")


def test_audit_fail_desktop_ui_touched():
    from scripts.ops import audit_agent_gui_chat_ui_implementation as a
    v = a.judge_gui_chat_ui(desktop_ui_unchanged=False)
    assert v.code == "FAIL_DESKTOP_UI_TOUCHED"


def test_audit_fail_cli_regression():
    from scripts.ops import audit_agent_gui_chat_ui_implementation as a
    v = a.judge_gui_chat_ui(cli_regression_ok=False)
    assert v.code == "FAIL_CLI_REGRESSION"


# ── 12) CLI 회귀 가드 ────────────────────────────────────


def test_regression_desktop_launcher_intact():
    from local_agent import desktop_launcher
    for sym in ("main", "self_test", "register_flow", "connect_flow"):
        assert hasattr(desktop_launcher, sym)


def test_regression_cli_self_test_runs():
    from local_agent import desktop_launcher
    r = desktop_launcher.self_test()
    assert r["ok"] is True


def test_regression_gui_state_unchanged():
    from local_agent import gui_state as gs
    assert hasattr(gs, "GuiController")
    assert hasattr(gs, "transition")


def test_regression_ai_chat_models_unchanged():
    from local_agent import ai_chat_models as M
    assert hasattr(M, "ChatMessage")
    assert hasattr(M, "ChatProviderConfig")


def test_regression_connection_diagnostics_unchanged():
    from local_agent import connection_diagnostics as cd
    assert hasattr(cd, "render_user_block")
    assert hasattr(cd, "normalize_ws_url")

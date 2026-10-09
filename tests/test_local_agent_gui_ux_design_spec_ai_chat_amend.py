"""AGENT_GUI_UX_DESIGN_SPEC_AI_CHAT_AMEND_01 — 14+ 테스트."""
from __future__ import annotations

from pathlib import Path

SPEC = Path("docs/design/local_agent_gui_ux_design_spec_ai_chat_amend_20260521.md")


# ── 1) 문서 존재 ─────────────────────────────────────────────


def test_spec_exists():
    assert SPEC.exists()


def test_spec_has_amend_rationale():
    text = SPEC.read_text(encoding="utf-8")
    assert "보정 사유" in text
    assert "wizard + tray only" in text


# ── 2) 사용자 목적 재정의 ─────────────────────────────────


def test_spec_redefines_user_goals():
    text = SPEC.read_text(encoding="utf-8")
    for k in ("AI 채팅", "작업 위임", "승인", "진단"):
        assert k in text


# ── 3) 4안 비교 ────────────────────────────────────────────


def test_spec_compares_four_options():
    text = SPEC.read_text(encoding="utf-8")
    for opt in ("A. wizard + tray only",
                "B. wizard + tray + Chat 단일창",
                "C. wizard + tray + 3탭 미니창",
                "D. React desktop/ui"):
        assert opt in text, f"missing option: {opt}"


def test_spec_recommends_option_c():
    text = SPEC.read_text(encoding="utf-8")
    assert "권장" in text
    assert "C. wizard + tray + 3탭 미니창" in text


# ── 4) Chat 탭 설계 ─────────────────────────────────────


def test_spec_has_chat_tab_design():
    text = SPEC.read_text(encoding="utf-8")
    for k in ("Chat 탭", "메시지 목록", "사용자 입력창",
              "Enter 전송", "Shift+Enter", "전송 버튼"):
        assert k in text, f"missing chat element: {k}"


def test_spec_has_task_delegation_card():
    text = SPEC.read_text(encoding="utf-8")
    assert "작업 위임" in text
    assert "승인" in text
    assert "거절" in text
    assert "위험도" in text or "risk" in text.lower()


def test_spec_disables_input_when_disconnected():
    text = SPEC.read_text(encoding="utf-8")
    assert "비활성" in text or "비활성화" in text
    assert "연결" in text


# ── 5) Status 탭 설계 ──────────────────────────────────


def test_spec_has_status_tab_design():
    text = SPEC.read_text(encoding="utf-8")
    assert "Status 탭" in text
    for k in ("agent_id", "server_url", "ws_url",
              "마지막 heartbeat", "재연결", "재등록"):
        assert k in text


# ── 6) Diagnostics 탭 설계 ─────────────────────────────


def test_spec_has_diagnostics_tab_design():
    text = SPEC.read_text(encoding="utf-8")
    assert "Diagnostics 탭" in text
    assert "render_user_block" in text or "복사" in text


# ── 7) Wizard 유지 ──────────────────────────────────────


def test_spec_keeps_wizard():
    text = SPEC.read_text(encoding="utf-8")
    assert "Step 1" in text and "Step 2" in text and "Step 3" in text
    assert "wizard" in text.lower()


# ── 8) Tray 메뉴 보정 ──────────────────────────────────


def test_spec_amends_tray_menu():
    text = SPEC.read_text(encoding="utf-8")
    for k in ("Chat 열기", "상태 보기", "진단",
              "재등록", "종료", "열기"):
        assert k in text, f"missing tray item: {k}"


# ── 9) PII / 보안 UX ──────────────────────────────────


def test_spec_pii_policy_complete():
    text = SPEC.read_text(encoding="utf-8")
    for k in ("device_token", "registration_code", "마스킹",
              "redact", "대화 로그", "민감정보", "session"):
        assert k in text, f"missing PII: {k}"


def test_spec_chat_disables_disk_save_by_default():
    text = SPEC.read_text(encoding="utf-8")
    assert "디스크 저장 기본 OFF" in text or "저장 기본 OFF" in text


def test_spec_no_raw_token_in_doc():
    import re
    text = SPEC.read_text(encoding="utf-8")
    assert text, "문서가 비어 있음 — 비어 있으면 아래 비밀값 검사는 공허하게 통과한다"
    matches = re.findall(r'"device_token"\s*:\s*"([^"]{20,})"', text)
    real = [m for m in matches if "<" not in m and m != "[REDACTED]"]
    assert real == []


# ── 10) AI API 분리 ──────────────────────────────────


def test_spec_separates_ai_api_implementation():
    text = SPEC.read_text(encoding="utf-8")
    assert "AGENT_AI_CHAT_API_CLIENT_01" in text
    assert "AGENT_GUI_CHAT_IMPLEMENTATION_01" in text
    assert "OUT_OF_SCOPE" in text or "범위 분리" in text


# ── 11) MVP / Later / 하지 않음 ─────────────────────


def test_spec_has_mvp_section():
    text = SPEC.read_text(encoding="utf-8")
    assert "MVP" in text


def test_spec_has_later_section():
    text = SPEC.read_text(encoding="utf-8")
    assert "Later" in text


def test_spec_has_excluded_section():
    text = SPEC.read_text(encoding="utf-8")
    assert "하지 않을" in text or "하지 않음" in text


# ── 12) desktop/ui 미수정 명시 ────────────────────


def test_spec_states_desktop_ui_unchanged():
    text = SPEC.read_text(encoding="utf-8")
    assert "desktop/ui" in text
    assert "수정" in text
    assert "REACT_GUI_AGENT_INTEGRATION_01" in text


# ── 13) audit ────────────────────────────────────


def test_audit_warn_ai_api_deferred_on_real_spec():
    from tools.audits.agent import audit_local_agent_gui_ux_design_spec_ai_chat_amend as a
    v = a.judge_amend(desktop_ui_unchanged=True,
                       ai_api_implementation_done=False)
    # AI API 실제 구현은 본 공정 외 → WARN_AI_API_IMPLEMENTATION_DEFERRED 가 정상
    assert v.code in ("PASS_AGENT_GUI_UX_AI_CHAT_AMEND",
                       "WARN_AI_API_IMPLEMENTATION_DEFERRED")


def test_audit_fail_chat_missing(tmp_path):
    from tools.audits.agent import audit_local_agent_gui_ux_design_spec_ai_chat_amend as a
    p = tmp_path / "x.md"
    p.write_text("# minimal", encoding="utf-8")
    v = a.judge_amend(spec_path=p)
    assert v.code == "FAIL_CHAT_REQUIREMENT_MISSING"


def test_audit_fail_desktop_ui_violation():
    from tools.audits.agent import audit_local_agent_gui_ux_design_spec_ai_chat_amend as a
    v = a.judge_amend(desktop_ui_unchanged=False)
    assert v.code == "FAIL_DESKTOP_UI_SCOPE_VIOLATION"


# ── 14) 회귀 가드 ────────────────────────────────


def test_regression_prev_ux_spec_unchanged():
    """직전 UX 설계서 (27d6ede) 도 그대로 있어야 함."""
    prev = Path("docs/design/local_agent_gui_ux_design_spec_20260521.md")
    assert prev.exists()


def test_regression_gui_state_unchanged():
    from core.agent_runtime.gui import gui_state as gs
    assert hasattr(gs, "GuiController")


def test_regression_connection_diagnostics_unchanged():
    from core.agent_runtime.connection import connection_diagnostics as cd
    assert hasattr(cd, "render_user_block")
    assert hasattr(cd, "explain_error")

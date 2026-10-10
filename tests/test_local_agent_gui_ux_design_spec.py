"""AGENT_GUI_UX_DESIGN_SPEC_01 — 12+ 테스트."""

from __future__ import annotations

from pathlib import Path

SPEC = Path("docs/design/local_agent_gui_ux_design_spec_20260521.md")


# ── 1) 문서 존재 ────────────────────────────────────────────


def test_spec_exists():
    assert SPEC.exists()


def test_spec_is_not_empty():
    text = SPEC.read_text(encoding="utf-8")
    assert len(text) > 5000  # 충분한 분량 (수백 줄)


# ── 2) 사용자 유형 정의 ─────────────────────────────────────


def test_spec_defines_personas():
    text = SPEC.read_text(encoding="utf-8")
    assert "Persona A" in text
    assert "Persona B" in text
    assert "일반 사용자" in text
    assert "운영자" in text


# ── 3) 핵심 사용자 흐름 ────────────────────────────────────


def test_spec_has_user_flows():
    text = SPEC.read_text(encoding="utf-8")
    for k in (
        "첫 실행",
        "등록코드",
        "wss 자동 연결",
        "재실행",
        "재등록",
        "인증 실패",
        "서버 접속 실패",
        "진단",
        "종료",
    ):
        assert k in text, f"missing flow: {k}"


# ── 4) 4개 GUI 구조안 비교 ─────────────────────────────────


def test_spec_compares_four_options():
    text = SPEC.read_text(encoding="utf-8")
    for opt in ("A. 현재 4탭", "B. 트레이 중심", "C. 단일 창 2탭", "D. 첫 등록 wizard"):
        assert opt in text, f"missing option: {opt}"


# ── 5) 최종 권장안 ─────────────────────────────────────────


def test_spec_states_final_recommendation():
    text = SPEC.read_text(encoding="utf-8")
    assert "권장 = " in text
    # 권장은 B / C / D 중 하나여야 함 (A 는 over-engineering 평가됨)
    assert any(
        rec in text
        for rec in (
            "권장 = **B",
            "권장 = **C",
            "권장 = **D",
        )
    )


# ── 6) 화면별 설계 ─────────────────────────────────────────


def test_spec_has_screen_designs():
    text = SPEC.read_text(encoding="utf-8")
    for screen in ("Step 1", "Step 2", "Step 3", "진단 다이얼로그", "재등록 확인", "트레이 메뉴"):
        assert screen in text, f"missing screen: {screen}"


def test_spec_wizard_has_3_steps():
    text = SPEC.read_text(encoding="utf-8")
    assert "Step 1 of 3" in text or "Step 1/3" in text or "Step 1" in text
    assert "Step 3 of 3" in text or "Step 3 of 3" in text


# ── 7) 오류 UX ────────────────────────────────────────────


def test_spec_covers_required_errors():
    text = SPEC.read_text(encoding="utf-8")
    for code in (
        "REG_CODE_EXPIRED",
        "REG_CODE_INVALID",
        "REG_CODE_ALREADY_USED",
        "AUTH_FAILED_4401",
        "TOKEN_NOT_STORED",
        "SERVER_NOT_REACHABLE",
        "NETWORK_BLOCKED_PROXY",
        "HEARTBEAT_LOST",
    ):
        assert code in text, f"missing error: {code}"


# ── 8) PII / 보안 UX ──────────────────────────────────────


def test_spec_pii_policy_explicit():
    text = SPEC.read_text(encoding="utf-8")
    for k in ("device_token", "registration_code", "agent_id", "마스킹", "redact", "show='●'"):
        assert k in text, f"missing PII rule: {k}"


def test_spec_no_real_secret_values():
    """문서 안에 실제 token / code raw 값이 없는지."""
    import re

    text = SPEC.read_text(encoding="utf-8")
    assert text, "문서가 비어 있음 — 비어 있으면 아래 비밀값 검사는 공허하게 통과한다"
    matches = re.findall(r'"device_token"\s*:\s*"([^"]{20,})"', text)
    real = [m for m in matches if "<" not in m and m != "[REDACTED]"]
    assert real == []


# ── 9) 탭/메뉴 결정 ───────────────────────────────────────


def test_spec_decides_remove_logs_tab():
    text = SPEC.read_text(encoding="utf-8")
    # Logs 탭 / Dashboard 탭 / Settings 탭 제거 의사 결정
    assert "Logs 탭" in text and "제거" in text


def test_spec_decides_keep_diagnostics_dialog():
    text = SPEC.read_text(encoding="utf-8")
    assert "다이얼로그" in text
    assert "트레이 메뉴" in text


# ── 10) 구현 우선순위 (MVP / Later / 하지 않음) ───────────


def test_spec_has_mvp_section():
    text = SPEC.read_text(encoding="utf-8")
    assert "MVP" in text


def test_spec_has_later_section():
    text = SPEC.read_text(encoding="utf-8")
    assert "Later" in text


def test_spec_has_excluded_section():
    text = SPEC.read_text(encoding="utf-8")
    assert "하지 않음" in text


# ── 11) 다음 공정명 ───────────────────────────────────────


def test_spec_proposes_next_implementation_process():
    text = SPEC.read_text(encoding="utf-8")
    assert "AGENT_GUI_SIMPLIFY_IMPLEMENTATION_01" in text


# ── 12) desktop/ui 미수정 ────────────────────────────────


def test_spec_states_desktop_ui_unchanged():
    text = SPEC.read_text(encoding="utf-8")
    assert "desktop/ui" in text
    assert "수정" in text  # 수정 안 함 명시
    assert "REACT_GUI_AGENT_INTEGRATION_01" in text


# ── 13) audit ─────────────────────────────────────────────


def test_audit_pass_on_real_spec():
    from tools.audits.agent import audit_local_agent_gui_ux_design_spec as a

    v = a.judge_spec(desktop_ui_unchanged=True)
    assert v.code == "PASS_AGENT_GUI_UX_DESIGN_SPEC", v.reasons


def test_audit_fail_user_flow_missing(tmp_path):
    from tools.audits.agent import audit_local_agent_gui_ux_design_spec as a

    p = tmp_path / "minimal.md"
    p.write_text("# Spec\n내용 짧음", encoding="utf-8")
    v = a.judge_spec(spec_path=p)
    assert v.code == "FAIL_USER_FLOW_MISSING"


def test_audit_fail_desktop_ui_violation():
    from tools.audits.agent import audit_local_agent_gui_ux_design_spec as a

    v = a.judge_spec(desktop_ui_unchanged=False)
    assert v.code == "FAIL_DESKTOP_UI_SCOPE_VIOLATION"


# ── 14) 회귀 가드 ────────────────────────────────────────


# test_regression_gui_impl_audit_unchanged 는 b13d1216("Electron 데스크톱·로컬에이전트 GUI 삭제") 로 audit_local_agent_gui_implementation 모듈이 사라져 2026-10-05 제거


def test_regression_field_test_audit_unchanged():
    from tools.audits.agent import audit_local_agent_user_field_test as a

    assert hasattr(a, "judge_field_test")


def test_regression_gui_state_unchanged():
    from core.agent_runtime.gui import gui_state as gs

    assert hasattr(gs, "GuiController")
    assert hasattr(gs, "transition")

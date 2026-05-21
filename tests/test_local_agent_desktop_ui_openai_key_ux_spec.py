"""AGENT_DESKTOP_UI_OPENAI_KEY_UX_SPEC_01 — 16+ 테스트."""
from __future__ import annotations

from pathlib import Path


SPEC = Path("docs/design/local_agent_desktop_ui_openai_key_ux_spec_20260521.md")


# ── 1) 문서 존재 ──────────────────────────────────────────


def test_spec_exists():
    assert SPEC.exists()


def test_spec_is_substantial():
    assert len(SPEC.read_text(encoding="utf-8")) > 8000


# ── 2) 기존 설계 검토 섹션 ───────────────────────────────


def test_spec_reviews_prior_designs():
    text = SPEC.read_text(encoding="utf-8")
    assert "local_agent_gui_ux_design_spec_20260521.md" in text
    assert "local_agent_gui_ux_design_spec_ai_chat_amend_20260521.md" in text
    assert "검토 결과" in text


# ── 3) OpenAI BYOK 결정 ──────────────────────────────────


def test_spec_defines_byok():
    text = SPEC.read_text(encoding="utf-8")
    assert "BYOK" in text
    assert "Bring Your Own Key" in text
    assert "Windows Credential Manager" in text


def test_spec_states_key_never_to_server():
    text = SPEC.read_text(encoding="utf-8")
    assert "서버로 전송되지 않" in text or "서버로 전송 0" in text


# ── 4) UI 구조 비교 ──────────────────────────────────────


def test_spec_compares_four_ui_options():
    text = SPEC.read_text(encoding="utf-8")
    for opt in ("A. 기존 3탭", "B. 4탭",
                "C. 3탭 유지 + Settings modal",
                "D. Wizard 에 OpenAI key"):
        assert opt in text, f"missing option: {opt}"


def test_spec_recommends_option_c():
    text = SPEC.read_text(encoding="utf-8")
    assert "권장" in text
    assert "3탭 + Settings modal" in text


# ── 5) API key Settings modal 설계 ──────────────────────


def test_spec_has_settings_modal_design():
    text = SPEC.read_text(encoding="utf-8")
    for k in ("AI Settings modal", "API key", "show='●'",
              "[ 저장 ]", "[ 연결 테스트 ]", "[ 교체 ]",
              "[ 삭제 ]", "Provider"):
        assert k in text, f"missing modal field: {k}"


def test_spec_states_no_key_reshow():
    text = SPEC.read_text(encoding="utf-8")
    assert "재표시 안 함" in text or "재표시 금지" in text
    assert "sk-****" in text  # fingerprint 표시 방식


def test_spec_disables_clipboard_for_key():
    text = SPEC.read_text(encoding="utf-8")
    assert "clipboard 복사 버튼" in text or "clipboard" in text.lower()


# ── 6) Chat 탭 설계 ─────────────────────────────────────


def test_spec_has_chat_tab_design():
    text = SPEC.read_text(encoding="utf-8")
    for k in ("Chat 탭", "AI 상태", "메시지", "입력",
              "전송", "Enter 전송", "AI 설정"):
        assert k in text


def test_spec_chat_input_disabled_when_no_key():
    text = SPEC.read_text(encoding="utf-8")
    assert "미설정" in text
    assert "비활성" in text


# ── 7) Status / Diagnostics 보강 ────────────────────────


def test_spec_status_tab_kept():
    text = SPEC.read_text(encoding="utf-8")
    assert "Status 탭" in text


def test_spec_diagnostics_includes_openai_fingerprint():
    text = SPEC.read_text(encoding="utf-8")
    assert "Diagnostics 탭" in text
    assert "fingerprint" in text


# ── 8) 오류 UX ──────────────────────────────────────────


def test_spec_covers_openai_error_codes():
    text = SPEC.read_text(encoding="utf-8")
    for code in ("API_KEY_NOT_SET", "API_KEY_INVALID",
                 "API_QUOTA_EXCEEDED", "RATE_LIMITED",
                 "NETWORK_ERROR", "MODEL_NOT_AVAILABLE",
                 "REQUEST_TIMEOUT", "PROVIDER_ERROR"):
        assert code in text, f"missing error code: {code}"


# ── 9) 보안 / PII UX ────────────────────────────────────


def test_spec_security_policy_complete():
    text = SPEC.read_text(encoding="utf-8")
    for k in ("device_token", "registration_code", "OpenAI",
              "Credential Manager", "마스킹", "redact",
              "평문 fallback", "기본 OFF"):
        assert k in text, f"missing security: {k}"


def test_spec_forbids_chatgpt_web_automation():
    text = SPEC.read_text(encoding="utf-8")
    assert "ChatGPT 웹 자동화" in text
    # 금지 표현 동반
    import re
    m = re.search(r"ChatGPT 웹 자동화.{0,80}(❌|금지|하지 않)",
                   text, re.DOTALL)
    assert m, "ChatGPT 웹 자동화 금지 표현 부정확"


def test_spec_no_raw_api_key_in_doc():
    """문서에 실제 OpenAI key 형태가 들어가지 않았는지."""
    import re
    text = SPEC.read_text(encoding="utf-8")
    matches = re.findall(r"\bsk-[A-Za-z0-9]{20,}\b", text)
    # 정규식 패턴 [A-Za-z 같은 건 OK, 실제 raw 값처럼 보이는 건 NG
    real = [m for m in matches if "[A-Za-z" not in m]
    assert real == [], f"raw key in doc: {real}"


# ── 10) MVP / Later / 하지 않음 ────────────────────────


def test_spec_has_mvp_section():
    text = SPEC.read_text(encoding="utf-8")
    assert "MVP" in text


def test_spec_has_later_section():
    text = SPEC.read_text(encoding="utf-8")
    assert "Later" in text


def test_spec_has_excluded_section():
    text = SPEC.read_text(encoding="utf-8")
    assert "하지 않" in text


def test_spec_proxy_mode_in_later():
    text = SPEC.read_text(encoding="utf-8")
    assert "AGENT_OPENAI_PROXY_MODE_01" in text or "회사 proxy" in text


# ── 11) 다음 공정명 ─────────────────────────────────────


def test_spec_proposes_next_processes_3():
    text = SPEC.read_text(encoding="utf-8")
    for proc in ("AGENT_OPENAI_BYOK_KEY_STORE_01",
                  "AGENT_OPENAI_CHAT_CLIENT_01",
                  "AGENT_GUI_CHAT_IMPLEMENTATION_01"):
        assert proc in text, f"missing next process: {proc}"


# ── 12) desktop/ui 미수정 명시 ─────────────────────────


def test_spec_states_desktop_ui_unchanged():
    text = SPEC.read_text(encoding="utf-8")
    assert "desktop/ui" in text
    assert "수정" in text
    assert "REACT_GUI_AGENT_INTEGRATION_01" in text


# ── 13) audit ───────────────────────────────────────────


def test_audit_warn_proxy_deferred_on_real_spec():
    from scripts.ops import audit_local_agent_desktop_ui_openai_key_ux_spec as a
    v = a.judge_spec(desktop_ui_unchanged=True,
                      proxy_mode_implemented=False)
    assert v.code in ("PASS_DESKTOP_UI_OPENAI_KEY_UX_SPEC",
                       "WARN_PROXY_MODE_DEFERRED")


def test_audit_fail_openai_key_ux_missing(tmp_path):
    from scripts.ops import audit_local_agent_desktop_ui_openai_key_ux_spec as a
    p = tmp_path / "x.md"
    p.write_text("# minimal", encoding="utf-8")
    v = a.judge_spec(spec_path=p)
    assert v.code == "FAIL_OPENAI_KEY_UX_MISSING"


def test_audit_fail_desktop_ui_violation():
    from scripts.ops import audit_local_agent_desktop_ui_openai_key_ux_spec as a
    v = a.judge_spec(desktop_ui_unchanged=False)
    assert v.code == "FAIL_DESKTOP_UI_SCOPE_VIOLATION"


# ── 14) 회귀 가드 ──────────────────────────────────────


def test_regression_ai_chat_amend_unchanged():
    p = Path("docs/design/local_agent_gui_ux_design_spec_ai_chat_amend_20260521.md")
    assert p.exists()


def test_regression_ai_chat_client_module_unchanged():
    from local_agent import ai_chat_client
    assert hasattr(ai_chat_client, "MockAiChatClient")
    assert hasattr(ai_chat_client, "redact_input")


def test_regression_ai_chat_models_unchanged():
    from local_agent import ai_chat_models as M
    assert hasattr(M, "ChatProviderConfig")
    assert hasattr(M, "ChatMessage")

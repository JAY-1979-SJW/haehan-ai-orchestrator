"""AGENT_AI_CHAT_API_CLIENT_01 — 18+ 테스트."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from local_agent import ai_chat_models as M
from local_agent import ai_chat_client as C


# ── 1) ChatMessage / ChatRequest / ChatResponse schema ──────────


def test_chat_message_schema():
    m = M.ChatMessage(message_id="m1", role=M.ROLE_USER,
                       text_redacted="hi")
    d = m.to_dict()
    assert d["message_id"] == "m1"
    assert d["role"] == "user"
    assert d["text_redacted"] == "hi"
    assert d["status"] == M.STATUS_COMPLETED


def test_chat_request_has_no_raw_text_field():
    cr = M.ChatRequest(request_id="r", session_id="s",
                        text_redacted="hello")
    fields = set(cr.__dataclass_fields__.keys())
    # 절대 있으면 안 되는 필드
    assert "text_raw" not in fields
    assert "raw_text" not in fields
    assert "original" not in fields
    # text_redacted 만 존재
    assert "text_redacted" in fields


def test_chat_response_external_call_count_zero():
    msg = M.ChatMessage(message_id="m1", role=M.ROLE_ASSISTANT,
                         text_redacted="ok")
    r = M.ChatResponse(request_id="r", message=msg)
    assert r.external_call_count == 0


# ── 2) Provider config — api_key 필드 부재 ─────────────────


def test_provider_config_has_no_api_key_field():
    cfg = M.ChatProviderConfig()
    fields = set(cfg.__dataclass_fields__.keys())
    assert "api_key" not in fields
    assert "secret" not in fields
    # api_key_source 만 (env / keyring / server_proxy) 보유
    assert "api_key_source" in fields


def test_provider_config_defaults_to_mock():
    cfg = M.ChatProviderConfig()
    assert cfg.provider == "mock"
    assert cfg.enabled is True


# ── 3) Mock send_message deterministic ─────────────────────


def test_mock_send_status_keyword():
    c = C.MockAiChatClient()
    req = M.ChatRequest(request_id=M.new_request_id(),
                         session_id=M.new_session_id(),
                         text_redacted="상태 알려줘")
    r = c.send_message(req)
    assert r.external_call_count == 0
    assert "Status" in r.message.text_redacted


def test_mock_send_default_reply():
    c = C.MockAiChatClient()
    req = M.ChatRequest(request_id="r1", session_id="s1",
                         text_redacted="안녕하세요")
    r = c.send_message(req)
    assert "도와드릴" in r.message.text_redacted


def test_mock_send_empty_raises():
    c = C.MockAiChatClient()
    req = M.ChatRequest(request_id="r1", session_id="s1",
                         text_redacted="")
    with pytest.raises(C._ChatException) as exc:
        c.send_message(req)
    assert exc.value.err.code == M.ERR_EMPTY_MESSAGE


def test_mock_send_too_long_raises():
    c = C.MockAiChatClient()
    req = M.ChatRequest(request_id="r1", session_id="s1",
                         text_redacted="x" * (M.MAX_INPUT_CHARS + 1))
    with pytest.raises(C._ChatException) as exc:
        c.send_message(req)
    assert exc.value.err.code == M.ERR_INPUT_TOO_LONG


def test_mock_send_provider_disabled():
    cfg = M.ChatProviderConfig(enabled=False)
    c = C.MockAiChatClient(provider_config=cfg)
    req = M.ChatRequest(request_id="r1", session_id="s1",
                         text_redacted="hello")
    with pytest.raises(C._ChatException) as exc:
        c.send_message(req)
    assert exc.value.err.code == M.ERR_PROVIDER_DISABLED


# ── 4) stream 이벤트 순서 ──────────────────────────────────


def test_mock_stream_yields_delta_then_end():
    c = C.MockAiChatClient()
    req = M.ChatRequest(request_id="r1", session_id="s1",
                         text_redacted="안녕")
    events = list(c.stream_message(req))
    kinds = [e.event for e in events]
    assert "delta" in kinds
    assert kinds[-1] == "end"


def test_mock_stream_empty_yields_error():
    c = C.MockAiChatClient()
    req = M.ChatRequest(request_id="r1", session_id="s1",
                         text_redacted="")
    events = list(c.stream_message(req))
    assert events[0].event == "error"
    assert events[0].error.code == M.ERR_EMPTY_MESSAGE


# ── 5) cancel ──────────────────────────────────────────────


def test_cancel_sets_request_cancelled():
    c = C.MockAiChatClient()
    rid = "r-cancel"
    c.cancel(request_id=rid)
    req = M.ChatRequest(request_id=rid, session_id="s",
                         text_redacted="hello")
    with pytest.raises(C._ChatException) as exc:
        c.send_message(req)
    assert exc.value.err.code == M.ERR_REQUEST_CANCELLED


# ── 6) Redaction ───────────────────────────────────────────


def test_redact_openai_api_key():
    r = C.redact_input("OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz123456")
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in r


def test_redact_anthropic_api_key():
    r = C.redact_input("token: sk-ant-abc1234567890defghijklmnop12345")
    assert "sk-ant-abc1234567890defghijklmnop12345" not in r


def test_redact_device_token_kv():
    r = C.redact_input("device_token=ABCDEFGH12345678")
    assert "ABCDEFGH12345678" not in r


def test_redact_bearer_token():
    r = C.redact_input("Authorization: Bearer abc123def456ghi789jklmno")
    assert "abc123def456ghi789jklmno" not in r


def test_redact_rrn():
    r = C.redact_input("주민번호 901231-1234567 입니다")
    assert "901231-1234567" not in r


def test_redact_phone():
    r = C.redact_input("연락처 010-1234-5678 입니다")
    assert "010-1234-5678" not in r


def test_redact_email():
    r = C.redact_input("contact me at user@example.com")
    assert "user@example.com" not in r


def test_has_pii_warning_true_when_redacted():
    raw = "device_token=SECRETLONG12345678"
    red = C.redact_input(raw)
    assert C.has_pii_warning(raw, red) is True


def test_has_pii_warning_false_when_clean():
    raw = "안녕하세요. 오늘 일정 알려주세요."
    red = C.redact_input(raw)
    assert C.has_pii_warning(raw, red) is False


# ── 7) make_request_from_user_input ───────────────────────


def test_make_request_redacts_and_flags_pii():
    req, pii = C.make_request_from_user_input(
        session_id="s1",
        raw_input="device_token=ABCDEFGH12345678 hi",
    )
    assert pii is True
    assert "ABCDEFGH12345678" not in req.text_redacted
    assert req.session_id == "s1"


def test_make_request_clean_input_no_pii():
    req, pii = C.make_request_from_user_input(
        session_id="s1", raw_input="안녕",
    )
    assert pii is False
    assert "안녕" in req.text_redacted


# ── 8) TaskDelegationCard — 메타만, 실행 0 ────────────────


def test_task_delegation_keyword_returns_card_no_execution():
    c = C.MockAiChatClient()
    req = M.ChatRequest(request_id="r1", session_id="s1",
                         text_redacted="파일 삭제 해줘")
    r = c.send_message(req)
    assert r.message.local_task_candidate is True
    assert r.message.task_card is not None
    assert r.message.task_card.risk == "high"


def test_task_delegation_medium_risk_keyword():
    c = C.MockAiChatClient()
    req = M.ChatRequest(request_id="r1", session_id="s1",
                         text_redacted="pip install requests")
    r = c.send_message(req)
    assert r.message.local_task_candidate is True
    assert r.message.task_card.risk in ("medium", "high")


def test_normal_keyword_no_task_card():
    c = C.MockAiChatClient()
    req = M.ChatRequest(request_id="r1", session_id="s1",
                         text_redacted="오늘 날씨 어때?")
    r = c.send_message(req)
    assert r.message.local_task_candidate is False
    assert r.message.task_card is None


def test_task_delegation_card_built_via_helper():
    card = M.build_task_delegation_card(
        kind="read_doc", risk="low",
        summary_kr="문서 읽기 요청", scope_kr="로컬 파일 1개",
    )
    assert card.card_id.startswith("card-")
    assert card.risk == "low"


# ── 9) Session state ──────────────────────────────────────


def test_create_default_chat_session():
    s = M.create_default_chat_session()
    assert s.session_id.startswith("ses-")
    assert s.provider.provider == "mock"
    assert s.messages == []
    assert s.external_call_count == 0


def test_session_append_user_and_assistant():
    s = M.create_default_chat_session()
    M.append_user_message(s, text_redacted="hi", pii_redacted=False)
    M.append_assistant_message(s, text_redacted="hello")
    assert len(s.messages) == 2
    assert s.messages[0].role == M.ROLE_USER
    assert s.messages[1].role == M.ROLE_ASSISTANT


# ── 10) format_stream_event_for_gui ──────────────────────


def test_format_stream_event_delta():
    ev = M.ChatStreamEvent(event="delta", request_id="r", session_id="s",
                            delta_text_redacted="hello")
    d = M.format_stream_event_for_gui(ev)
    assert d["event"] == "delta"
    assert d["delta"] == "hello"


def test_format_stream_event_with_card():
    card = M.build_task_delegation_card(kind="x", risk="low",
                                          summary_kr="요약",
                                          scope_kr="범위")
    ev = M.ChatStreamEvent(event="task_card", request_id="r",
                            session_id="s", task_card=card)
    d = M.format_stream_event_for_gui(ev)
    assert d["task_card"]["risk"] == "low"


# ── 11) Source 정적 분석 — 외부 호출 패턴 부재 ────────────


def test_source_no_external_ai_call():
    src = Path("local_agent/ai_chat_client.py").read_text(encoding="utf-8")
    low = src.lower()
    for pat in ("openai", "anthropic", "https://api.",
                "urllib.request.urlopen", "requests.post"):
        assert pat not in low, f"forbidden pattern: {pat}"


def test_source_no_dangerous_execution():
    src = Path("local_agent/ai_chat_client.py").read_text(encoding="utf-8")
    for pat in ("subprocess.run", "subprocess.Popen", "os.system",
                "os.unlink", "os.remove", "shutil.rmtree"):
        assert pat not in src, f"dangerous call: {pat}"


def test_source_no_chat_history_file_write():
    src = Path("local_agent/ai_chat_client.py").read_text(encoding="utf-8")
    # 파일 저장 함수 호출 없음
    assert ".write_text" not in src
    assert "open(" not in src or "open(__" in src  # __file__ 같은 건 OK


# ── 12) audit ────────────────────────────────────────────


def test_audit_returns_warn_or_pass():
    from scripts.ops import audit_agent_ai_chat_api_client as a
    v = a.judge_chat_client()
    # 외부 AI 미구현은 의도 → WARN 정상
    assert v.code in ("PASS_AGENT_AI_CHAT_API_CLIENT",
                       "WARN_EXTERNAL_AI_NOT_IMPLEMENTED")


# ── 13) 회귀 가드 ────────────────────────────────────────


def test_regression_gui_state_unchanged():
    from local_agent import gui_state as gs
    assert hasattr(gs, "GuiController")


def test_regression_connection_diagnostics_unchanged():
    from local_agent import connection_diagnostics as cd
    assert hasattr(cd, "explain_error")


def test_regression_token_store_unchanged():
    from local_agent import token_store as ts
    assert hasattr(ts, "save_device_token")

"""AGENT_AI_CHAT_API_CLIENT_01 audit."""
from __future__ import annotations

import importlib
import inspect
import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ClientVerdict:
    passed: bool
    code: str
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


_FORBIDDEN_NET_PATTERNS = (
    "openai", "anthropic", "https://api.", "http://api.",
    "urllib.request.urlopen", "requests.post", "httpx.post",
    "websockets.connect",
)

REQUIRED_MODELS = ("ChatMessage", "ChatRequest", "ChatResponse",
                   "ChatError", "ChatSessionState",
                   "ChatProviderConfig", "ChatStreamEvent",
                   "TaskDelegationCard")
REQUIRED_HELPERS = ("create_default_chat_session", "append_user_message",
                    "append_assistant_message",
                    "build_task_delegation_card",
                    "format_stream_event_for_gui",
                    "new_message_id", "new_session_id", "new_request_id")
REQUIRED_ERRORS = ("EMPTY_MESSAGE", "INPUT_TOO_LONG", "PII_INPUT_WARNING",
                   "PROVIDER_DISABLED", "PROVIDER_UNAVAILABLE",
                   "REQUEST_CANCELLED", "RATE_LIMITED", "NETWORK_ERROR",
                   "API_KEY_NOT_CONFIGURED", "TASK_DELEGATION_REQUIRED")


def _resolve(mod: str, sym: str):
    try:
        m = importlib.import_module(mod)
        return getattr(m, sym, None)
    except Exception:
        return None


def judge_chat_client() -> ClientVerdict:
    metrics: dict = {}

    # FAIL_CHAT_PROTOCOL_BROKEN — 모델/심볼 존재
    for sym in REQUIRED_MODELS:
        if _resolve("local_agent.ai_chat_models", sym) is None:
            return ClientVerdict(False, "FAIL_CHAT_PROTOCOL_BROKEN",
                                 reasons=[f"missing model: {sym}"],
                                 metrics=metrics)
    for sym in REQUIRED_HELPERS:
        if _resolve("local_agent.ai_chat_models", sym) is None:
            return ClientVerdict(False, "FAIL_CHAT_PROTOCOL_BROKEN",
                                 reasons=[f"missing helper: {sym}"],
                                 metrics=metrics)

    M = importlib.import_module("local_agent.ai_chat_models")
    for code in REQUIRED_ERRORS:
        attr = f"ERR_{code}"
        if not hasattr(M, attr):
            return ClientVerdict(False, "FAIL_CHAT_PROTOCOL_BROKEN",
                                 reasons=[f"missing error: {attr}"],
                                 metrics=metrics)

    # client
    if _resolve("local_agent.ai_chat_client", "AiChatClient") is None:
        return ClientVerdict(False, "FAIL_CHAT_PROTOCOL_BROKEN",
                             reasons=["AiChatClient protocol missing"],
                             metrics=metrics)
    if _resolve("local_agent.ai_chat_client", "MockAiChatClient") is None:
        return ClientVerdict(False, "FAIL_CHAT_PROTOCOL_BROKEN",
                             reasons=["MockAiChatClient missing"],
                             metrics=metrics)

    # FAIL_EXTERNAL_AI_CALLED — 소스 정적 분석
    src_files = (Path("local_agent/ai_chat_client.py"),
                 Path("local_agent/ai_chat_models.py"))
    for f in src_files:
        text = f.read_text(encoding="utf-8")
        for pat in _FORBIDDEN_NET_PATTERNS:
            if pat in text.lower():
                return ClientVerdict(False, "FAIL_EXTERNAL_AI_CALLED",
                                     reasons=[f"forbidden pattern '{pat}' in {f}"],
                                     metrics=metrics)

    # FAIL_REDACTION_BROKEN — redact 동작 검증
    from local_agent.ai_chat_client import redact_input, has_pii_warning
    for raw, key in (
        ("OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz123456 hello",
         "sk-abcdefghijklmnopqrstuvwxyz123456"),
        ("device_token=ABCDEFGH12345678 text",
         "ABCDEFGH12345678"),
        ("Authorization: Bearer abc123def456ghi789jklmno test",
         "abc123def456ghi789jklmno"),
        ("내 주민번호 901231-1234567 입니다",
         "901231-1234567"),
        ("연락처 010-1234-5678",
         "010-1234-5678"),
        ("email me at user@example.com please",
         "user@example.com"),
    ):
        r = redact_input(raw)
        if key in r:
            return ClientVerdict(False, "FAIL_REDACTION_BROKEN",
                                 reasons=[f"value survived: {key[:20]}..."],
                                 metrics=metrics)
        if not has_pii_warning(raw, r):
            return ClientVerdict(False, "FAIL_REDACTION_BROKEN",
                                 reasons=[f"has_pii_warning False for: {raw[:30]}"],
                                 metrics=metrics)

    # FAIL_RAW_INPUT_STORED — ChatRequest 에 raw 필드 부재
    cr = M.ChatRequest(request_id="r", session_id="s",
                        text_redacted="hello")
    fields = set(cr.__dataclass_fields__.keys())
    if "text_raw" in fields or "raw_text" in fields or "original" in fields:
        return ClientVerdict(False, "FAIL_RAW_INPUT_STORED",
                             reasons=["ChatRequest has raw text field"],
                             metrics=metrics)

    # FAIL_API_KEY_LEAK — ChatProviderConfig 에 api_key 값 필드 없음
    cfg = M.ChatProviderConfig()
    cfg_fields = set(cfg.__dataclass_fields__.keys())
    if "api_key" in cfg_fields or "secret" in cfg_fields:
        return ClientVerdict(False, "FAIL_API_KEY_LEAK",
                             reasons=["ChatProviderConfig holds api_key directly"],
                             metrics=metrics)

    # FAIL_TASK_EXECUTED_UNSAFELY — 위임 카드 받고 실제 실행하는 코드 없음
    src_client = src_files[0].read_text(encoding="utf-8")
    for danger in ("subprocess.run", "subprocess.Popen", "os.system",
                    "os.unlink", "os.remove", "shutil.rmtree",
                    "Path.unlink", "send_message_to_server"):
        if danger in src_client:
            return ClientVerdict(False, "FAIL_TASK_EXECUTED_UNSAFELY",
                                 reasons=[f"dangerous call '{danger}' in client"],
                                 metrics=metrics)

    # Mock 행동 검증 — external_call_count 항상 0
    from local_agent.ai_chat_client import MockAiChatClient
    c = MockAiChatClient()
    req = M.ChatRequest(request_id="r-1", session_id="s-1",
                         text_redacted="안녕")
    resp = c.send_message(req)
    if resp.external_call_count != 0:
        return ClientVerdict(False, "FAIL_EXTERNAL_AI_CALLED",
                             reasons=["external_call_count != 0"],
                             metrics=metrics)

    metrics["external_call_count"] = 0
    metrics["models_present"] = len(REQUIRED_MODELS)
    metrics["error_codes_present"] = len(REQUIRED_ERRORS)

    # WARN — 실제 외부 AI 구현 안 됨 (의도된 OUT_OF_SCOPE)
    return ClientVerdict(False, "WARN_EXTERNAL_AI_NOT_IMPLEMENTED",
                         reasons=["mock only — actual external AI provider 미구현 (의도)"],
                         metrics=metrics)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    args = ap.parse_args(argv)
    v = judge_chat_client()
    print(json.dumps({"verdict": v.code, "passed": v.passed,
                      "reasons": v.reasons, "metrics": v.metrics},
                     ensure_ascii=False, indent=2))
    return 0 if v.passed else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())

"""AI Chat adapter placeholder.

본 모듈은 GUI 가 AI 응답을 받는 경로를 추상화한다.
이번 공정에서는 실제 OpenAI 호출 / API key 저장 0.
NotConfigured 응답만 반환한다. 다음 공정에서 실제 어댑터 (OpenAI / Server Proxy /
BYOK) 가 동일 인터페이스로 교체된다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from . import ai_chat_client as _aic
from . import gui_chat_state as _cs


@dataclass
class AdapterResponse:
    """adapter 응답 — text_redacted only."""
    text_redacted: str
    is_task_card: bool = False
    task_card_text: str = ""
    ok: bool = True
    error_code: str = ""           # AI_NOT_CONFIGURED / ... (UI 가 매핑)
    external_call_count: int = 0   # placeholder 단계 항상 0


class AiChatAdapter(Protocol):
    def is_configured(self) -> bool: ...

    def send_message(self, *, text_raw: str) -> AdapterResponse: ...

    def validate_message(self, text: str) -> tuple[bool, str]: ...

    def detect_sensitive_input(self, text: str) -> bool: ...


# ── placeholder 구현 (현재 공정 default) ────────────────────────


class PlaceholderAdapter:
    """실제 AI 호출 없음. NotConfigured 응답만."""

    def __init__(self):
        self.external_call_count = 0    # 영구히 0

    def is_configured(self) -> bool:
        return False

    def validate_message(self, text: str) -> tuple[bool, str]:
        if not text or not text.strip():
            return (False, "메시지가 비어 있습니다.")
        if len(text) > 8000:
            return (False, "입력이 너무 깁니다.")
        return (True, "")

    def detect_sensitive_input(self, text: str) -> bool:
        if not text:
            return False
        redacted = _aic.redact_input(text)
        return _aic.has_pii_warning(text, redacted)

    def send_message(self, *, text_raw: str) -> AdapterResponse:
        """실제 호출 없이 NotConfigured 응답.

        text_raw 는 함수 scope 안에서만 사용, redact 후 즉시 폐기.
        """
        ok, reason = self.validate_message(text_raw)
        if not ok:
            return AdapterResponse(
                text_redacted="", ok=False,
                error_code="EMPTY_OR_TOO_LONG",
                external_call_count=0,
            )
        # raw input 은 화면 표시 없이 redact 만 (검증용)
        _ = _aic.redact_input(text_raw)
        text_raw = ""  # 즉시 폐기
        # placeholder 응답
        return AdapterResponse(
            text_redacted=build_not_configured_response_text(),
            ok=True,
            error_code="",
            external_call_count=0,
        )


def build_not_configured_response_text() -> str:
    """AI 미설정 상태에서의 placeholder 응답 문구."""
    return (
        "AI 연결은 아직 설정되지 않았습니다.\n"
        "오른쪽 위 [⚙ AI 설정] 에서 연결 방식을 설정하세요. "
        "(이번 공정은 UI 만 구현되었으며, 실제 AI 호출은 다음 공정에서 활성화됩니다.)"
    )


# ── factory ────────────────────────────────────────────────────


class OpenAiDirectTestAdapter:
    """Developer Test Mode adapter — 실 OpenAI 호출.

    key 미설정 → API_KEY_NOT_SET error
    key 있음 → openai_chat_client.OpenAiDirectTestClient 위임
    """

    def __init__(self):
        from . import openai_chat_client as _occ
        self._client = _occ.OpenAiDirectTestClient()
        self._occ = _occ

    def is_configured(self) -> bool:
        return self._client.is_configured()

    def validate_message(self, text: str) -> tuple[bool, str]:
        if not text or not text.strip():
            return (False, "메시지가 비어 있습니다.")
        if len(text) > 8000:
            return (False, "입력이 너무 깁니다.")
        return (True, "")

    def detect_sensitive_input(self, text: str) -> bool:
        if not text:
            return False
        red = _aic.redact_input(text)
        return _aic.has_pii_warning(text, red)

    def send_message(self, *, text_raw: str) -> AdapterResponse:
        ok, _ = self.validate_message(text_raw)
        if not ok:
            return AdapterResponse(
                text_redacted="", ok=False,
                error_code="EMPTY_OR_TOO_LONG", external_call_count=0,
            )
        if not self.is_configured():
            return AdapterResponse(
                text_redacted="", ok=False,
                error_code=self._occ.ERR_API_KEY_NOT_SET,
                external_call_count=0,
            )
        req = self._occ.OpenAiChatRequest(text=text_raw)
        text_raw = ""  # 폐기
        resp = self._client.chat(req)
        return AdapterResponse(
            text_redacted=resp.text_redacted,
            ok=resp.ok,
            error_code=resp.error_code,
            external_call_count=resp.external_call_count,
        )


class ServerProxyChatAdapter:
    """상용 기본 모드 — 데스크앱 → 서버 proxy → OpenAI.

    사용자 PC 에 OpenAI key 없음.
    agent_id + device_token 은 controller / token_store 에서 자동 로드.
    """

    def __init__(self, *, server_url: str = "",
                  agent_id: str = ""):
        from . import server_proxy_chat_client as _spc
        self._spc = _spc
        # ctor 인자 비어 있으면 launcher 가 set_agent_id 로 갱신
        self.server_url = server_url or "https://haehan-ai.kr/orchestrator"
        self.agent_id = agent_id
        self._client = _spc.ServerProxyChatClient(
            server_url=self.server_url, agent_id=self.agent_id)

    def set_context(self, *, server_url: str, agent_id: str) -> None:
        self.server_url = server_url
        self.agent_id = agent_id
        self._client = self._spc.ServerProxyChatClient(
            server_url=server_url, agent_id=agent_id)

    def is_configured(self) -> bool:
        return self._client.is_configured()

    def validate_message(self, text: str) -> tuple[bool, str]:
        if not text or not text.strip():
            return (False, "메시지가 비어 있습니다.")
        if len(text) > 8000:
            return (False, "입력이 너무 깁니다.")
        return (True, "")

    def detect_sensitive_input(self, text: str) -> bool:
        if not text:
            return False
        red = _aic.redact_input(text)
        return _aic.has_pii_warning(text, red)

    def send_message(self, *, text_raw: str) -> AdapterResponse:
        ok, _ = self.validate_message(text_raw)
        if not ok:
            return AdapterResponse(
                text_redacted="", ok=False,
                error_code="EMPTY_OR_TOO_LONG", external_call_count=0,
            )
        if not self.is_configured():
            return AdapterResponse(
                text_redacted="", ok=False,
                error_code=self._spc.ERR_DEVICE_TOKEN_MISSING,
                external_call_count=0,
            )
        resp = self._client.chat(text_raw)
        text_raw = ""  # 폐기
        return AdapterResponse(
            text_redacted=resp.text_redacted,
            ok=resp.ok,
            error_code=resp.error_code,
            external_call_count=resp.external_call_count,
        )


def make_default_adapter(*, mode: str = _cs.MODE_SERVER_PROXY,
                          server_url: str = "",
                          agent_id: str = "",
                          ) -> "AiChatAdapter":
    """mode 별 adapter 분기.

    - SERVER_PROXY (상용 기본) → ServerProxyChatAdapter (서버 경유)
    - DEV_TEST_KEY → OpenAiDirectTestAdapter (실 OpenAI 직접 호출)
    - USER_BYOK → PlaceholderAdapter (이번 공정 OUT_OF_SCOPE)
    """
    if mode == _cs.MODE_DEV_TEST_KEY:
        return OpenAiDirectTestAdapter()
    if mode == _cs.MODE_SERVER_PROXY:
        return ServerProxyChatAdapter(server_url=server_url,
                                        agent_id=agent_id)
    return PlaceholderAdapter()

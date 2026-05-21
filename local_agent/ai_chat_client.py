"""AI Chat client 계약 + Mock 구현.

본 모듈은 외부 AI API 를 호출하지 않는다 (mock only).
- 입력은 redact 후 모델에 전달
- 원문은 함수 scope 안에서만, 즉시 폐기
- 디스크 저장 / chat history file 생성 0
- task 실제 실행 0 (위임 카드 메타만 반환)
"""
from __future__ import annotations

import re
from typing import Iterator, Protocol

from . import ai_chat_models as M
from . import gui_log_buffer as _lb  # redact 재사용


# ── redaction 규칙 (chat 전용 추가) ─────────────────────────────

# 추가 패턴: 주민번호 / 전화번호 / 이메일 / 일반 API key 형식
_PATTERNS_EXTRA = [
    # 주민번호 (000000-0000000 또는 0000000000000)
    (re.compile(r"\b\d{6}-\d{7}\b"), "[REDACTED_RRN]"),
    # 전화번호 (010-1234-5678 / 010 1234 5678 / 01012345678 / +82-10-...)
    (re.compile(r"\b(?:\+?82-?)?0?1[016789][-\s]?\d{3,4}[-\s]?\d{4}\b"),
     "[REDACTED_PHONE]"),
    # 이메일
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
     "[REDACTED_EMAIL]"),
    # sk-* 형태 (provider 무관 일반 API key 패턴)
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), "[REDACTED_API_KEY]"),
    # sk-ant-* 형태 (특정 provider key 패턴)
    (re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"), "[REDACTED_API_KEY]"),
    # 일반 long secret-ish 토큰 (40자 이상 base64/url-safe)
    (re.compile(r"\b[A-Za-z0-9_-]{40,}\b"), "[REDACTED_TOKEN]"),
]


def redact_input(text: str) -> str:
    """user 입력 / AI 응답 모두 통과시키는 redaction."""
    if not text:
        return text
    # 1차: gui_log_buffer.redact (device_token / Authorization 등 KV/JSON)
    out = _lb.redact(text)
    # 2차: 본 모듈 추가 패턴
    for pat, repl in _PATTERNS_EXTRA:
        out = pat.sub(repl, out)
    return out


def has_pii_warning(original: str, redacted: str) -> bool:
    """원문이 redact 결과와 다르면 PII 감지된 것."""
    return bool(original) and original != redacted


# ── 위임 카드 후보 키워드 ──────────────────────────────────────

_TASK_DELEGATION_TRIGGERS = (
    "파일 삭제", "delete file", "rm ", "remove file",
    "명령 실행", "execute", "shell",
    "권한 변경", "chmod",
    "포트 열기", "방화벽",
    "패키지 설치", "pip install", "npm install",
    "데이터베이스", "drop table",
    "전송", "send email", "이메일 보내",
)

_TASK_HIGH_RISK = ("파일 삭제", "rm ", "remove file", "delete file",
                    "drop table", "chmod")


def _detect_task_candidate(text_redacted: str
                            ) -> M.TaskDelegationCard | None:
    """입력에 위임 후보 키워드가 있으면 카드 메타 생성 (실제 실행 0)."""
    low = (text_redacted or "").lower()
    matched: str | None = None
    for kw in _TASK_DELEGATION_TRIGGERS:
        if kw in low:
            matched = kw
            break
    if not matched:
        return None
    risk = "high" if any(h in low for h in _TASK_HIGH_RISK) else "medium"
    return M.build_task_delegation_card(
        kind="generic_local_task",
        risk=risk,
        summary_kr=f"사용자 입력에 위임 후보가 감지됨: '{matched}'",
        scope_kr="로컬 파일/실행/네트워크 — 사용자 승인 필요",
    )


# ── client protocol ─────────────────────────────────────────────


class AiChatClient(Protocol):
    """UI 가 의존하는 인터페이스."""

    provider_config: M.ChatProviderConfig

    def send_message(self, request: M.ChatRequest
                      ) -> M.ChatResponse: ...

    def stream_message(self, request: M.ChatRequest
                        ) -> Iterator[M.ChatStreamEvent]: ...

    def cancel(self, *, request_id: str = "",
                session_id: str = "") -> bool: ...

    def health_check(self) -> bool: ...

    def build_error(self, code: str, message_kr: str = "",
                     *, request_id: str = "",
                     session_id: str = "") -> M.ChatError: ...


# ── Mock client 구현 ────────────────────────────────────────────


class MockAiChatClient:
    """deterministic mock — 외부 호출 0.

    응답 규칙:
      "상태" / "연결" 키워드 → Status 탭 안내 응답
      "진단" 키워드 → Diagnostics 탭 안내
      "등록" / "재등록" 키워드 → Registration 안내
      그 외 → "이해했습니다. 추가로 도와드릴 게 있을까요?" + echo summary
      위임 후보 키워드 → TaskDelegationCard 포함
      입력 비어 있음 → EMPTY_MESSAGE
      입력 길이 초과 → INPUT_TOO_LONG
      PII 감지 → PII_INPUT_WARNING (응답은 정상 진행, warning event 발화)
    """

    def __init__(self, *, provider_config: M.ChatProviderConfig | None = None):
        self.provider_config = provider_config or M.ChatProviderConfig(
            provider="mock", model="mock-1", enabled=True,
        )
        self._cancelled_requests: set[str] = set()

    # ── core helpers ────────────────────────────────────────────

    def health_check(self) -> bool:
        return self.provider_config.enabled

    def build_error(self, code: str, message_kr: str = "",
                     *, request_id: str = "",
                     session_id: str = "") -> M.ChatError:
        if not message_kr:
            message_kr = _DEFAULT_ERROR_KR.get(code, "알 수 없는 오류")
        return M.ChatError(code=code, message_kr=message_kr,
                            request_id=request_id, session_id=session_id)

    def cancel(self, *, request_id: str = "",
                session_id: str = "") -> bool:
        if request_id:
            self._cancelled_requests.add(request_id)
            return True
        return False

    # ── send (non-streaming) ───────────────────────────────────

    def send_message(self, request: M.ChatRequest) -> M.ChatResponse:
        # request.text_redacted 가 이미 redact 적용된 상태라 가정
        text = request.text_redacted or ""
        if not text.strip():
            raise _ChatException(self.build_error(
                M.ERR_EMPTY_MESSAGE, "메시지가 비어 있습니다.",
                request_id=request.request_id, session_id=request.session_id,
            ))
        if len(text) > M.MAX_INPUT_CHARS:
            raise _ChatException(self.build_error(
                M.ERR_INPUT_TOO_LONG, "입력이 너무 깁니다.",
                request_id=request.request_id, session_id=request.session_id,
            ))
        if not self.provider_config.enabled:
            raise _ChatException(self.build_error(
                M.ERR_PROVIDER_DISABLED, "AI provider 가 비활성화됨.",
                request_id=request.request_id, session_id=request.session_id,
            ))
        if request.request_id in self._cancelled_requests:
            raise _ChatException(self.build_error(
                M.ERR_REQUEST_CANCELLED,
                request_id=request.request_id,
                session_id=request.session_id,
            ))

        reply_text, card = self._mock_reply(text)
        msg = M.ChatMessage(
            message_id=M.new_message_id(),
            role=M.ROLE_ASSISTANT,
            text_redacted=reply_text,
            status=M.STATUS_COMPLETED,
            local_task_candidate=card is not None,
            task_card=card,
        )
        return M.ChatResponse(
            request_id=request.request_id, message=msg,
            finish_reason="stop", external_call_count=0,
        )

    # ── stream ─────────────────────────────────────────────────

    def stream_message(self, request: M.ChatRequest
                        ) -> Iterator[M.ChatStreamEvent]:
        text = request.text_redacted or ""
        sid = request.session_id
        rid = request.request_id
        if not text.strip():
            yield M.ChatStreamEvent(
                event="error", request_id=rid, session_id=sid,
                error=self.build_error(M.ERR_EMPTY_MESSAGE,
                                        request_id=rid, session_id=sid),
            )
            return
        if len(text) > M.MAX_INPUT_CHARS:
            yield M.ChatStreamEvent(
                event="error", request_id=rid, session_id=sid,
                error=self.build_error(M.ERR_INPUT_TOO_LONG,
                                        request_id=rid, session_id=sid),
            )
            return

        reply_text, card = self._mock_reply(text)
        # PII warning (redact 표시 마커가 있으면)
        if "[REDACTED" in text:
            yield M.ChatStreamEvent(
                event="warning", request_id=rid, session_id=sid,
                error=self.build_error(M.ERR_PII_INPUT_WARNING,
                                        request_id=rid, session_id=sid),
            )

        # delta 를 단어 단위로 쪼개 전송 (deterministic)
        words = reply_text.split()
        for w in words:
            if rid in self._cancelled_requests:
                yield M.ChatStreamEvent(
                    event="error", request_id=rid, session_id=sid,
                    error=self.build_error(M.ERR_REQUEST_CANCELLED,
                                            request_id=rid, session_id=sid),
                )
                return
            yield M.ChatStreamEvent(
                event="delta", request_id=rid, session_id=sid,
                delta_text_redacted=w + " ",
            )

        if card is not None:
            yield M.ChatStreamEvent(
                event="task_card", request_id=rid, session_id=sid,
                task_card=card,
            )

        yield M.ChatStreamEvent(event="end", request_id=rid, session_id=sid)

    # ── mock 응답 로직 ─────────────────────────────────────────

    def _mock_reply(self, text_redacted: str
                     ) -> tuple[str, M.TaskDelegationCard | None]:
        low = text_redacted.lower()
        # 1순위: 위임 후보 키워드
        card = _detect_task_candidate(text_redacted)
        if card is not None:
            return ("아래 작업을 진행하려면 승인이 필요합니다. "
                     "내용을 확인 후 [승인] 또는 [거절] 을 눌러주세요.",
                     card)
        if "상태" in low or "연결" in low:
            return ("현재 연결 상태는 Status 탭에서 확인할 수 있습니다.",
                     None)
        if "진단" in low:
            return ("진단 정보는 Diagnostics 탭에서 볼 수 있습니다. "
                     "오류가 표시되면 권장 조치를 따라 주세요.", None)
        if "재등록" in low or "등록" in low:
            return ("재등록은 트레이 메뉴 또는 Diagnostics 탭에서 가능합니다. "
                     "관리자에게 새 등록코드를 요청하세요.", None)
        # 기본 응답
        return ("이해했습니다. 추가로 도와드릴 게 있을까요?", None)


class _ChatException(Exception):
    """내부 — error 객체 운반용."""

    def __init__(self, err: M.ChatError):
        super().__init__(err.code)
        self.err = err


# ── 기본 한글 오류 메시지 ──────────────────────────────────────

_DEFAULT_ERROR_KR = {
    M.ERR_EMPTY_MESSAGE: "메시지가 비어 있습니다.",
    M.ERR_INPUT_TOO_LONG: "입력이 너무 깁니다. (최대 {} 자)".format(
        M.MAX_INPUT_CHARS),
    M.ERR_PII_INPUT_WARNING: "민감정보가 포함된 것 같습니다. 그래도 전송하시겠어요?",
    M.ERR_PROVIDER_DISABLED: "AI provider 가 비활성화되어 있습니다.",
    M.ERR_PROVIDER_UNAVAILABLE: "AI 서비스에 일시적으로 접근할 수 없습니다.",
    M.ERR_REQUEST_CANCELLED: "요청이 취소되었습니다.",
    M.ERR_RATE_LIMITED: "요청이 너무 많습니다. 잠시 후 다시 시도하세요.",
    M.ERR_NETWORK_ERROR: "네트워크 오류가 발생했습니다.",
    M.ERR_API_KEY_NOT_CONFIGURED: "API key 가 설정되지 않았습니다.",
    M.ERR_TASK_DELEGATION_REQUIRED: "이 작업은 사용자 승인이 필요합니다.",
}


# ── helper: 사용자 입력을 안전하게 ChatRequest 로 변환 ────────────


def make_request_from_user_input(*, session_id: str,
                                   raw_input: str,
                                   stream: bool = True
                                   ) -> tuple[M.ChatRequest, bool]:
    """사용자 raw 입력 → redact → ChatRequest. (req, pii_detected)."""
    redacted = redact_input(raw_input)
    pii = has_pii_warning(raw_input, redacted)
    req = M.ChatRequest(
        request_id=M.new_request_id(),
        session_id=session_id,
        text_redacted=redacted,
        stream=stream,
    )
    # raw_input 변수는 호출자에서 즉시 폐기 권장
    return req, pii

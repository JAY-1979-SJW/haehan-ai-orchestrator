"""AI Chat 메시지/세션 모델 (계약).

본 모듈은 외부 AI API 호출을 하지 않는다.
ChatRequest 에는 원문 저장 금지 — ChatMessage.text_redacted 만 저장.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

KST = timezone(timedelta(hours=9))


# ── 역할 / 상태 enum ──────────────────────────────────────────────

ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
ROLE_SYSTEM = "system"
ROLE_TOOL = "tool"
ALL_ROLES = (ROLE_USER, ROLE_ASSISTANT, ROLE_SYSTEM, ROLE_TOOL)

STATUS_PENDING = "pending"
STATUS_STREAMING = "streaming"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"
ALL_STATUSES = (STATUS_PENDING, STATUS_STREAMING,
                STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED)


# ── 오류 코드 ──────────────────────────────────────────────────

ERR_EMPTY_MESSAGE = "EMPTY_MESSAGE"
ERR_INPUT_TOO_LONG = "INPUT_TOO_LONG"
ERR_PII_INPUT_WARNING = "PII_INPUT_WARNING"
ERR_PROVIDER_DISABLED = "PROVIDER_DISABLED"
ERR_PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
ERR_REQUEST_CANCELLED = "REQUEST_CANCELLED"
ERR_RATE_LIMITED = "RATE_LIMITED"
ERR_NETWORK_ERROR = "NETWORK_ERROR"
ERR_API_KEY_NOT_CONFIGURED = "API_KEY_NOT_CONFIGURED"
ERR_TASK_DELEGATION_REQUIRED = "TASK_DELEGATION_REQUIRED"

ALL_ERROR_CODES = (
    ERR_EMPTY_MESSAGE, ERR_INPUT_TOO_LONG, ERR_PII_INPUT_WARNING,
    ERR_PROVIDER_DISABLED, ERR_PROVIDER_UNAVAILABLE,
    ERR_REQUEST_CANCELLED, ERR_RATE_LIMITED, ERR_NETWORK_ERROR,
    ERR_API_KEY_NOT_CONFIGURED, ERR_TASK_DELEGATION_REQUIRED,
)


# ── 상수 ──────────────────────────────────────────────────────

MAX_INPUT_CHARS = 8000


def _now_iso() -> str:
    return datetime.now(KST).replace(microsecond=0).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


# ── 모델 ──────────────────────────────────────────────────────


@dataclass
class ChatMessage:
    """단일 메시지. raw 텍스트 저장 금지 — text_redacted 만 보유."""
    message_id: str
    role: str
    text_redacted: str
    created_at: str = field(default_factory=_now_iso)
    status: str = STATUS_COMPLETED
    pii_redacted: bool = False
    local_task_candidate: bool = False
    # 사용자 위험 카드 메타 (local_task_candidate=True 일 때만 채워짐)
    task_card: Optional["TaskDelegationCard"] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        # task_card 가 None 이면 그대로
        return d


@dataclass
class TaskDelegationCard:
    """AI 가 로컬에이전트에게 작업 위임을 요청하는 UI 카드 데이터."""
    card_id: str
    kind: str                # search_file / open_url / read_doc / ...
    risk: str                # "low" | "medium" | "high"
    summary_kr: str
    scope_kr: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ChatRequest:
    """사용자 요청 — 원문 저장 금지. text_redacted 만."""
    request_id: str
    session_id: str
    text_redacted: str
    max_tokens: int = 1024
    stream: bool = False


@dataclass
class ChatResponse:
    request_id: str
    message: ChatMessage
    finish_reason: str = "stop"   # stop / length / cancelled / error
    external_call_count: int = 0   # mock 은 항상 0


@dataclass
class ChatError:
    code: str
    message_kr: str
    request_id: str = ""
    session_id: str = ""


@dataclass
class ChatStreamEvent:
    """stream 응답의 한 조각."""
    event: str          # "delta" / "task_card" / "warning" / "end" / "error"
    request_id: str
    session_id: str
    delta_text_redacted: str = ""
    task_card: Optional[TaskDelegationCard] = None
    error: Optional[ChatError] = None


@dataclass
class ChatProviderConfig:
    provider: str = "mock"        # mock / provider_a / provider_b / local
    model: str = "mock-1"
    endpoint: str = ""
    api_key_source: str = "env"   # env / keyring / server_proxy
    enabled: bool = True

    def to_dict(self) -> dict:
        d = asdict(self)
        # api_key 값 자체는 어디서도 보유하지 않음 — source 만 표시
        return d


@dataclass
class ChatSessionState:
    session_id: str
    provider: ChatProviderConfig
    messages: list[ChatMessage] = field(default_factory=list)
    pending_message_id: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    external_call_count: int = 0
    pii_warning_count: int = 0
    cancelled_count: int = 0

    def append(self, msg: ChatMessage) -> None:
        self.messages.append(msg)
        self.updated_at = _now_iso()

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "provider": self.provider.to_dict(),
            "messages": [m.to_dict() for m in self.messages],
            "pending_message_id": self.pending_message_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "external_call_count": self.external_call_count,
            "pii_warning_count": self.pii_warning_count,
            "cancelled_count": self.cancelled_count,
        }


# ── factory helpers (GUI 가 쓰는 진입점) ─────────────────────────


def new_message_id() -> str:
    return _new_id("msg")


def new_session_id() -> str:
    return _new_id("ses")


def new_request_id() -> str:
    return _new_id("req")


def new_card_id() -> str:
    return _new_id("card")


def create_default_chat_session(provider: ChatProviderConfig | None = None
                                 ) -> ChatSessionState:
    return ChatSessionState(
        session_id=new_session_id(),
        provider=provider or ChatProviderConfig(),
    )


def append_user_message(session: ChatSessionState, *, text_redacted: str,
                         pii_redacted: bool) -> ChatMessage:
    msg = ChatMessage(
        message_id=new_message_id(),
        role=ROLE_USER,
        text_redacted=text_redacted,
        status=STATUS_COMPLETED,
        pii_redacted=pii_redacted,
    )
    session.append(msg)
    return msg


def append_assistant_message(session: ChatSessionState, *,
                              text_redacted: str,
                              status: str = STATUS_COMPLETED,
                              local_task_candidate: bool = False,
                              task_card: Optional[TaskDelegationCard] = None,
                              ) -> ChatMessage:
    msg = ChatMessage(
        message_id=new_message_id(),
        role=ROLE_ASSISTANT,
        text_redacted=text_redacted,
        status=status,
        local_task_candidate=local_task_candidate,
        task_card=task_card,
    )
    session.append(msg)
    return msg


def build_task_delegation_card(*, kind: str, risk: str,
                                summary_kr: str, scope_kr: str
                                ) -> TaskDelegationCard:
    assert risk in ("low", "medium", "high")
    return TaskDelegationCard(
        card_id=new_card_id(), kind=kind, risk=risk,
        summary_kr=summary_kr, scope_kr=scope_kr,
    )


def format_stream_event_for_gui(ev: ChatStreamEvent) -> dict:
    """GUI 가 바로 표시할 수 있는 dict 표현 (redacted 만)."""
    out: dict = {"event": ev.event, "request_id": ev.request_id,
                 "session_id": ev.session_id}
    if ev.delta_text_redacted:
        out["delta"] = ev.delta_text_redacted
    if ev.task_card:
        out["task_card"] = ev.task_card.to_dict()
    if ev.error:
        out["error"] = asdict(ev.error)
    return out

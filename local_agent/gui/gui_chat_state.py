"""Chat UI 상태 + AI mode enum.

본 모듈은 UI 표시용 상태만. 실제 AI 호출/key 저장 0.
"""

from __future__ import annotations

import contextlib
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


# ── AI mode (제공 방식) ────────────────────────────────────────

MODE_DEV_TEST_KEY = "DEVELOPER_TEST_KEY"
MODE_SERVER_PROXY = "PRODUCTION_SERVER_PROXY"
MODE_USER_BYOK = "USER_BYOK_ADVANCED"
ALL_MODES = (MODE_DEV_TEST_KEY, MODE_SERVER_PROXY, MODE_USER_BYOK)


def mode_label_kr(mode: str) -> str:
    return {
        MODE_DEV_TEST_KEY: "개발 테스트 키",
        MODE_SERVER_PROXY: "운영 서버 프록시",
        MODE_USER_BYOK: "BYOK (고급)",
    }.get(mode, mode)


# ── AI 연결 상태 ──────────────────────────────────────────────

AI_NOT_CONFIGURED = "AI_NOT_CONFIGURED"
AI_READY_PLACEHOLDER = "AI_READY_PLACEHOLDER"
AI_ERROR = "AI_ERROR"
ALL_AI_STATUSES = (AI_NOT_CONFIGURED, AI_READY_PLACEHOLDER, AI_ERROR)


def ai_status_label_kr(s: str) -> str:
    return {
        AI_NOT_CONFIGURED: "미설정",
        AI_READY_PLACEHOLDER: "준비됨 (placeholder)",
        AI_ERROR: "오류",
    }.get(s, s)


# ── 메시지 / 모델 ────────────────────────────────────────────


@dataclass
class ChatUiMessage:
    """화면 표시용 메시지 — redacted text만."""

    role: str  # user / assistant / system
    text_redacted: str
    created_at: str = ""
    is_task_card: bool = False
    task_card_text: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(KST).strftime("%H:%M:%S")


@dataclass
class AiModeState:
    mode: str = MODE_SERVER_PROXY  # 기본값 — UI placeholder
    model_kr: str = "(모델 미선택)"
    fingerprint: str = ""  # sk-****abcd 형태만 (placeholder 단계에선 빈문자열)
    last_test_iso: str = ""
    last_error_code: str = ""

    def to_safe_dict(self) -> dict:
        return {
            "mode": self.mode,
            "model": self.model_kr,
            "fingerprint": self.fingerprint or "—",
            "last_test": self.last_test_iso or "—",
            "last_error": self.last_error_code or "—",
        }


@dataclass
class ChatUiState:
    """Chat 탭 + AI Settings modal 의 공유 상태."""

    ai_status: str = AI_NOT_CONFIGURED
    ai_mode: AiModeState = field(default_factory=AiModeState)
    messages: list[ChatUiMessage] = field(default_factory=list)
    last_user_event: str = ""
    pii_warning_count: int = 0
    external_call_count: int = 0  # placeholder 단계는 항상 0


# ── thread-safe controller ────────────────────────────────────


class ChatUiController:
    """Chat UI 상태 컨트롤러 (lock + listeners)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._state = ChatUiState()
        self._listeners: list = []

    @property
    def state(self) -> ChatUiState:
        with self._lock:
            import dataclasses

            return dataclasses.replace(
                self._state, messages=list(self._state.messages), ai_mode=dataclasses.replace(self._state.ai_mode)
            )

    def append_message(self, msg: ChatUiMessage) -> None:
        with self._lock:
            self._state.messages.append(msg)
        self._notify()

    def set_ai_status(self, status: str, *, error_code: str = "") -> None:
        with self._lock:
            self._state.ai_status = status
            if error_code:
                self._state.ai_mode.last_error_code = error_code
        self._notify()

    def set_mode(self, mode: str) -> None:
        assert mode in ALL_MODES
        with self._lock:
            self._state.ai_mode.mode = mode
        self._notify()

    def set_fingerprint(self, fingerprint: str) -> None:
        with self._lock:
            self._state.ai_mode.fingerprint = fingerprint
        self._notify()

    def inc_pii_warning(self) -> None:
        with self._lock:
            self._state.pii_warning_count += 1
        self._notify()

    def subscribe(self, fn) -> None:
        self._listeners.append(fn)

    def _notify(self) -> None:
        snap = self.state
        for fn in list(self._listeners):
            # GUI 상태 변경 구독자 콜백 호출 실패를 무시 - UI 갱신 실패일 뿐 채팅 상태 데이터에는 영향 없음, best-effort 알림
            with contextlib.suppress(Exception):
                fn(snap)

    def clear_messages(self) -> None:
        with self._lock:
            self._state.messages.clear()
        self._notify()

"""GUI 상태 머신 — 순수 함수 (Tkinter/pystray 무관, 테스트 가능).

GUI 와 트레이가 공유하는 단일 진실 소스.
"""

from __future__ import annotations

import contextlib
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from core.agent_runtime.connection import connection_diagnostics as cd

KST = timezone(timedelta(hours=9))


# ── 상태 enum ───────────────────────────────────────────────────────

STATE_NOT_REGISTERED = cd.STATE_NOT_REGISTERED
STATE_CONNECTING = cd.STATE_CONNECTING
STATE_AUTHENTICATING = cd.STATE_AUTHENTICATING
STATE_CONNECTED = cd.STATE_CONNECTED
STATE_HEARTBEAT_OK = "HEARTBEAT_OK"
STATE_DISCONNECTED = cd.STATE_DISCONNECTED
STATE_AUTH_FAILED = cd.STATE_AUTH_FAILED
STATE_RECONNECTING = "RECONNECTING"
STATE_SERVER_UNREACHABLE = cd.STATE_SERVER_UNREACHABLE

ALL_STATES = (
    STATE_NOT_REGISTERED,
    STATE_CONNECTING,
    STATE_AUTHENTICATING,
    STATE_CONNECTED,
    STATE_HEARTBEAT_OK,
    STATE_DISCONNECTED,
    STATE_AUTH_FAILED,
    STATE_RECONNECTING,
    STATE_SERVER_UNREACHABLE,
)


# ── 데이터 ─────────────────────────────────────────────────────────


@dataclass
class GuiModel:
    """GUI 가 표시할 모든 정보. device_token 원문 보유 금지."""

    server_url: str = "https://haehan-ai.kr/orchestrator"
    agent_id: str = ""  # 풀 ID (저장만, 표시는 마스킹)
    state: str = STATE_NOT_REGISTERED
    last_heartbeat_iso: str = ""
    last_error_code: str = ""
    last_error_message_user: str = ""
    last_user_event: str = ""  # 등록 성공/실패 등 1회성 안내
    reconnect_count: int = 0

    @property
    def agent_id_masked(self) -> str:
        return cd.mask_agent_id(self.agent_id)

    def to_dict(self) -> dict:
        """직렬화 — token/secret 절대 미포함."""
        return {
            "server_url": cd._strip_secrets_from_url(self.server_url),
            "agent_id_masked": self.agent_id_masked,
            "state": self.state,
            "last_heartbeat_iso": self.last_heartbeat_iso,
            "last_error_code": self.last_error_code,
            "last_error_message_user": self.last_error_message_user,
            "last_user_event": self.last_user_event,
            "reconnect_count": self.reconnect_count,
        }


# ── 상태 머신 (전이 규칙) ───────────────────────────────────────

# (from_state, event) -> to_state
_TRANSITIONS = {
    (STATE_NOT_REGISTERED, "register_started"): STATE_CONNECTING,
    (STATE_NOT_REGISTERED, "register_success"): STATE_DISCONNECTED,
    (STATE_NOT_REGISTERED, "register_failed"): STATE_NOT_REGISTERED,
    (STATE_DISCONNECTED, "connect_start"): STATE_CONNECTING,
    (STATE_DISCONNECTED, "register_success"): STATE_DISCONNECTED,
    (STATE_DISCONNECTED, "reset_token"): STATE_NOT_REGISTERED,
    (STATE_CONNECTING, "ws_open"): STATE_AUTHENTICATING,
    (STATE_CONNECTING, "connect_failed"): STATE_SERVER_UNREACHABLE,
    (STATE_AUTHENTICATING, "auth_ok"): STATE_CONNECTED,
    (STATE_AUTHENTICATING, "auth_failed_4401"): STATE_AUTH_FAILED,
    (STATE_CONNECTED, "heartbeat_ack"): STATE_HEARTBEAT_OK,
    (STATE_CONNECTED, "ws_closed"): STATE_RECONNECTING,
    (STATE_HEARTBEAT_OK, "heartbeat_ack"): STATE_HEARTBEAT_OK,
    (STATE_HEARTBEAT_OK, "ws_closed"): STATE_RECONNECTING,
    (STATE_HEARTBEAT_OK, "heartbeat_lost"): STATE_RECONNECTING,
    (STATE_RECONNECTING, "ws_open"): STATE_AUTHENTICATING,
    (STATE_RECONNECTING, "auth_failed_4401"): STATE_AUTH_FAILED,
    (STATE_RECONNECTING, "connect_failed"): STATE_SERVER_UNREACHABLE,
    (STATE_AUTH_FAILED, "reset_token"): STATE_NOT_REGISTERED,
    (STATE_AUTH_FAILED, "register_success"): STATE_DISCONNECTED,
    (STATE_SERVER_UNREACHABLE, "ws_open"): STATE_AUTHENTICATING,
    (STATE_SERVER_UNREACHABLE, "connect_start"): STATE_CONNECTING,
    (STATE_SERVER_UNREACHABLE, "reset_token"): STATE_NOT_REGISTERED,
}


def transition(current: str, event: str) -> str:
    """현재 상태 + 이벤트 → 다음 상태. 알 수 없는 전이면 current 유지."""
    return _TRANSITIONS.get((current, event), current)


# ── 컨트롤러 (Tkinter from another thread 안전) ─────────────────


class GuiController:
    """thread-safe GUI 상태 컨트롤러.

    백그라운드 WS 스레드가 이벤트를 던지면 lock 안에서 model 업데이트.
    GUI 스레드는 polling 으로 model 을 읽어 표시한다.
    """

    def __init__(self, server_url: str = "https://haehan-ai.kr/orchestrator"):
        self._lock = threading.Lock()
        self._model = GuiModel(server_url=server_url)
        self._listeners: list = []

    @property
    def model(self) -> GuiModel:
        with self._lock:
            # snapshot copy (얕은) — caller 가 쓰기 안 함
            m = self._model
            import dataclasses

            return dataclasses.replace(m)

    def set_server_url(self, url: str) -> None:
        with self._lock:
            self._model.server_url = url
        self._notify()

    def set_agent_id(self, agent_id: str) -> None:
        with self._lock:
            self._model.agent_id = agent_id
        self._notify()

    def fire(self, event: str, *, error_code: str = "", user_event: str = "") -> None:
        """이벤트 발화 — 상태 머신에 따라 state 갱신."""
        with self._lock:
            new = transition(self._model.state, event)
            self._model.state = new
            if event == "heartbeat_ack":
                self._model.last_heartbeat_iso = datetime.now(KST).replace(microsecond=0).isoformat()
                self._model.last_error_code = ""
                self._model.last_error_message_user = ""
            if error_code:
                self._model.last_error_code = error_code
                self._model.last_error_message_user = cd.explain_error(error_code)
            if user_event:
                self._model.last_user_event = user_event
            if event in ("ws_closed", "connect_failed"):
                self._model.reconnect_count += 1
            if event == "register_success":
                self._model.reconnect_count = 0
            if event == "reset_token":
                self._model.agent_id = ""
                self._model.last_heartbeat_iso = ""
                self._model.last_error_code = ""
                self._model.last_error_message_user = ""
                self._model.last_user_event = "재등록 필요"
        self._notify()

    def subscribe(self, fn) -> None:
        self._listeners.append(fn)

    def _notify(self) -> None:
        snap = self.model
        for fn in self._listeners:
            # 구독자 콜백 실패가 다른 구독자 통지를 막지 않도록 격리(순수 상태 머신, UI 콜백 오류는 GUI 계층 책임)
            with contextlib.suppress(Exception):
                fn(snap)

    def render_user_block(self) -> str:
        m = self.model
        d = cd.build_diagnostics(
            server_base_url=m.server_url,
            agent_id=m.agent_id,
            state=m.state,
            last_heartbeat_iso=m.last_heartbeat_iso,
            last_error_code=m.last_error_code,
            reconnect_count=m.reconnect_count,
        )
        return cd.render_user_block(d)

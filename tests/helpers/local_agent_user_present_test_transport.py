"""
Local Agent User-Present Test Transport (in-memory)

실제 WebSocket 연결 없이 message contract와 adapter를 검증하기 위한
in-memory transport helper.

운영 WebSocket 서버에 연결하지 않는다.
실제 소켓 연결 코드 없음. 순수 in-memory 구현.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class InMemoryTestTransport:
    """
    in-memory send/receive 시뮬레이터.
    실제 WebSocket 연결 없음.
    """

    def __init__(self) -> None:
        self._sent: list[dict[str, Any]] = []
        self._received: list[dict[str, Any]] = []

    def send(self, message: dict[str, Any]) -> None:
        """서버 → 로컬 Agent 방향 메시지 전송 시뮬레이션."""
        self._sent.append(dict(message))

    def receive(self) -> dict[str, Any] | None:
        """로컬 Agent → 서버 방향 메시지 수신 시뮬레이션."""
        if self._received:
            return self._received.pop(0)
        return None

    def push_inbound(self, message: dict[str, Any]) -> None:
        """테스트에서 수신 큐에 메시지를 직접 삽입한다."""
        self._received.append(dict(message))

    def get_sent_messages(self) -> list[dict[str, Any]]:
        """전송된 모든 메시지 목록 반환 (copy)."""
        return [dict(m) for m in self._sent]

    def get_sent_by_type(self, message_type: str) -> list[dict[str, Any]]:
        """특정 message_type으로 전송된 메시지만 반환."""
        return [m for m in self._sent if m.get("message_type") == message_type]

    def clear(self) -> None:
        """테스트 전용: 전송/수신 큐 초기화."""
        self._sent.clear()
        self._received.clear()

    @property
    def sent_count(self) -> int:
        return len(self._sent)

    @property
    def received_count(self) -> int:
        return len(self._received)


def make_bank_task_payload(
    workflow_run_id: str = "wr_test_bank_001",
    tenant_id: str = "t1",
    user_id: str = "u1",
    site_id: str = "s_bank",
) -> dict[str, Any]:
    """은행 user-present task payload 기본값 생성 헬퍼."""
    return {
        "message_type": "USER_PRESENT_TASK",
        "workflow_run_id": workflow_run_id,
        "workflow_id": "w1",
        "tenant_id": tenant_id,
        "user_id": user_id,
        "site_id": site_id,
        "site_category": "bank",
        "target_domain": "kbstar.com",
        "target_url_redacted": "https://kbstar.com/***",
        "target_url_hash": "abc12345",
        "auth_method_label": "공동인증서/공인인증서",
        "user_message_ko": "은행 사이트 접속에 사용자 직접 인증이 필요합니다.",
        "required_user_actions": [
            "브라우저에서 직접 로그인/인증을 완료하세요.",
            "완료 후 UI에서 '인증 완료' 버튼을 클릭하세요.",
        ],
        "blocked_ai_actions": [
            "비밀번호 자동 입력 금지",
            "OTP 자동 입력 금지",
            "인증서 비밀번호 자동 입력 금지",
            "자동 클릭/폼 제출 금지",
        ],
        "safe_to_execute": False,
        "created_at": _now_iso(),
    }


def make_hometax_task_payload(
    workflow_run_id: str = "wr_test_hometax_001",
    tenant_id: str = "t1",
    user_id: str = "u1",
    site_id: str = "s_hometax",
) -> dict[str, Any]:
    """홈택스 user-present task payload 기본값 생성 헬퍼."""
    return {
        "message_type": "USER_PRESENT_TASK",
        "workflow_run_id": workflow_run_id,
        "workflow_id": "w1",
        "tenant_id": tenant_id,
        "user_id": user_id,
        "site_id": site_id,
        "site_category": "hometax",
        "target_domain": "hometax.go.kr",
        "target_url_redacted": "https://hometax.go.kr/***",
        "target_url_hash": "def67890",
        "auth_method_label": "공동인증서/공인인증서, 금융인증서",
        "user_message_ko": "홈택스 접속에 공동인증서/금융인증서 인증이 필요합니다.",
        "required_user_actions": [
            "공동인증서 또는 금융인증서로 직접 로그인하세요.",
            "완료 후 UI에서 '인증 완료' 버튼을 클릭하세요.",
        ],
        "blocked_ai_actions": [
            "인증서 비밀번호 자동 입력 금지",
            "OTP 자동 입력 금지",
        ],
        "safe_to_execute": False,
        "created_at": _now_iso(),
    }

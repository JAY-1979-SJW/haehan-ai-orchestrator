"""향후 액션 stub — 등록(implemented=False)되었으나 핸들러는 미연결.

prepare/execute 짝:
- bid.prepare_bid / bid.submit_with_user_approval
- esign.prepare_signature / esign.execute_with_user_approval

(browser.prepare_submit / browser.submit_with_user_approval는 2차 구현 완료)

핸들러 호출 시 NotImplementedError 발생 — 라우터/오케스트레이터가
명시적으로 미구현임을 인지할 수 있도록 한다.

action_registry.register_handler는 implemented=False인 액션의
핸들러 등록을 거부하므로, 이 모듈은 핸들러 등록 자체를 하지 않는다.
"""
from __future__ import annotations

from typing import Any

PENDING_ACTIONS = (
    "bid.prepare_bid",
    "bid.submit_with_user_approval",
    "esign.prepare_signature",
    "esign.execute_with_user_approval",
)


def stub_not_implemented(action_name: str, **kwargs: Any) -> dict[str, Any]:
    """라우터가 미구현 액션 호출 시 사용할 응답 생성기."""
    return {
        "ok": False,
        "verdict": "ACTION_NOT_IMPLEMENTED",
        "action_name": action_name,
        "message_ko": (
            f"액션 '{action_name}'은 등록만 됐고 실행 핸들러는 아직 구현되지 않았습니다. "
            "1차 구현 범위 외 — 향후 별도 작업으로 추가됩니다."
        ),
        "implemented": False,
        # 안전 필드
        "cookie_exported": False,
        "session_exported": False,
        "password_collected": False,
        "otp_collected": False,
        "certificate_password_collected": False,
        "storage_state_exported": False,
        "server_browser_used": False,
    }

"""web-tasks/run real_run 경로의 승인 생성 조립 계층.

책임:
  - token 발행 (approval.issue_token_for_dev_reg)
  - pending 레코드 생성 (dev_reg_approval.create_pending)
  - Telegram 승인 메시지 발송 (telegram_notifier + telegram_sender)
  - Telegram 발송 결과 mark (dev_reg_approval.mark_telegram_sent)

이 모듈은 얇은 조립 계층이다.
approval.py / dev_reg_approval.py / telegram_sender.py 의 책임을 이동하지 않는다.
응답 계약 (response key / status code / path) 은 web_task_router 모듈이 유지한다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ai_orchestrator.core import telegram_sender as _ts
from ai_orchestrator.dev_reg import dev_reg_approval as _dra
from ai_orchestrator.dev_reg.dev_reg_telegram import build_dev_reg_message
from tools.gates.approval import issue_token_for_dev_reg

logger = logging.getLogger(__name__)

_DEFAULT_TTL_MINUTES = 30


@dataclass
class PendingApprovalResult:
    """create_web_task_pending_approval() 반환값.

    응답 dict에 필요한 값만 노출한다.
    token 원문 / approval_token_hash / screenshot_path 는 포함하지 않는다.
    """

    task_id: str
    expires_at: str
    risk_level: str
    requires_approval: bool
    provider: str
    action_type: str
    telegram_sent: bool
    telegram_message_id: str


def create_web_task_pending_approval(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수, 인자 묶음 변경 시 API 영향)
    *,
    task_id: str,
    provider: str,
    action_type: str,
    risk_level: str,
    requires_approval: bool,
    summary: str,
    target_url: str,
    requested_by: str,
    actor_role: str,
    ttl_minutes: int = _DEFAULT_TTL_MINUTES,
) -> PendingApprovalResult:
    """web-tasks/run real_run 경로의 승인 생성 조립.

    1. issue_token_for_dev_reg() → ApprovalToken
    2. _dra.create_pending()     → DevRegApproval 레코드
    3. build_dev_reg_message()   → Telegram 메시지 조립
    4. _ts.send_message()        → Telegram 발송 (실패 시 skip, 응답 계약 유지)
    5. _dra.mark_telegram_sent() → 발송 결과 기록
    """
    # 1. 승인 토큰 발행
    token = issue_token_for_dev_reg(
        task_id=task_id,
        requested_by=requested_by,
        risk_level=risk_level,
        ttl_minutes=ttl_minutes,
    )

    # 2. pending 레코드 생성
    _dra.create_pending(
        task_id=task_id,
        token_id=token.token_id,
        provider=provider,
        action_type=action_type,
        risk_level=risk_level,
        summary=summary,
        target_url=target_url,
        screenshot_path="",
        requested_by=requested_by,
        expires_at=token.expires_at,
    )

    # 3. Telegram 메시지 조립 + 발송
    msg = build_dev_reg_message(
        task_id=task_id,
        provider=provider,
        action_type=action_type,
        summary=summary,
        risk_level=risk_level,
        target_url=target_url,
        expires_at=token.expires_at,
        token_id=token.token_id,
    )
    send_result = _ts.send_message(text=msg["text"], reply_markup=msg["reply_markup"])
    tg_sent = bool(send_result.get("ok"))
    tg_msg_id = str((send_result.get("result") or {}).get("message_id", ""))

    # 4. 발송 결과 mark
    _dra.mark_telegram_sent(task_id, message_id=tg_msg_id)

    return PendingApprovalResult(
        task_id=task_id,
        expires_at=token.expires_at,
        risk_level=risk_level,
        requires_approval=requires_approval,
        provider=provider,
        action_type=action_type,
        telegram_sent=tg_sent,
        telegram_message_id=tg_msg_id,
    )


__all__ = ["PendingApprovalResult", "create_web_task_pending_approval"]

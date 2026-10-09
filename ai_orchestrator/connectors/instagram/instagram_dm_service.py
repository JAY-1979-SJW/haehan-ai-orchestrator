"""Instagram 댓글 이벤트 처리 파이프라인 — webhook에서 저장된 이벤트를 rule engine에 태우고
Private Reply까지 보낸다. Webhook 응답 지연을 피하기 위해 FastAPI BackgroundTasks에서 호출된다.

Kill switch 3단계(지시문 §44): GLOBAL(INSTAGRAM_DM_ENABLED) -> ACCOUNT(automation_enabled) -> RULE(enabled).
셋 모두 켜져야 실제 발송. 하나라도 꺼져 있으면 BLOCKED로 기록하고 발송하지 않는다.

DRY RUN(지시문 §45): INSTAGRAM_DM_DRY_RUN=true 이면 실제 Meta API를 호출하지 않고
DRY_RUN 상태로 기록한다 (webhook/DB/matching은 그대로 수행).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Protocol

from ai_orchestrator.connectors.instagram import instagram_dm_db as db
from ai_orchestrator.connectors.instagram import instagram_dm_rule_engine as rule_engine
from ai_orchestrator.connectors.instagram import instagram_dm_token_store as token_store
from ai_orchestrator.connectors.instagram.instagram_graph_client import send_private_reply
from tools.gates.gate_core import is_opted_out

logger = logging.getLogger(__name__)


def _global_enabled() -> bool:
    return os.environ.get("INSTAGRAM_DM_ENABLED", "false").strip().lower() == "true"


def _dry_run() -> bool:
    return os.environ.get("INSTAGRAM_DM_DRY_RUN", "true").strip().lower() != "false"


class _AccountRow(Protocol):
    """계정 한 행 — dict 와 sqlite3.Row 가 모두 키로 값을 읽는다(sqlite3 를 import 하지 않고 타입만 표현)."""

    def __getitem__(self, key: str, /) -> Any: ...


def _blocked_reason(account: _AccountRow, rule: dict) -> str | None:
    """발송 차단 사유(전역/계정/룰 비활성). 차단 없으면 None."""
    if not _global_enabled():
        return "GLOBAL_DISABLED"
    if not account["automation_enabled"]:
        return "ACCOUNT_DISABLED"
    if not rule["enabled"]:
        return "RULE_DISABLED"
    return None


def process_comment_event(comment_event_id: str, *, instagram_account_id: str) -> None:
    account = db.get_account(instagram_account_id)
    if account is None:
        logger.warning("instagram_dm: account not found id=%s", instagram_account_id)
        return

    events = [e for e in db.list_comment_events(instagram_account_id, limit=500) if e["id"] == comment_event_id]
    event = events[0] if events else None
    if event is None:
        logger.warning("instagram_dm: comment event not found id=%s", comment_event_id)
        return

    rules = db.list_rules(instagram_account_id)
    result = rule_engine.evaluate(
        account_automation_enabled=bool(account["automation_enabled"]),
        comment_text=event["comment_text"],
        media_id=event["media_id"],
        rules=rules,
    )

    rule = result.rule
    if not result.matched or rule is None:  # rule 이 없으면 발송 경로로 진행하지 않는다(fail-closed)
        db.update_comment_event_status(
            comment_event_id, status="NO_MATCH" if result.reason == "NO_MATCH" else "IGNORED"
        )
        return

    db.update_comment_event_status(
        comment_event_id, status="MATCHED", matched_rule_id=rule["id"], matched_keyword=result.matched_keyword
    )

    message = rule_engine.render_template(
        rule["reply_message"], username=event["commenter_username"], keyword=result.matched_keyword
    )

    reply_log_id, reserved = db.try_reserve_reply_slot(
        instagram_account_id=instagram_account_id,
        comment_event_id=comment_event_id,
        comment_id=event["comment_id"],
        rule_id=rule["id"],
        request_message=message,
    )
    if not reserved:
        logger.info("instagram_dm: duplicate reply blocked comment_id=%s", event["comment_id"])
        return

    blocked_reason = _blocked_reason(account, rule)
    if blocked_reason:
        db.update_reply_result(reply_log_id, status="BLOCKED", blocked_reason=blocked_reason)
        return

    # 수신거부(광고성 DM 법적 의무) — 자동 실행 경로라 승인 문구는 받을 수 없고, 수신거부 대조만 한다.
    # 거부 목록 파일이 깨졌으면 보수적으로 보내지 않는다(is_opted_out 이 True).
    if is_opted_out(str(event["commenter_username"] or "")):
        db.update_reply_result(reply_log_id, status="BLOCKED", blocked_reason="OPTED_OUT")
        return

    if _dry_run():
        db.update_reply_result(reply_log_id, status="DRY_RUN")
        db.update_comment_event_status(
            comment_event_id, status="SENT", matched_rule_id=rule["id"], matched_keyword=result.matched_keyword
        )
        return

    token = token_store.load_token(account["instagram_user_id"])
    if not token:
        db.update_reply_result(reply_log_id, status="FAILED", blocked_reason="TOKEN_MISSING")
        db.set_account_status(instagram_account_id, "token_expired")
        return

    api_result = send_private_reply(account["instagram_user_id"], event["comment_id"], message, token)
    if api_result.success:
        db.update_reply_result(
            reply_log_id,
            status="SENT",
            meta_recipient_id=api_result.recipient_id,
            meta_message_id=api_result.message_id,
        )
        db.update_comment_event_status(
            comment_event_id, status="SENT", matched_rule_id=rule["id"], matched_keyword=result.matched_keyword
        )
    else:
        status = "UNKNOWN" if api_result.retryable else "FAILED"
        db.update_reply_result(
            reply_log_id,
            status=status,
            meta_error_code=str(api_result.error_code) if api_result.error_code is not None else None,
            meta_error_subcode=str(api_result.error_subcode) if api_result.error_subcode is not None else None,
            meta_error_message=api_result.error_message,
        )
        db.update_comment_event_status(comment_event_id, status="FAILED")

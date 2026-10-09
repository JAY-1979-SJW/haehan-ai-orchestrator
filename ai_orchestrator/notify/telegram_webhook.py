import json
import logging
from pathlib import Path

from ..audit.audit_logger import log_event
from tools.gates.approval import approve_token, reject_token
from ..tasks.inbox import create_inbox_item
from ..dev_reg.dev_reg_telegram import parse_dev_reg_callback_data
from .telegram_notifier import build_result_text, parse_callback_data

logger = logging.getLogger(__name__)

_USER_MAP_PATH = Path(__file__).resolve().parents[1] / "policies" / "telegram_users.json"
_VALID_ACTIONS = {"approve", "reject"}

_APPROVE_AUDIT = {
    "approved": "APPROVAL_GRANTED",
    "not_found": "APPROVAL_INVALID_TOKEN",
    "task_mismatch": "APPROVAL_INVALID_TOKEN",
    "already_used": "APPROVAL_ALREADY_USED",
    "expired": "APPROVAL_EXPIRED",
    "forbidden": "APPROVAL_DENIED",
    "rate_limited": "APPROVAL_RATE_LIMITED",
}

_REJECT_AUDIT = {
    "rejected": "APPROVAL_REJECTED",
    "not_found": "APPROVAL_REJECT_INVALID_TOKEN",
    "task_mismatch": "APPROVAL_REJECT_INVALID_TOKEN",
    "already_used": "APPROVAL_ALREADY_USED",
    "expired": "APPROVAL_EXPIRED",
    "forbidden": "APPROVAL_REJECT_FORBIDDEN",
    "rate_limited": "APPROVAL_RATE_LIMITED",
}


def load_user_map() -> list[dict]:
    if not _USER_MAP_PATH.exists():
        logger.warning("telegram_users.json 없음: %s", _USER_MAP_PATH)
        return []
    try:
        return json.loads(_USER_MAP_PATH.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001 - telegram_users.json 로드 실패 시 에러 로그 남기고 빈 목록 반환 - 허용 사용자 목록이 비면 이후 권한 체크가 전원 거부(fail-closed)로 이어지는 안전한 폴백
        logger.error("telegram_users.json 로드 실패: %s", e)
        return []


def get_mapped_user(telegram_user_id: str) -> dict | None:
    for user in load_user_map():
        if str(user.get("telegram_user_id", "")) == str(telegram_user_id) and user.get("enabled", False):
            return user
    return None


def handle_telegram_webhook(payload: dict) -> dict:
    """
    payload 필수 필드: telegram_user_id, action, task_id, token_id
    Returns: {"success": bool, "status": str, "actor": str, "role": str}
    """
    # 필수 필드 검증
    required = {"telegram_user_id", "action", "task_id", "token_id"}
    missing = required - set(payload.keys())
    if missing:
        logger.warning("텔레그램 webhook: 누락 필드 %s", missing)
        return {"success": False, "status": "invalid_payload", "message": f"누락 필드: {sorted(missing)}"}

    tg_user_id = str(payload["telegram_user_id"])
    action = str(payload["action"]).lower().strip()
    task_id = str(payload["task_id"])
    token_id = str(payload["token_id"])
    reason = str(payload.get("reason", ""))

    # action 검증
    if action not in _VALID_ACTIONS:
        logger.warning("텔레그램 webhook: 알 수 없는 action=%s", action)
        return {"success": False, "status": "invalid_action", "message": f"알 수 없는 action: {action}"}

    # 사용자 매핑 검증
    user = get_mapped_user(tg_user_id)
    if not user:
        logger.warning("텔레그램 webhook: 미등록/비활성 사용자 | tg_user_id=%s", tg_user_id)
        return {"success": False, "status": "user_not_found", "message": "등록되지 않은 텔레그램 사용자"}

    actor = user["actor"]
    role = user["role"]

    # inbox 기록 (telegram_command로 저장)
    create_inbox_item(
        source_type="telegram_command",
        source_account=tg_user_id,
        external_id=token_id,
        sender=actor,
        title=f"텔레그램 {action}",
        body_raw=json.dumps({k: v for k, v in payload.items() if k != "telegram_user_id"}, ensure_ascii=False),
        body_summary=f"action={action} task_id={task_id}",
        linked_task_id=task_id,
        metadata={"role": role, "action": action},
    )

    if action == "approve":
        token, status = approve_token(token_id, task_id, actor, role)
        audit_event = _APPROVE_AUDIT.get(status, "APPROVAL_DENIED")
        log_event(
            audit_event,
            task_id,
            token_id=token_id,
            actor=actor,
            role=role,
            decision=status,
            risk_level=token.risk_level,
            note="source=telegram",
        )
        return {"success": status == "approved", "status": status, "actor": actor, "role": role}

    else:  # reject
        token, status = reject_token(token_id, task_id, actor, role, reason=reason)
        audit_event = _REJECT_AUDIT.get(status, "APPROVAL_REJECTED")
        log_event(
            audit_event,
            task_id,
            token_id=token_id,
            actor=actor,
            role=role,
            decision=status,
            risk_level=token.risk_level,
            note=f"source=telegram | reason={reason}" if reason else "source=telegram",
        )
        return {"success": status == "rejected", "status": status, "actor": actor, "role": role}


def handle_telegram_update(update: dict) -> dict:
    """실제 Telegram Update(JSON) 수신 어댑터.

    두 가지 callback_data 형식을 순서대로 시도한다:
      1. "action|task_id|token_id" — 기존 범용 승인 흐름
      2. "dr_a|token_id" / "dr_r|token_id" — 개발자 등록 신청 전용
    """
    cq = update.get("callback_query")
    if not isinstance(cq, dict):
        return {"success": False, "status": "invalid_payload", "message": "callback_query 없음"}

    frm = cq.get("from") or {}
    tg_user_id = frm.get("id")
    tg_username = frm.get("username")
    if tg_user_id is None:
        return {"success": False, "status": "invalid_payload", "message": "callback_query.from.id 없음"}

    data = cq.get("data")
    cq_id = cq.get("id", "")

    # ── 형식 1: 기존 "approve|task_id|token_id" ─────────────────────
    parsed = parse_callback_data(data) if isinstance(data, str) else None
    if parsed is not None:
        reason = str(cq.get("reason", "")) if "reason" in cq else ""
        flat = {
            "telegram_user_id": str(tg_user_id),
            "action": parsed["action"],
            "task_id": parsed["task_id"],
            "token_id": parsed["token_id"],
            "reason": reason,
        }
        result = handle_telegram_webhook(flat)
        result["message"] = build_result_text(
            parsed["action"],
            result.get("status", ""),
            actor=result.get("actor", ""),
            reason=reason,
        )
        if tg_username:
            result["telegram_username"] = tg_username
        result["callback_query_id"] = cq_id
        return result

    # ── 형식 2: 개발자 등록 "dr_a|token_id" / "dr_r|token_id" ───────
    dr_parsed = parse_dev_reg_callback_data(data) if isinstance(data, str) else None
    if dr_parsed is not None:
        return _handle_dev_reg_callback(
            tg_user_id=str(tg_user_id),
            action=dr_parsed["action"],
            token_id=dr_parsed["token_id"],
            cq_id=cq_id,
            username=tg_username or "",
        )

    return {"success": False, "status": "invalid_payload", "message": f"잘못된 callback_data: {data!r}"}


def _handle_dev_reg_callback(
    tg_user_id: str,
    action: str,
    token_id: str,
    cq_id: str,
    username: str,
) -> dict:
    """개발자 등록 신청 승인/거절 처리."""
    user = get_mapped_user(tg_user_id)
    if not user:
        logger.warning("개발자 등록 webhook: 미등록/비활성 사용자 | tg_user_id=%s", tg_user_id)
        return {
            "success": False,
            "status": "user_not_found",
            "message": "등록되지 않은 텔레그램 사용자",
            "callback_query_id": cq_id,
        }

    actor = user["actor"]
    role = user["role"]

    from ..dev_reg.dev_reg_approval import handle_telegram_decision

    result = handle_telegram_decision(
        token_id=token_id,
        action=action,
        actor=actor,
        role=role,
    )
    result["callback_query_id"] = cq_id
    if username:
        result["telegram_username"] = username
    return result

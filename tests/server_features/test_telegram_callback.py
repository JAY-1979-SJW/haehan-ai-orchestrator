import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ai_orchestrator.core.models import RiskAssessment, TaskRequest
from ai_orchestrator.notify.telegram_notifier import (
    build_approval_message,
    build_callback_data,
    parse_callback_data,
)
from ai_orchestrator.notify.telegram_webhook import handle_telegram_update
from tools.gates.approval import issue_token


def _req(task_id: str) -> TaskRequest:
    return TaskRequest(
        task_id=task_id,
        source="manual",
        action_type="edit_config",
        target="/var/www/haehan/cfg.yaml",
        description="CB 테스트",
        requested_by="test",
    )


def _risk() -> RiskAssessment:
    return RiskAssessment(risk_level="medium", reasons=["test"], requires_approval=True)


def _tid() -> str:
    return f"CB-{uuid.uuid4().hex[:6]}"


def _update(tg_user_id: str, callback_data: str, username: str = "admin", query_id: str = "cbq-1") -> dict:
    return {
        "update_id": 1,
        "callback_query": {
            "id": query_id,
            "from": {"id": int(tg_user_id), "username": username},
            "message": {"message_id": 10, "chat": {"id": int(tg_user_id)}, "text": "승인 요청"},
            "data": callback_data,
        },
    }


# ── 0. callback_data round-trip ────────────────────────────────────
def test_callback_data_roundtrip():
    data = build_callback_data("approve", "CB-abc123", "11111111-1111-1111-1111-111111111111")
    parsed = parse_callback_data(data)
    assert parsed == {"action": "approve", "task_id": "CB-abc123", "token_id": "11111111-1111-1111-1111-111111111111"}


# ── 1. approve callback → approved ────────────────────────────────
def test_callback_approve_success():
    tid = _tid()
    token = issue_token(_req(tid), _risk())
    update = _update("111111111", build_callback_data("approve", tid, token.token_id))
    r = handle_telegram_update(update)
    assert r["success"] is True and r["status"] == "approved", r
    assert r["role"] == "admin"
    assert "승인 완료" in r["message"]
    assert r.get("telegram_username") == "admin"


# ── 2. reject callback → rejected ─────────────────────────────────
def test_callback_reject_success():
    tid = _tid()
    token = issue_token(_req(tid), _risk())
    update = _update("222222222", build_callback_data("reject", tid, token.token_id), username="approver-01")
    update["callback_query"]["reason"] = "정책 위반"
    r = handle_telegram_update(update)
    assert r["success"] is True and r["status"] == "rejected", r
    assert "거절 완료" in r["message"]


# ── 3. 이미 처리된 토큰 재호출 → already_used ────────────────────
def test_callback_already_used_blocked():
    tid = _tid()
    token = issue_token(_req(tid), _risk())
    update = _update("111111111", build_callback_data("approve", tid, token.token_id))
    r1 = handle_telegram_update(update)
    assert r1["status"] == "approved"
    r2 = handle_telegram_update(update)
    assert r2["success"] is False and r2["status"] == "already_used", r2


# ── 4. 잘못된 task_id → task_mismatch ────────────────────────────
def test_callback_task_mismatch_blocked():
    tid = _tid()
    token = issue_token(_req(tid), _risk())
    update = _update("111111111", build_callback_data("approve", "WRONG-TASK", token.token_id))
    r = handle_telegram_update(update)
    assert r["success"] is False and r["status"] == "task_mismatch", r


# ── 5. 잘못된 callback_data 포맷 → invalid_payload ───────────────
def test_callback_invalid_data():
    update = _update("111111111", "garbage-without-separators")
    r = handle_telegram_update(update)
    assert r["success"] is False and r["status"] == "invalid_payload", r


# ── 6. build_approval_message 구조 ───────────────────────────────
def test_build_approval_message_structure():
    msg = build_approval_message("T-1", "medium", "tok-xyz-1")
    kb = msg["reply_markup"]["inline_keyboard"]
    assert kb[0][0]["callback_data"].startswith("approve|T-1|")
    assert kb[0][1]["callback_data"].startswith("reject|T-1|")


if __name__ == "__main__":
    tests = [
        test_callback_data_roundtrip,
        test_callback_approve_success,
        test_callback_reject_success,
        test_callback_already_used_blocked,
        test_callback_task_mismatch_blocked,
        test_callback_invalid_data,
        test_build_approval_message_structure,
    ]
    for t in tests:
        t()
        print(f"PASS: {t.__name__}")
    print("\n모든 telegram_callback 테스트 통과")

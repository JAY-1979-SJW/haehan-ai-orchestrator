import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ai_orchestrator.audit.audit_logger import read_recent_logs
from ai_orchestrator.core.models import RiskAssessment, TaskRequest
from ai_orchestrator.notify.telegram_webhook import handle_telegram_webhook
from tools.gates.approval import issue_token


def _req(task_id: str) -> TaskRequest:
    return TaskRequest(
        task_id=task_id,
        source="manual",
        action_type="edit_config",
        target="/var/www/haehan/cfg.yaml",
        description="TG 테스트",
        requested_by="test",
    )


def _risk() -> RiskAssessment:
    return RiskAssessment(risk_level="medium", reasons=["test"], requires_approval=True)


def _tid() -> str:
    return f"TG-{uuid.uuid4().hex[:8]}"


# ── 1. 정상 approve ─────────────────────────────────────────────────
def test_telegram_approve_success():
    tid = _tid()
    token = issue_token(_req(tid), _risk())
    result = handle_telegram_webhook(
        {
            "telegram_user_id": "111111111",  # admin
            "action": "approve",
            "task_id": tid,
            "token_id": token.token_id,
        }
    )
    assert result["success"] is True, f"expected success: {result}"
    assert result["status"] == "approved"
    assert result["role"] == "admin"


# ── 2. 정상 reject ──────────────────────────────────────────────────
def test_telegram_reject_success():
    tid = _tid()
    token = issue_token(_req(tid), _risk())
    result = handle_telegram_webhook(
        {
            "telegram_user_id": "222222222",  # approver
            "action": "reject",
            "task_id": tid,
            "token_id": token.token_id,
            "reason": "테스트 거절",
        }
    )
    assert result["success"] is True, f"expected success: {result}"
    assert result["status"] == "rejected"
    assert result["role"] == "approver"


# ── 3. 미등록 사용자 거절 ────────────────────────────────────────────
def test_telegram_unmapped_user():
    tid = _tid()
    token = issue_token(_req(tid), _risk())
    result = handle_telegram_webhook(
        {
            "telegram_user_id": "000000000",
            "action": "approve",
            "task_id": tid,
            "token_id": token.token_id,
        }
    )
    assert result["success"] is False
    assert result["status"] == "user_not_found"


# ── 4. viewer role 거절 (forbidden) ─────────────────────────────────
def test_telegram_viewer_forbidden():
    tid = _tid()
    token = issue_token(_req(tid), _risk())
    result = handle_telegram_webhook(
        {
            "telegram_user_id": "333333333",  # viewer
            "action": "approve",
            "task_id": tid,
            "token_id": token.token_id,
        }
    )
    assert result["success"] is False
    assert result["status"] == "forbidden"


# ── 5. task_id/token_id 불일치 ──────────────────────────────────────
def test_telegram_task_mismatch():
    tid = _tid()
    token = issue_token(_req(tid), _risk())
    result = handle_telegram_webhook(
        {
            "telegram_user_id": "111111111",
            "action": "approve",
            "task_id": "WRONG-TASK-ID",
            "token_id": token.token_id,
        }
    )
    assert result["success"] is False
    assert result["status"] == "task_mismatch"


# ── 6. invalid action ────────────────────────────────────────────────
def test_telegram_invalid_action():
    tid = _tid()
    token = issue_token(_req(tid), _risk())
    result = handle_telegram_webhook(
        {
            "telegram_user_id": "111111111",
            "action": "delete",
            "task_id": tid,
            "token_id": token.token_id,
        }
    )
    assert result["success"] is False
    assert result["status"] == "invalid_action"


# ── 7. 누락 필드 ────────────────────────────────────────────────────
def test_telegram_missing_fields():
    result = handle_telegram_webhook(
        {
            "telegram_user_id": "111111111",
            "action": "approve",
            # task_id, token_id 누락
        }
    )
    assert result["success"] is False
    assert result["status"] == "invalid_payload"


# ── 8. disabled 사용자 거절 ─────────────────────────────────────────
def test_telegram_disabled_user():
    tid = _tid()
    token = issue_token(_req(tid), _risk())
    result = handle_telegram_webhook(
        {
            "telegram_user_id": "999999999",  # enabled=false
            "action": "approve",
            "task_id": tid,
            "token_id": token.token_id,
        }
    )
    assert result["success"] is False
    assert result["status"] == "user_not_found"


# ── 9. audit 이벤트명 검증 ──────────────────────────────────────────
def test_audit_event_names():
    tid_a = _tid()
    tid_r = _tid()
    token_a = issue_token(_req(tid_a), _risk())
    token_r = issue_token(_req(tid_r), _risk())

    handle_telegram_webhook(
        {
            "telegram_user_id": "111111111",
            "action": "approve",
            "task_id": tid_a,
            "token_id": token_a.token_id,
        }
    )
    handle_telegram_webhook(
        {
            "telegram_user_id": "222222222",
            "action": "reject",
            "task_id": tid_r,
            "token_id": token_r.token_id,
            "reason": "감사 로그 테스트",
        }
    )

    logs = read_recent_logs(limit=100)
    event_names = {e["event_type"] for e in logs}
    assert "APPROVAL_GRANTED" in event_names, f"APPROVAL_GRANTED 없음: {event_names}"
    assert "APPROVAL_REJECTED" in event_names, f"APPROVAL_REJECTED 없음: {event_names}"


if __name__ == "__main__":
    tests = [
        test_telegram_approve_success,
        test_telegram_reject_success,
        test_telegram_unmapped_user,
        test_telegram_viewer_forbidden,
        test_telegram_task_mismatch,
        test_telegram_invalid_action,
        test_telegram_missing_fields,
        test_telegram_disabled_user,
        test_audit_event_names,
    ]
    for t in tests:
        t()
        print(f"PASS: {t.__name__}")
    print("\n모든 telegram_webhook 테스트 통과")

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ai_orchestrator.audit.audit_logger import read_recent_logs
from ai_orchestrator.core.models import RiskAssessment, TaskRequest
from tools.gates.approval import (
    RATE_LIMIT_MAX,
    approve_token,
    issue_token,
    validate_token,
)


def _req(task_id: str, action="edit_config") -> TaskRequest:
    return TaskRequest(
        task_id=task_id,
        source="manual",
        action_type=action,
        target="/var/www/haehan/cfg.yaml",
        description="테스트",
        requested_by="test",
    )


def _risk(level="medium") -> RiskAssessment:
    return RiskAssessment(risk_level=level, reasons=["test"], requires_approval=True)


def _unique_task() -> str:
    return f"V2-{uuid.uuid4().hex[:8]}"


# ── 1. 정상 승인 성공 ──────────────────────────────────────��───────
def test_normal_approval_success():
    tid = _unique_task()
    req, risk = _req(tid), _risk()
    token = issue_token(req, risk)
    approved, status = approve_token(token.token_id, tid, "대표님", "admin")
    assert status == "approved", f"expected approved, got {status}"
    assert approved.status == "approved"
    assert approved.used_at is not None
    assert approved.result == "approved"
    assert validate_token(token.token_id, tid)


# ── 2. 없는 token → not_found ────────────────────────────��────────
def test_unknown_token_not_found():
    _, status = approve_token("00000000-0000-0000-0000-000000000000", "any-task", "actor", "admin")
    assert status == "not_found"


# ── 3. task_id 불일치 → task_mismatch ────────────────────────────
def test_task_mismatch():
    tid = _unique_task()
    token = issue_token(_req(tid), _risk())
    _, status = approve_token(token.token_id, "WRONG-TASK", "actor", "admin")
    assert status == "task_mismatch"


# ── 4. 이미 사용된 토큰 재사용 → already_used ────────────────────
def test_already_used_token():
    tid = _unique_task()
    token = issue_token(_req(tid), _risk())
    _, s1 = approve_token(token.token_id, tid, "대표님", "admin")
    assert s1 == "approved"
    _, s2 = approve_token(token.token_id, tid, "대표님", "admin")
    assert s2 == "already_used"


# ── 5. role 부족 (viewer) → forbidden ────────────────────────────
def test_viewer_role_forbidden():
    tid = _unique_task()
    token = issue_token(_req(tid), _risk())
    _, status = approve_token(token.token_id, tid, "viewer-user", "viewer")
    assert status == "forbidden"


# ── 6. operator → forbidden ────────────────────���──────────────────
def test_operator_role_forbidden():
    tid = _unique_task()
    token = issue_token(_req(tid), _risk())
    _, status = approve_token(token.token_id, tid, "op-user", "operator")
    assert status == "forbidden"


# ── 7. approver role → 승인 성공 ───────────────────────────────���─
def test_approver_role_allowed():
    tid = _unique_task()
    token = issue_token(_req(tid), _risk())
    _, status = approve_token(token.token_id, tid, "approver-user", "approver")
    assert status == "approved"


# ── 8. 만료 토큰 → expired ────────────────────────────────────────
def test_expired_token():
    tid = _unique_task()
    token = issue_token(_req(tid), _risk(), ttl_minutes=0)
    _, status = approve_token(token.token_id, tid, "대표님", "admin")
    assert status == "expired"
    assert not validate_token(token.token_id, tid)


# ── 9. rate limit — 동일 actor 짧은 시간 연속 시도 ──────────────
def test_rate_limit():
    actor = f"rate-actor-{uuid.uuid4().hex}"
    # rate store 클린 (고유 actor라 기본적으로 비어 있음)
    results = []
    for _i in range(RATE_LIMIT_MAX + 1):
        tid = f"RATE-{uuid.uuid4().hex[:8]}"
        token = issue_token(_req(tid), _risk())
        _, status = approve_token(token.token_id, tid, actor, "admin")
        results.append(status)

    assert results[:RATE_LIMIT_MAX] == ["approved"] * RATE_LIMIT_MAX, (
        f"처음 {RATE_LIMIT_MAX}회는 모두 approved여야 함: {results}"
    )
    assert results[RATE_LIMIT_MAX] == "rate_limited", f"마지막은 rate_limited여야 함: {results[RATE_LIMIT_MAX]}"


# ── 10. audit 로그 이벤트명 구분 검증 ────────────────────────────
def test_audit_event_names():
    from ai_orchestrator.audit.audit_logger import log_event

    tid = _unique_task()
    token = issue_token(_req(tid), _risk())

    # 정상 승인 → APPROVAL_GRANTED 이벤트
    _, status = approve_token(token.token_id, tid, "대표님", "admin")
    log_event("APPROVAL_GRANTED", tid, token_id=token.token_id, actor="대표님", role="admin", decision=status)

    # forbidden → APPROVAL_DENIED 이벤트
    tid2 = _unique_task()
    token2 = issue_token(_req(tid2), _risk())
    _, s2 = approve_token(token2.token_id, tid2, "viewer", "viewer")
    log_event("APPROVAL_DENIED", tid2, token_id=token2.token_id, actor="viewer", role="viewer", decision=s2)

    logs = read_recent_logs(limit=50)
    event_names = {e["event_type"] for e in logs}
    assert "APPROVAL_GRANTED" in event_names
    assert "APPROVAL_DENIED" in event_names


# ── 11. already_used audit 이벤트 ─────────────────────────��──────
def test_already_used_audit_event():
    from ai_orchestrator.audit.audit_logger import log_event

    actor = f"already-actor-{uuid.uuid4().hex}"
    tid = _unique_task()
    token = issue_token(_req(tid), _risk())
    approve_token(token.token_id, tid, actor, "admin")
    _, s = approve_token(token.token_id, tid, actor, "admin")
    assert s == "already_used", f"expected already_used, got {s}"
    log_event("APPROVAL_ALREADY_USED", tid, token_id=token.token_id, actor=actor, decision=s)

    logs = read_recent_logs(limit=50)
    assert any(e["event_type"] == "APPROVAL_ALREADY_USED" for e in logs)


if __name__ == "__main__":
    tests = [
        test_normal_approval_success,
        test_unknown_token_not_found,
        test_task_mismatch,
        test_already_used_token,
        test_viewer_role_forbidden,
        test_operator_role_forbidden,
        test_approver_role_allowed,
        test_expired_token,
        test_rate_limit,
        test_audit_event_names,
        test_already_used_audit_event,
    ]
    for t in tests:
        t()
        print(f"PASS: {t.__name__}")
    print("\n모든 approval_v2 테스트 통과")

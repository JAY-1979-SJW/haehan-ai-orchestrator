import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ai_orchestrator.core.models import RiskAssessment, TaskRequest
from tools.gates.approval import approve_token, issue_token, validate_token


def make_req(task_id="T-APR-001"):
    return TaskRequest(
        task_id=task_id,
        source="manual",
        action_type="edit_config",
        target="/var/www/haehan/cfg.yaml",
        description="테스트",
        requested_by="test",
    )


def make_risk():
    return RiskAssessment(risk_level="medium", reasons=["test"], requires_approval=True)


def test_issue_and_validate():
    req = make_req("T-APR-V1")
    risk = make_risk()
    token = issue_token(req, risk)
    assert token.status == "issued"
    # 아직 승인 안 했으므로 validate=False
    assert not validate_token(token.token_id, req.task_id)
    print("PASS: issue_token 후 미승인 상태 validate=False")


def test_approve_and_validate():
    req = make_req("T-APR-V2")
    risk = make_risk()
    token = issue_token(req, risk)
    approved, status = approve_token(token.token_id, req.task_id, "대표님", "admin")
    assert status == "approved"
    assert approved.status == "approved"
    assert validate_token(token.token_id, req.task_id)
    print("PASS: approve_token 후 status=approved, validate=True")


def test_wrong_task_id_fails():
    req = make_req("T-APR-V3")
    risk = make_risk()
    token = issue_token(req, risk)
    _, status = approve_token(token.token_id, req.task_id, "대표님", "admin")
    assert status == "approved"
    assert not validate_token(token.token_id, "WRONG-TASK-ID")
    print("PASS: task_id 불일치 시 validate=False")


def test_expired_token_fails():
    req = make_req("T-APR-V4")
    risk = make_risk()
    token = issue_token(req, risk, ttl_minutes=0)
    _, status = approve_token(token.token_id, req.task_id, "대표님", "admin")
    assert status == "expired"
    assert not validate_token(token.token_id, req.task_id)
    print("PASS: 만료 토큰 status=expired, validate=False")


if __name__ == "__main__":
    test_issue_and_validate()
    test_approve_and_validate()
    test_wrong_task_id_fails()
    test_expired_token_fails()
    print("\n모든 approval 테스트 통과")

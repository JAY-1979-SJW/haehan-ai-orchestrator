import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ai_orchestrator.core.models import TaskRequest
from ai_orchestrator.llm.planner import plan
from ai_orchestrator.tasks.executor import execute


def make_req(task_id, action, target, payload=None):
    return TaskRequest(
        task_id=task_id,
        source="manual",
        action_type=action,
        target=target,
        description="정책 게이트 테스트",
        payload=payload or {},
        requested_by="test",
    )


def test_read_file_auto_allowed():
    req = make_req("PG001", "read_file", "/var/log/app.log")
    risk, ep = plan(req)
    result = execute(ep)
    assert ep.allowed, "read_file should be allowed"
    assert not ep.requires_approval, "read_file should not require approval"
    assert result == "DRY_RUN_ONLY"
    print("PASS: read_file → 자동 허용, DRY_RUN_ONLY")


def test_restart_service_pending_approval():
    req = make_req("PG002", "restart_service", "haehan-api")
    risk, ep = plan(req)
    result = execute(ep)
    assert ep.requires_approval, "restart_service should require approval"
    assert result == "PENDING_APPROVAL"
    print("PASS: restart_service → PENDING_APPROVAL")


def test_delete_file_blocked():
    req = make_req("PG003", "delete_file", "/var/www/haehan/old.tar.gz")
    risk, ep = plan(req)
    result = execute(ep)
    assert not ep.allowed, "delete_file should be blocked"
    assert result.startswith("BLOCKED")
    print("PASS: delete_file → BLOCKED")


def test_blocked_path_blocked():
    req = make_req("PG004", "write_file", "/etc/nginx/nginx.conf")
    risk, ep = plan(req)
    result = execute(ep)
    assert not ep.allowed, "blocked path should be blocked"
    assert result.startswith("BLOCKED")
    print("PASS: blocked_path(/etc/) → BLOCKED")


if __name__ == "__main__":
    test_read_file_auto_allowed()
    test_restart_service_pending_approval()
    test_delete_file_blocked()
    test_blocked_path_blocked()
    print("\n모든 policy_gate 테스트 통과")

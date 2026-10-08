import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / ".."))

from orchestrator_v1.core.models import ExecutionPlan, RiskAssessment, TaskRequest
from orchestrator_v1.tasks.policy_engine import load_policy
from orchestrator_v1.tasks.whitelist_executor import can_execute, execute_allowed

_TMPDIR = tempfile.gettempdir()


def _make_policy_with_tmp() -> dict:
    policy = load_policy()
    # Ensure system temp dir is in allowed_paths for cross-platform tests
    allowed = policy.get("allowed_paths", [])
    if _TMPDIR not in allowed:
        allowed.append(_TMPDIR)
    policy["allowed_paths"] = allowed
    return policy


def _make_low_read(target: str) -> tuple:
    task = TaskRequest(
        task_id="t-low-read",
        source="pc",
        action_type="read_file",
        target=target,
        description="read test",
    )
    risk = RiskAssessment(risk_level="low", requires_approval=False)
    plan = ExecutionPlan(task_id=task.task_id, allowed=True, requires_approval=False, steps=[])
    return task, risk, plan


def test_low_read_file_can_execute():
    policy = _make_policy_with_tmp()
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".txt", delete=False, dir=_TMPDIR) as f:
        f.write("hello")
        path = f.name

    task, risk, plan = _make_low_read(path)
    ok, reasons = can_execute(task, risk, plan, policy, approval_valid=False)
    assert ok, f"Expected executable but got: {reasons}"
    Path(path).unlink()


def test_low_read_file_executes():
    policy = _make_policy_with_tmp()
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".txt", delete=False, dir=_TMPDIR) as f:
        f.write("content")
        path = f.name

    task, risk, plan = _make_low_read(path)
    result = execute_allowed(task, risk, plan, policy, approval_valid=False)
    assert result["status"] == "EXECUTED", result
    Path(path).unlink()


def test_medium_edit_config_preview_only():
    policy = _make_policy_with_tmp()
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".txt", delete=False, dir=_TMPDIR) as f:
        f.write("old")
        path = f.name

    task = TaskRequest(
        task_id="t-med-edit",
        source="pc",
        action_type="edit_config",
        target=path,
        description="edit test",
        payload={"new_content": "new content"},
    )
    risk = RiskAssessment(risk_level="medium", requires_approval=True)
    plan = ExecutionPlan(task_id=task.task_id, allowed=True, requires_approval=True, steps=[])

    result = execute_allowed(task, risk, plan, policy, approval_valid=True)
    assert result["status"] == "PREVIEW_ONLY", result
    assert result.get("preview_only") is True

    with Path(path).open(encoding="utf-8") as f:
        assert f.read() == "old", "file must NOT be modified"
    Path(path).unlink()


def test_high_restart_service_blocked():
    policy = load_policy()
    task = TaskRequest(
        task_id="t-high-restart",
        source="server",
        action_type="restart_service",
        target="nginx",
        description="restart nginx",
    )
    risk = RiskAssessment(risk_level="high", requires_approval=True)
    plan = ExecutionPlan(
        task_id=task.task_id,
        allowed=False,
        requires_approval=True,
        blocked_reasons=["high actions cannot be auto-executed"],
    )

    ok, reasons = can_execute(task, risk, plan, policy, approval_valid=True)
    assert not ok
    assert len(reasons) > 0


def test_blocked_path_is_blocked():
    policy = load_policy()
    # Use a real blocked path from policy
    blocked_path = policy.get("blocked_paths", ["/etc/"])[0]
    task = TaskRequest(
        task_id="t-blocked-path",
        source="pc",
        action_type="read_file",
        target=str(Path(blocked_path) / "testfile"),
        description="try to read blocked path",
    )
    risk = RiskAssessment(risk_level="low", requires_approval=False)
    plan = ExecutionPlan(task_id=task.task_id, allowed=True, requires_approval=False)

    ok, reasons = can_execute(task, risk, plan, policy, approval_valid=False)
    assert not ok
    assert len(reasons) > 0

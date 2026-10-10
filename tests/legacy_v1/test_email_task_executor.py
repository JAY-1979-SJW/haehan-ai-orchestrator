"""
email task approval → execution 테스트
1. approval 승인 → execution ready 전환
2. approval 거절 → 상태 유지 (pending)
3. medium risk policy → 실행 차단(skipped)
4. high risk policy → 실행 차단(blocked_policy)
5. low risk → executor 연결 정상 동작
6. 승인 없이 execute 호출 → not_approved
7. ready 아닌 task execute → not_ready
8. 없는 task approve/reject/execute → not_found
9. 자동 실행 미발생 확인
10. 기존 approval_manager/_store 무변경
11. 앱 부팅 가능 여부
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / ".."))

import orchestrator_v1.tasks.email_task_approval as email_task_approval
import orchestrator_v1.tasks.email_task_store as email_task_store
from orchestrator_v1.tasks import email_task_executor

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def task_path(tmp_path):
    return str(tmp_path / "email_tasks.jsonl")


@pytest.fixture
def token_path(tmp_path):
    return str(tmp_path / "email_approval_tokens.json")


def _seed_task(task_path: str, task_id: str, risk_level: str = "medium") -> dict:
    entry = {
        "task_id": task_id,
        "source": "email_candidate",
        "source_item_id": f"item-{task_id}",
        "category": "operations" if risk_level == "high" else "sales",
        "priority": "high" if risk_level == "high" else "medium",
        "task_type": "ops_check" if risk_level == "high" else "quote_response",
        "title": f"[test] {task_id}",
        "status": "pending",
        "risk_level": risk_level,
        "created_at": "2026-04-22T10:00:00",
        "linked_candidate_id": f"item-{task_id}",
    }
    Path(task_path).parent.mkdir(parents=True, exist_ok=True)
    with Path(task_path).open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def _request_and_approve(task_id, task_path, token_path, approved_by="operator-1"):
    """approval 요청 + 승인 헬퍼."""
    email_task_approval.request_approval(task_id, token_path=token_path, task_path=task_path)
    return email_task_executor.approve_task(task_id, approved_by, token_path=token_path, task_path=task_path)


# ── 1. approval 승인 → execution ready 전환 ───────────────────────────────────


def test_approve_sets_task_ready(task_path, token_path):
    _seed_task(task_path, "etask-exec001")
    email_task_approval.request_approval("etask-exec001", token_path=token_path, task_path=task_path)

    result = email_task_executor.approve_task("etask-exec001", "operator-1", token_path=token_path, task_path=task_path)

    assert result["status"] == "approved"
    assert result["task_status"] == "ready"
    assert result["approval_status"] == "approved"

    task = email_task_store.get_email_task("etask-exec001", path=task_path)
    assert task["status"] == "ready"
    assert task["approval_status"] == "approved"


def test_approve_token_status_updated(task_path, token_path):
    _seed_task(task_path, "etask-exec002")
    email_task_approval.request_approval("etask-exec002", token_path=token_path, task_path=task_path)

    email_task_executor.approve_task("etask-exec002", "admin-1", token_path=token_path, task_path=task_path)

    token = email_task_approval.get_approval_for_task("etask-exec002", token_path=token_path)
    assert token["status"] == "approved"
    assert token["approved_by"] == "admin-1"


# ── 2. approval 거절 → 상태 유지 ──────────────────────────────────────────────


def test_reject_keeps_task_pending(task_path, token_path):
    _seed_task(task_path, "etask-exec003")
    email_task_approval.request_approval("etask-exec003", token_path=token_path, task_path=task_path)

    result = email_task_executor.reject_task("etask-exec003", "operator-1", token_path=token_path, task_path=task_path)

    assert result["status"] == "rejected"
    assert result["approval_status"] == "rejected"

    task = email_task_store.get_email_task("etask-exec003", path=task_path)
    assert task["status"] == "pending"  # status 유지
    assert task["approval_status"] == "rejected"


# ── 3. medium risk → SKIPPED (정책상 실행 금지) ───────────────────────────────


def test_medium_risk_execution_skipped(task_path, token_path):
    _seed_task(task_path, "etask-med001", risk_level="medium")
    _request_and_approve("etask-med001", task_path, token_path)

    result = email_task_executor.execute_email_task("etask-med001", task_path=task_path, token_path=token_path)

    assert result["status"] == "skipped"
    assert result["risk_level"] == "medium"

    # task_store에 등록되지 않아야 함 (자동 실행 없음)
    import orchestrator_v1.tasks.task_store as ts

    assert ts.get("etask-med001") is None


# ── 4. high risk → BLOCKED_POLICY ─────────────────────────────────────────────


def test_high_risk_execution_blocked(task_path, token_path):
    _seed_task(task_path, "etask-high001", risk_level="high")
    _request_and_approve("etask-high001", task_path, token_path)

    result = email_task_executor.execute_email_task("etask-high001", task_path=task_path, token_path=token_path)

    assert result["status"] == "blocked_policy"
    assert result["risk_level"] == "high"


# ── 5. low risk → executor 연결 정상 동작 ────────────────────────────────────


def test_low_risk_execution_attempted(task_path, token_path):
    """low risk task는 execute_allowed()까지 호출됨 (adapter 결과는 BLOCKED or EXECUTED)."""
    _seed_task(task_path, "etask-low001", risk_level="low")
    _request_and_approve("etask-low001", task_path, token_path)

    result = email_task_executor.execute_email_task("etask-low001", task_path=task_path, token_path=token_path)

    # execute_allowed까지 진입했으면 status는 EXECUTED 또는 BLOCKED (adapter 결과)
    # "not_ready", "not_approved", "blocked_policy", "skipped" 등 조기 차단 아님
    assert result.get("status") not in {"not_ready", "not_approved", "blocked_policy", "skipped", "not_found"}
    assert "task_id" in result


def test_low_risk_task_status_executed(task_path, token_path):
    """low risk 실행 후 task status → executed."""
    _seed_task(task_path, "etask-low002", risk_level="low")
    _request_and_approve("etask-low002", task_path, token_path)

    email_task_executor.execute_email_task("etask-low002", task_path=task_path, token_path=token_path)

    task = email_task_store.get_email_task("etask-low002", path=task_path)
    assert task["status"] == "executed"


# ── 6. 승인 없이 execute → not_approved ──────────────────────────────────────


def test_execute_without_approval_rejected(task_path, token_path):
    _seed_task(task_path, "etask-noap001")
    # approval 요청 없이 바로 execute

    result = email_task_executor.execute_email_task("etask-noap001", task_path=task_path, token_path=token_path)
    # status=pending (not ready)이므로 not_ready
    assert result["status"] == "not_ready"


# ── 7. ready 아닌 task execute → not_ready ────────────────────────────────────


def test_execute_pending_task_returns_not_ready(task_path, token_path):
    _seed_task(task_path, "etask-notready001")

    result = email_task_executor.execute_email_task("etask-notready001", task_path=task_path, token_path=token_path)
    assert result["status"] == "not_ready"
    assert result["current_status"] == "pending"


# ── 8. 없는 task 처리 ─────────────────────────────────────────────────────────


def test_approve_not_found(task_path, token_path):
    result = email_task_executor.approve_task("etask-ghost", "operator-1", token_path=token_path, task_path=task_path)
    assert result["status"] == "not_found"


def test_reject_not_found(task_path, token_path):
    result = email_task_executor.reject_task("etask-ghost", "operator-1", token_path=token_path, task_path=task_path)
    assert result["status"] == "not_found"


def test_execute_not_found(task_path, token_path):
    result = email_task_executor.execute_email_task("etask-ghost", task_path=task_path, token_path=token_path)
    assert result["status"] == "not_found"


# ── 9. 자동 실행 미발생 확인 ──────────────────────────────────────────────────


def test_no_auto_execution_on_approve(task_path, token_path):
    """approve_task 호출 자체가 실행을 트리거하지 않음."""
    import orchestrator_v1.tasks.task_store as ts

    ts.clear()

    _seed_task(task_path, "etask-auto001", risk_level="medium")
    email_task_approval.request_approval("etask-auto001", token_path=token_path, task_path=task_path)
    email_task_executor.approve_task("etask-auto001", "operator-1", token_path=token_path, task_path=task_path)

    # in-memory task_store에 등록되지 않아야 함
    assert ts.get("etask-auto001") is None
    assert len(ts._store) == 0

    # task status는 ready이지만 executed는 아님
    task = email_task_store.get_email_task("etask-auto001", path=task_path)
    assert task["status"] == "ready"


# ── 10. 기존 approval_manager/_store 무변경 ───────────────────────────────────


def test_no_conflict_with_existing_approval_manager(task_path, token_path):
    import orchestrator_v1.tasks.approval_manager as approval_manager
    import orchestrator_v1.tasks.task_store as task_store

    before_approval = dict(approval_manager._store)
    before_task = dict(task_store._store)

    _seed_task(task_path, "etask-policy001", risk_level="medium")
    _request_and_approve("etask-policy001", task_path, token_path)
    email_task_executor.execute_email_task("etask-policy001", task_path=task_path, token_path=token_path)

    assert approval_manager._store == before_approval
    assert task_store._store == before_task


# ── 11. 앱 부팅 가능 여부 ─────────────────────────────────────────────────────


def test_app_boot_with_executor_routes():
    import os as _os

    _os.environ.setdefault("ORCH_DASHBOARD_USER", "test")
    _os.environ.setdefault("ORCH_DASHBOARD_PASSWORD", "test")

    from orchestrator_v1.monitoring.dashboard import create_app

    app = create_app()
    rules = {r.rule for r in app.url_map.iter_rules()}

    assert "/api/v1/tasks/<task_id>/approve" in rules
    assert "/api/v1/tasks/<task_id>/reject" in rules
    assert "/api/v1/tasks/<task_id>/execute" in rules
    assert "/api/v1/tasks/<task_id>/approval-request" in rules
    assert "/api/v1/tasks/<task_id>" in rules

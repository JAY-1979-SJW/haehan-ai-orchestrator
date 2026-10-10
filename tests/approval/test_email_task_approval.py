"""
email task → approval request 테스트
1. email task 1건 approval 요청 성공
2. 동일 task 중복 approval 요청 방지
3. 없는 task 거절
4. approval_token_id 연결 검증
5. 기존 approval 구조와 충돌 없음
6. 앱 부팅 가능 여부
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / ".."))

import orchestrator_v1.tasks.email_task_approval as email_task_approval
import orchestrator_v1.tasks.email_task_store as email_task_store

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def task_path(tmp_path):
    return str(tmp_path / "email_tasks.jsonl")


@pytest.fixture
def token_path(tmp_path):
    return str(tmp_path / "email_approval_tokens.json")


def _seed_task(task_path: str, task_id: str = "etask-test001") -> dict:
    """테스트용 email task를 직접 삽입."""
    entry = {
        "task_id": task_id,
        "source": "email_candidate",
        "source_item_id": "item-abc123",
        "category": "sales",
        "priority": "medium",
        "task_type": "quote_response",
        "title": "[sales] quote_response — test",
        "status": "pending",
        "risk_level": "medium",
        "created_at": "2026-04-22T10:00:00",
        "linked_candidate_id": "item-abc123",
    }
    Path(task_path).parent.mkdir(parents=True, exist_ok=True)
    with Path(task_path).open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


# ── 1. email task 1건 approval 요청 성공 ──────────────────────────────────────


def test_approval_request_success(task_path, token_path):
    _seed_task(task_path)

    result = email_task_approval.request_approval(
        "etask-test001",
        token_path=token_path,
        task_path=task_path,
    )

    assert result["status"] == "created"
    assert result["task_id"] == "etask-test001"
    assert "token_id" in result
    assert result["approval_status"] == "pending"
    assert "created_at" in result


def test_approval_status_is_pending_only(task_path, token_path):
    """승인 요청 후 status는 pending — 실행 연결 없음."""
    _seed_task(task_path)
    result = email_task_approval.request_approval(
        "etask-test001",
        token_path=token_path,
        task_path=task_path,
    )
    assert result["approval_status"] == "pending"


# ── 2. 동일 task 중복 approval 요청 방지 ──────────────────────────────────────


def test_duplicate_approval_request(task_path, token_path):
    _seed_task(task_path)

    r1 = email_task_approval.request_approval("etask-test001", token_path=token_path, task_path=task_path)
    r2 = email_task_approval.request_approval("etask-test001", token_path=token_path, task_path=task_path)

    assert r1["status"] == "created"
    assert r2["status"] == "duplicate"
    assert r2["token_id"] == r1["token_id"]

    # 토큰 파일에 1개만 존재해야 함
    tokens = json.loads(Path(token_path).open(encoding="utf-8").read())
    task_tokens = [e for e in tokens.values() if e["task_id"] == "etask-test001"]
    assert len(task_tokens) == 1


# ── 3. 없는 task 거절 ─────────────────────────────────────────────────────────


def test_not_found_task(task_path, token_path):
    result = email_task_approval.request_approval(
        "etask-nonexistent",
        token_path=token_path,
        task_path=task_path,
    )
    assert result["status"] == "not_found"
    assert result["task_id"] == "etask-nonexistent"

    # 토큰 파일이 생성되지 않아야 함
    assert not Path(token_path).exists()


# ── 4. approval_token_id 연결 검증 ────────────────────────────────────────────


def test_approval_token_id_linked_to_task(task_path, token_path):
    """email task에 approval_token_id 필드가 기록되는지 확인."""
    _seed_task(task_path)

    result = email_task_approval.request_approval("etask-test001", token_path=token_path, task_path=task_path)

    task = email_task_store.get_email_task("etask-test001", path=task_path)
    assert task is not None
    assert task.get("approval_token_id") == result["token_id"]
    assert task.get("approval_status") == "pending"
    assert "approval_requested_at" in task


def test_get_approval_for_task(task_path, token_path):
    """get_approval_for_task 가 token을 반환하는지 확인."""
    _seed_task(task_path)
    result = email_task_approval.request_approval("etask-test001", token_path=token_path, task_path=task_path)

    token = email_task_approval.get_approval_for_task("etask-test001", token_path=token_path)
    assert token is not None
    assert token["token_id"] == result["token_id"]
    assert token["task_id"] == "etask-test001"
    assert token["source"] == "email_task"


def test_get_approval_not_found(token_path):
    """approval 없는 task 조회 시 None 반환."""
    result = email_task_approval.get_approval_for_task("etask-ghost", token_path=token_path)
    assert result is None


# ── 5. 기존 approval 구조와 충돌 없음 ─────────────────────────────────────────


def test_no_conflict_with_existing_approval(task_path, token_path):
    """기존 approval_manager / task_store가 변경되지 않는지 확인."""
    import orchestrator_v1.tasks.approval_manager as approval_manager
    import orchestrator_v1.tasks.task_store as task_store

    before_task_store = dict(task_store._store)
    before_approval_store = dict(approval_manager._store)

    _seed_task(task_path)
    email_task_approval.request_approval("etask-test001", token_path=token_path, task_path=task_path)

    assert task_store._store == before_task_store
    assert approval_manager._store == before_approval_store


def test_email_approval_token_separate_from_main_tokens(task_path, token_path):
    """email approval token이 별도 파일에 저장되는지 확인."""
    _seed_task(task_path)
    email_task_approval.request_approval("etask-test001", token_path=token_path, task_path=task_path)

    # 지정한 token_path에만 저장됨
    assert Path(token_path).exists()

    # 메인 approval_tokens.json 파일 경로 확인 (ai_orchestrator/storage/ 아님)
    Path(token_path).parent.parent / "email_approval_tokens.json"
    # 테스트 token_path가 tmp_path이므로 메인 경로와 다름
    assert str(Path(token_path).resolve()) != email_task_approval._DEFAULT_TOKEN_PATH


# ── 6. 앱 부팅 가능 여부 ──────────────────────────────────────────────────────


def test_app_boot_with_approval_routes():
    """앱 부팅 시 신규 approval 라우트가 등록되는지 확인."""
    import os as _os

    _os.environ.setdefault("ORCH_DASHBOARD_USER", "test")
    _os.environ.setdefault("ORCH_DASHBOARD_PASSWORD", "test")

    from orchestrator_v1.monitoring.dashboard import create_app

    app = create_app()
    rules = {r.rule for r in app.url_map.iter_rules()}

    assert "/api/v1/tasks/<task_id>/approval-request" in rules
    assert "/api/v1/tasks/<task_id>" in rules
    assert "/api/v1/tasks/<task_id>/approval" in rules

    # 기존 라우트 유지 확인
    assert "/api/v1/inbox/candidates/<item_id>/task" in rules
    assert "/api/v1/inbox/tasks/<task_id>" in rules

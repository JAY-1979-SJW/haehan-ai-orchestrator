"""
candidate → task 승격 테스트
- candidate 1건 → task 생성 성공
- 동일 candidate 재생성 방지
- linked_task_id 연결 검증
- 없는 candidate 거절
- task_type 없는 candidate 거절
- 기존 task 정책과 충돌 없음
- 앱 부팅 가능 여부
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / ".."))

import orchestrator_v1.tasks.candidate_store as candidate_store
import orchestrator_v1.tasks.email_task_store as email_task_store
from orchestrator_v1.tasks import candidate_to_task

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def cand_path(tmp_path):
    return str(tmp_path / "candidates.jsonl")


@pytest.fixture
def task_path(tmp_path):
    return str(tmp_path / "email_tasks.jsonl")


def _seed_candidate(
    cand_path: str,
    item_id_suffix: str = "001",
    category: str = "sales",
    task_type: str = "quote_response",
    priority: str = "medium",
) -> str:
    """테스트용 candidate를 직접 삽입하고 item_id를 반환."""
    import hashlib

    ext_id = f"<test-{item_id_suffix}@test>"
    account = "jay@haehan-ai.kr"
    raw = f"{ext_id}:{account}"
    item_id = hashlib.sha256(raw.encode()).hexdigest()[:16]

    entry = {
        "item_id": item_id,
        "external_id": ext_id,
        "source_account": account,
        "category": category,
        "priority": priority,
        "needs_review": False,
        "candidate_task_type": task_type,
        "classification_reason": "test",
        "classified_at": "2026-04-22T10:00:00",
        "linked_task_id": None,
    }
    Path(cand_path).parent.mkdir(parents=True, exist_ok=True)
    with Path(cand_path).open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return item_id


# ── 1. candidate 1건 → task 생성 성공 ────────────────────────────────────────


def test_promote_success(cand_path, task_path):
    item_id = _seed_candidate(cand_path)

    result = candidate_to_task.promote(item_id, candidate_path=cand_path, task_path=task_path)

    assert result["status"] == "created"
    assert result["task_id"].startswith("etask-")
    assert result["item_id"] == item_id
    assert result["category"] == "sales"
    assert result["task_type"] == "quote_response"
    assert result["risk_level"] == "medium"


def test_promoted_task_is_pending(cand_path, task_path):
    item_id = _seed_candidate(cand_path)
    result = candidate_to_task.promote(item_id, candidate_path=cand_path, task_path=task_path)

    task = email_task_store.get_email_task(result["task_id"], path=task_path)
    assert task is not None
    assert task["status"] == "pending"
    assert task["source"] == "email_candidate"


def test_task_not_auto_executed(cand_path, task_path):
    """생성된 task가 executor의 실행 흐름에 진입하지 않는지 확인."""
    import orchestrator_v1.tasks.task_store as ts

    ts.clear()

    item_id = _seed_candidate(cand_path)
    candidate_to_task.promote(item_id, candidate_path=cand_path, task_path=task_path)

    # in-memory task_store에 등록되지 않아야 함
    assert ts.get(f"etask-{item_id}") is None
    assert len(ts._store) == 0


# ── 2. 동일 candidate 재승격 방지 ─────────────────────────────────────────────


def test_duplicate_promote_returns_existing_task_id(cand_path, task_path):
    item_id = _seed_candidate(cand_path)

    r1 = candidate_to_task.promote(item_id, candidate_path=cand_path, task_path=task_path)
    r2 = candidate_to_task.promote(item_id, candidate_path=cand_path, task_path=task_path)

    assert r1["status"] == "created"
    assert r2["status"] == "duplicate"
    assert r2["task_id"] == r1["task_id"]

    # email_tasks.jsonl에 1건만 저장되어야 함
    tasks = email_task_store.list_email_tasks(path=task_path)
    assert len(tasks) == 1


# ── 3. linked_task_id 연결 검증 ──────────────────────────────────────────────


def test_linked_task_id_written_to_candidate(cand_path, task_path):
    item_id = _seed_candidate(cand_path)
    result = candidate_to_task.promote(item_id, candidate_path=cand_path, task_path=task_path)

    cand = candidate_store.get_candidate(item_id, path=cand_path)
    assert cand is not None
    assert cand["linked_task_id"] == result["task_id"]
    assert "task_created_at" in cand


def test_task_has_linked_candidate_id(cand_path, task_path):
    item_id = _seed_candidate(cand_path)
    result = candidate_to_task.promote(item_id, candidate_path=cand_path, task_path=task_path)

    task = email_task_store.get_email_task(result["task_id"], path=task_path)
    assert task["linked_candidate_id"] == item_id
    assert task["source_item_id"] == item_id


# ── 4. 없는 candidate 거절 ────────────────────────────────────────────────────


def test_not_found_candidate(cand_path, task_path):
    result = candidate_to_task.promote("nonexistent-id", candidate_path=cand_path, task_path=task_path)
    assert result["status"] == "not_found"


# ── 5. task_type 없는 candidate 거절 ─────────────────────────────────────────


def test_no_task_type_rejected(cand_path, task_path):
    _seed_candidate(cand_path, task_type=None, item_id_suffix="002")

    # task_type=None으로 재삽입 (seed 함수가 None 삽입 불가하므로 직접 작성)
    import hashlib

    ext_id = "<test-no-type@test>"
    account = "jay@haehan-ai.kr"
    raw = f"{ext_id}:{account}"
    item_id2 = hashlib.sha256(raw.encode()).hexdigest()[:16]
    entry = {
        "item_id": item_id2,
        "external_id": ext_id,
        "source_account": account,
        "category": "general",
        "priority": "low",
        "needs_review": True,
        "candidate_task_type": None,
        "classification_reason": "general",
        "classified_at": "2026-04-22T10:00:00",
        "linked_task_id": None,
    }
    with Path(cand_path).open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    result = candidate_to_task.promote(item_id2, candidate_path=cand_path, task_path=task_path)
    assert result["status"] == "no_task_type"


# ── 6. operations → risk_level=high ──────────────────────────────────────────


def test_operations_category_risk_high(cand_path, task_path):
    item_id = _seed_candidate(cand_path, category="operations", task_type="ops_check", item_id_suffix="ops")
    result = candidate_to_task.promote(item_id, candidate_path=cand_path, task_path=task_path)

    assert result["status"] == "created"
    assert result["risk_level"] == "high"

    task = email_task_store.get_email_task(result["task_id"], path=task_path)
    assert task["risk_level"] == "high"


# ── 7. 기존 task 정책과 충돌 없음 ─────────────────────────────────────────────


def test_no_conflict_with_existing_policy():
    """기존 approval_manager / task_store가 변경되지 않았는지 확인."""
    import orchestrator_v1.tasks.approval_manager as approval_manager
    import orchestrator_v1.tasks.task_store as task_store

    before_store = dict(task_store._store)
    before_approval = dict(approval_manager._store)

    # promote 수행 (독립 tmp 파일 사용)
    import tempfile

    cp = tempfile.mktemp(suffix="_c.jsonl")
    tp = tempfile.mktemp(suffix="_t.jsonl")
    item_id = _seed_candidate(cp, item_id_suffix="policy")
    candidate_to_task.promote(item_id, candidate_path=cp, task_path=tp)

    assert task_store._store == before_store
    assert approval_manager._store == before_approval


# ── 8. JSONL 포맷 검증 ────────────────────────────────────────────────────────


def test_email_task_jsonl_format(cand_path, task_path):
    item_id = _seed_candidate(cand_path)
    candidate_to_task.promote(item_id, candidate_path=cand_path, task_path=task_path)

    with Path(task_path).open(encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]  # noqa: E741
    assert len(lines) == 1

    parsed = json.loads(lines[0])
    required = {
        "task_id",
        "source",
        "source_item_id",
        "category",
        "priority",
        "task_type",
        "title",
        "status",
        "risk_level",
        "created_at",
        "linked_candidate_id",
    }
    assert required.issubset(parsed.keys())
    assert parsed["status"] == "pending"
    assert parsed["source"] == "email_candidate"


# ── 9. 앱 부팅 + 신규 라우트 등록 확인 ───────────────────────────────────────


def test_app_boot_with_promote_routes():
    import os as _os

    _os.environ.setdefault("ORCH_DASHBOARD_USER", "test")
    _os.environ.setdefault("ORCH_DASHBOARD_PASSWORD", "test")

    from orchestrator_v1.monitoring.dashboard import create_app

    app = create_app()
    rules = {r.rule for r in app.url_map.iter_rules()}

    assert "/api/v1/inbox/candidates/<item_id>/task" in rules
    assert "/api/v1/inbox/tasks/<task_id>" in rules

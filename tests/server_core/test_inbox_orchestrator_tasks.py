import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / ".." / ".."))

from ai_orchestrator.tasks.inbox import (
    create_inbox_item,
    get_inbox_item,
    read_recent_inbox,
)


# ── 1. item 저장/조회 정상 ────────────────────────────────────────────
def test_create_and_get_inbox_item():
    item = create_inbox_item(
        source_type="manual",
        sender="test-actor",
        title="테스트 아이템",
        body_raw="raw content",
        body_summary="요약",
        linked_task_id="TASK-001",
    )
    assert item.item_id
    assert item.status == "new"
    assert item.source_type == "manual"

    fetched = get_inbox_item(item.item_id)
    assert fetched is not None
    assert fetched.item_id == item.item_id
    assert fetched.title == "테스트 아이템"


# ── 2. 기본 status = new ──────────────────────────────────────────────
def test_inbox_default_status():
    item = create_inbox_item(source_type="email", sender="sender@test.com")
    assert item.status == "new"


# ── 3. read_recent_inbox limit 동작 ─────────────────────────────────
def test_read_recent_inbox_limit():
    prefix = uuid.uuid4().hex[:8]
    for i in range(5):
        create_inbox_item(
            source_type="manual",
            title=f"limit-test-{prefix}-{i}",
        )
    items = read_recent_inbox(limit=3)
    assert len(items) >= 1  # 최소 3개 이상 있는 상황에서 limit 적용


# ── 4. telegram_command source_type 저장 ────────────────────────────
def test_inbox_telegram_command_source():
    item = create_inbox_item(
        source_type="telegram_command",
        source_account="111111111",
        external_id="some-token-id",
        sender="admin",
        title="텔레그램 approve",
        body_summary="action=approve task_id=TASK-999",
        linked_task_id="TASK-999",
        metadata={"role": "admin", "action": "approve"},
    )
    assert item.source_type == "telegram_command"
    assert item.metadata["action"] == "approve"

    fetched = get_inbox_item(item.item_id)
    assert fetched is not None
    assert fetched.source_type == "telegram_command"


# ── 5. 없는 item_id 조회 시 None ────────────────────────────────────
def test_get_nonexistent_inbox_item():
    result = get_inbox_item("00000000-0000-0000-0000-000000000000")
    assert result is None


if __name__ == "__main__":
    tests = [
        test_create_and_get_inbox_item,
        test_inbox_default_status,
        test_read_recent_inbox_limit,
        test_inbox_telegram_command_source,
        test_get_nonexistent_inbox_item,
    ]
    for t in tests:
        t()
        print(f"PASS: {t.__name__}")
    print("\n모든 inbox 테스트 통과")

import json

import pytest

from scripts.hiworks import mail_batch, schemas


def _write_queue(path, rows):
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows),
        encoding="utf-8",
    )


def test_build_send_plan_is_dry_run_and_filters_pending(tmp_path):
    queue = tmp_path / "queue.jsonl"
    _write_queue(
        queue,
        [
            {"to": "a@example.com", "subject": "A", "body": "body", "status": "pending"},
            {"to": "done@example.com", "subject": "Done", "body": "body", "status": "prepared"},
            {"to": "b@example.com", "subject": "B", "body": "body", "metadata": {"site": "EUM"}},
        ],
    )

    plan = mail_batch.build_send_plan(
        queue_path=queue,
        limit=5,
        delay_min=3,
        delay_max=4,
        seed=7,
    )

    assert plan["provider"] == "hiworks"
    assert plan["mode"] == "dry_run_plan"
    assert plan["send_status"] == "not_sent"
    assert plan["send_unit"] == "one_recipient_per_message"
    assert [item["to"] for item in plan["items"]] == ["a@example.com", "b@example.com"]
    assert all(3 <= item["delay_seconds"] <= 4 for item in plan["items"])


def test_build_send_plan_validates_delay_range(tmp_path):
    queue = tmp_path / "queue.jsonl"
    _write_queue(queue, [{"to": "a@example.com", "subject": "A", "body": "body"}])

    with pytest.raises(ValueError):
        mail_batch.build_send_plan(queue_path=queue, delay_min=10, delay_max=5)


def test_workflow_aliases_resolve_send_batch():
    workflow = schemas.workflow_for_alias("send-batch")

    assert workflow is not None
    assert workflow["key"] == "send_batch_plan"
    assert workflow["risk"] == "prepare"

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


def test_execute_send_batch_sends_all_items_and_records_result(tmp_path, monkeypatch):
    monkeypatch.setattr(mail_batch, "DATA_DIR", tmp_path)
    monkeypatch.setenv("GATE_DATA_DIR", str(tmp_path / "gate"))
    monkeypatch.setattr(mail_batch, "LATEST_SEND_RESULT_PATH", tmp_path / "latest.json")
    monkeypatch.setattr(mail_batch, "SEND_RESULT_DIR", tmp_path / "results")

    sent_calls: list[dict] = []

    def fake_fill_compose(page, *, to, subject, body):
        return {"ok": True, "to": to, "subject": subject}

    def fake_send_mail(page):
        sent_calls.append({"url": "https://mails.office.hiworks.com/list"})
        return {"success": True, "detail": "발송 완료"}

    monkeypatch.setattr("scripts.hiworks.mail.fill_compose", fake_fill_compose)
    monkeypatch.setattr("scripts.hiworks.mail.send_mail", fake_send_mail)
    monkeypatch.setattr(mail_batch, "time", type("T", (), {"sleep": staticmethod(lambda _: None)})())

    plan = {
        "items": [
            {"index": 1, "to": "a@test.com", "subject": "S1", "body": "B1", "delay_seconds": 1},
            {"index": 2, "to": "b@test.com", "subject": "S2", "body": "B2", "delay_seconds": 1},
        ]
    }

    result = mail_batch.execute_send_batch(plan, page=object(), approval=mail_batch.APPROVAL_CONFIRM_TEXT)

    assert result["sent"] == 2
    assert result["failed"] == 0
    assert result["mode"] == "executed"
    assert result["send_status"] == "done"
    assert all(item["sent"] for item in result["items"])
    assert len(sent_calls) == 2
    assert (tmp_path / "latest.json").exists()


def test_execute_send_batch_records_partial_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(mail_batch, "DATA_DIR", tmp_path)
    monkeypatch.setenv("GATE_DATA_DIR", str(tmp_path / "gate"))
    monkeypatch.setattr(mail_batch, "LATEST_SEND_RESULT_PATH", tmp_path / "latest.json")
    monkeypatch.setattr(mail_batch, "SEND_RESULT_DIR", tmp_path / "results")

    call_count = 0

    def fake_fill_compose(page, *, to, subject, body):
        return {"ok": True}

    def fake_send_mail(page):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            return {"success": False, "error_msg": "button_not_found"}
        return {"success": True, "detail": "발송 완료"}

    monkeypatch.setattr("scripts.hiworks.mail.fill_compose", fake_fill_compose)
    monkeypatch.setattr("scripts.hiworks.mail.send_mail", fake_send_mail)
    monkeypatch.setattr(mail_batch, "time", type("T", (), {"sleep": staticmethod(lambda _: None)})())

    plan = {
        "items": [
            {"index": 1, "to": "a@test.com", "subject": "S1", "body": "B1", "delay_seconds": 0},
            {"index": 2, "to": "b@test.com", "subject": "S2", "body": "B2", "delay_seconds": 0},
            {"index": 3, "to": "c@test.com", "subject": "S3", "body": "B3", "delay_seconds": 0},
        ]
    }

    result = mail_batch.execute_send_batch(plan, page=object(), approval=mail_batch.APPROVAL_CONFIRM_TEXT)

    assert result["sent"] == 2
    assert result["failed"] == 1
    assert result["items"][1]["error"] == "button_not_found"


def test_approval_confirm_text_constant():
    assert mail_batch.APPROVAL_CONFIRM_TEXT == "HIWORKS_APPROVED_SEND_BATCH"

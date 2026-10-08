import json

from scripts.hiworks import workflows


def _write_queue(path, rows):
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows),
        encoding="utf-8",
    )


def test_load_sales_queue_reads_jsonl_with_limit(tmp_path):
    queue = tmp_path / "sales.jsonl"
    _write_queue(
        queue,
        [
            {"to": "a@example.com", "subject": "A", "body": "body-a"},
            {"to": "b@example.com", "subject": "B", "body": "body-b"},
        ],
    )

    rows = workflows.load_sales_queue(queue, limit=1)

    assert rows == [{"to": "a@example.com", "subject": "A", "body": "body-a"}]


def test_prepare_sales_mail_fills_only_and_writes_latest(monkeypatch, tmp_path):
    queue = tmp_path / "sales.jsonl"
    _write_queue(
        queue,
        [
            {
                "to": "target@example.com",
                "subject": "Subject",
                "body": "Body",
                "metadata": {"project_name": "Project"},
            }
        ],
    )
    calls = []

    def fake_fill_compose(page, *, to, subject, body):
        calls.append({"page": page, "to": to, "subject": subject, "body": body})
        return {
            "ok": True,
            "to": to,
            "subject": subject,
            "sent": False,
            "note": "filled only",
        }

    monkeypatch.setattr(workflows, "DATA_DIR", tmp_path)
    monkeypatch.setattr(workflows, "fill_compose", fake_fill_compose)

    result, path = workflows.prepare_sales_mail(object(), index=1, queue_path=queue)

    assert result["sent"] is False
    assert calls[0]["to"] == "target@example.com"
    assert path == tmp_path / "hiworks_prepare_sales_mail_latest.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["metadata"] == {"project_name": "Project"}
    assert saved["sent"] is False

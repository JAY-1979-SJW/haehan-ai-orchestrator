import json

from tools import runtime_drift_watch as watch


def test_write_payload_writes_latest_and_history(tmp_path):
    latest = tmp_path / "latest.json"
    history = tmp_path / "history.jsonl"
    payload = {
        "schema_version": 1,
        "created_at": "2026-05-26T00:00:00+00:00",
        "workflow": "runtime_drift_watch",
        "ok": True,
        "status": "ok",
        "secret_values_output": False,
    }

    watch.write_payload(payload, latest=latest, history=history)

    assert json.loads(latest.read_text(encoding="utf-8"))["status"] == "ok"
    rows = [json.loads(line) for line in history.read_text(encoding="utf-8").splitlines()]
    assert rows == [payload]


def test_watch_failure_payload_is_redacted(monkeypatch, tmp_path):
    def fail(_args):
        raise RuntimeError("network unavailable")

    monkeypatch.setattr(watch, "build_payload", fail)
    latest = tmp_path / "latest.json"
    history = tmp_path / "history.jsonl"

    code = watch.main([
        "--latest",
        str(latest),
        "--history",
        str(history),
    ])

    payload = json.loads(latest.read_text(encoding="utf-8"))
    assert code == 1
    assert payload["status"] == "watch_failed"
    assert payload["secret_values_output"] is False
    assert payload["failed_check_ids"] == ["watch_execution_failed"]

import json

import pytest

from scripts.common import realtime_audit
from scripts.hiworks import run_log


@pytest.fixture(autouse=True)
def _isolate_realtime_audit(monkeypatch, tmp_path):
    monkeypatch.setattr(realtime_audit, "AUDIT_JSONL", tmp_path / "audit.jsonl")
    monkeypatch.setattr(realtime_audit, "AUDIT_TEXT", tmp_path / "audit.log")


def test_work_run_writes_success_record_and_audit_events(monkeypatch, tmp_path):
    monkeypatch.setattr(run_log, "RUNS_DIR", tmp_path / "runs")
    workflow = {
        "key": "send_batch_plan",
        "title": "Send plan",
        "risk": "prepare",
        "command": "cmd",
    }

    with run_log.work_run(workflow, ["2", "--dry-run"]):
        pass

    files = list((tmp_path / "runs" / "send_batch_plan").glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["status"] == "ok"
    assert data["args"] == ["2", "--dry-run"]

    events = [json.loads(line) for line in realtime_audit.AUDIT_JSONL.read_text(encoding="utf-8").splitlines()]
    assert [event["event_type"] for event in events] == [
        "HIWORKS_WORK_STARTED",
        "HIWORKS_WORK_COMPLETED",
    ]
    assert all(event["site"] == "hiworks" for event in events)


def test_work_run_writes_failure_record(monkeypatch, tmp_path):
    monkeypatch.setattr(run_log, "RUNS_DIR", tmp_path / "runs")
    workflow = {"key": "mail", "title": "Mail", "risk": "read"}

    with pytest.raises(RuntimeError), run_log.work_run(workflow):
        raise RuntimeError("boom")

    files = list((tmp_path / "runs" / "mail").glob("*.json"))
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["status"] == "failed"
    assert data["error"]["type"] == "RuntimeError"

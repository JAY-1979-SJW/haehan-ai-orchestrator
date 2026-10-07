import json

import pytest

from scripts.common import realtime_audit
from scripts.eum import run_log


@pytest.fixture(autouse=True)
def _isolate_realtime_audit(monkeypatch, tmp_path):
    monkeypatch.setattr(realtime_audit, "AUDIT_JSONL", tmp_path / "audit.jsonl")
    monkeypatch.setattr(realtime_audit, "AUDIT_TEXT", tmp_path / "audit.log")


def test_work_run_writes_success_record(monkeypatch, tmp_path):
    monkeypatch.setattr(run_log, "RUNS_DIR", tmp_path)
    workflow = {
        "key": "device_history",
        "title": "History",
        "risk": "read",
        "code": "WEBMAN400M00",
        "command": "cmd",
    }

    with run_log.work_run(workflow, ["DEVICE-001"]):
        pass

    files = list((tmp_path / "device_history").glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["status"] == "ok"
    assert data["args"] == ["DEVICE-001"]
    assert data["elapsed_ms"] >= 0


def test_work_run_writes_failure_record(monkeypatch, tmp_path):
    monkeypatch.setattr(run_log, "RUNS_DIR", tmp_path)
    workflow = {"key": "monitor", "title": "Monitor", "risk": "read"}

    with pytest.raises(ValueError), run_log.work_run(workflow):
        raise ValueError("boom")

    files = list((tmp_path / "monitor").glob("*.json"))
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["status"] == "failed"
    assert data["error"]["type"] == "ValueError"

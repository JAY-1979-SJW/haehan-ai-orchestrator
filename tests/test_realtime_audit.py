import json
from pathlib import Path
from uuid import uuid4

from scripts.common import realtime_audit
from scripts.eum import run_log


def _runtime_dir() -> Path:
    path = Path("data") / "test_runtime" / "realtime_audit" / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_emit_event_writes_jsonl_and_text(monkeypatch):
    base = _runtime_dir()
    jsonl = base / "audit.jsonl"
    text = base / "audit.log"
    monkeypatch.setattr(realtime_audit, "AUDIT_JSONL", jsonl)
    monkeypatch.setattr(realtime_audit, "AUDIT_TEXT", text)

    entry = realtime_audit.emit_event(
        "TEST_EVENT",
        site="eum",
        workflow="device_history",
        status="ok",
        metadata={"token": "secret-token-123", "visible": "yes"},
    )

    assert entry["metadata"]["token"] != "secret-token-123"
    data = json.loads(jsonl.read_text(encoding="utf-8").splitlines()[0])
    assert data["event_type"] == "TEST_EVENT"
    assert data["metadata"]["visible"] == "yes"
    assert "secret-token-123" not in jsonl.read_text(encoding="utf-8")
    assert "TEST_EVENT" in text.read_text(encoding="utf-8")


def test_read_recent_events_filters(monkeypatch):
    base = _runtime_dir()
    jsonl = base / "audit.jsonl"
    text = base / "audit.log"
    monkeypatch.setattr(realtime_audit, "AUDIT_JSONL", jsonl)
    monkeypatch.setattr(realtime_audit, "AUDIT_TEXT", text)

    realtime_audit.emit_event("A", site="eum")
    realtime_audit.emit_event("B", site="naver")
    realtime_audit.emit_event("B", site="eum")

    events = realtime_audit.read_recent_events(site="eum", event_type="B")

    assert len(events) == 1
    assert events[0]["site"] == "eum"
    assert events[0]["event_type"] == "B"


def test_eum_work_run_emits_realtime_audit(monkeypatch):
    base = _runtime_dir()
    monkeypatch.setattr(run_log, "RUNS_DIR", base / "runs")
    monkeypatch.setattr(realtime_audit, "AUDIT_JSONL", base / "audit.jsonl")
    monkeypatch.setattr(realtime_audit, "AUDIT_TEXT", base / "audit.log")

    workflow = {
        "key": "device_history",
        "title": "History",
        "risk": "read",
        "code": "WEBMAN400M00",
        "command": "cmd",
    }

    with run_log.work_run(workflow, ["DEVICE-001"]):
        pass

    events = [
        json.loads(line)
        for line in realtime_audit.AUDIT_JSONL.read_text(encoding="utf-8").splitlines()
    ]
    assert [event["event_type"] for event in events] == [
        "EUM_WORK_STARTED",
        "EUM_WORK_COMPLETED",
    ]
    assert events[0]["metadata"]["args"] == ["DEVICE-001"]

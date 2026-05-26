import json

from scripts.ops import runtime_event_watch as event_watch


def test_parse_event_action_from_docker_json_line():
    event = event_watch.parse_event(json.dumps({"Action": "start", "Type": "container"}))

    assert event_watch.event_action(event) == "start"


def test_write_event_payload_writes_latest_and_history(tmp_path):
    latest = tmp_path / "latest.json"
    history = tmp_path / "history.jsonl"
    payload = {
        "schema_version": 1,
        "created_at": "2026-05-26T00:00:00+00:00",
        "workflow": "runtime_event_watch",
        "ok": True,
        "status": "ok",
        "secret_values_output": False,
    }

    event_watch.write_payload(payload, latest=latest, history=history)

    assert json.loads(latest.read_text(encoding="utf-8"))["status"] == "ok"
    assert json.loads(history.read_text(encoding="utf-8").strip())["workflow"] == "runtime_event_watch"

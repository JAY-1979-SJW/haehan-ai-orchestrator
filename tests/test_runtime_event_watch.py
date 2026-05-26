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


def test_run_checks_includes_compose_project_boundary(monkeypatch, tmp_path):
    monkeypatch.setattr(event_watch, "ROOT", tmp_path)
    drift_latest = tmp_path / "data" / "runtime" / "runtime_drift_latest.json"
    drift_latest.parent.mkdir(parents=True)
    drift_latest.write_text(json.dumps({"ok": True, "status": "ok"}), encoding="utf-8")

    def fake_run(args, *, cwd=tmp_path, timeout=240):
        command = " ".join(str(item) for item in args)
        if "runtime_drift_watch.py" in command:
            return 0, "", ""
        if "verify_container_orphans.py" in command:
            return 0, json.dumps({"ok": True, "status": "ok", "untracked_in_container_count": 0}), ""
        if "verify_compose_project_boundary.py" in command:
            return 0, json.dumps({"ok": True, "status": "ok", "failed_check_ids": []}), ""
        return 1, "", "unexpected command"

    monkeypatch.setattr(event_watch, "run", fake_run)

    payload = event_watch.run_checks("haehan-ai-orchestrator-api")

    assert payload["ok"] is True
    assert payload["compose_project_boundary"]["ok"] is True

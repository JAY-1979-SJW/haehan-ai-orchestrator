import json

from scripts.ops import stress_orchestrator_boundary as stress


def test_stress_iteration_runs_expected_gates(monkeypatch):
    commands = []

    def fake_json_gate(args, *, name, timeout=240):
        commands.append((name, args))
        return {"name": name, "ok": True, "status": "ok"}

    monkeypatch.setattr(stress, "json_gate", fake_json_gate)
    monkeypatch.setattr(stress, "health_check", lambda url: {"name": "api_health", "ok": True})

    payload = stress.run_iteration("api", "http://127.0.0.1:8400/api/v1/health", 1)

    assert payload["ok"] is True
    assert [name for name, _ in commands] == [
        "compose_project_boundary",
        "container_orphans",
        "runtime_drift",
    ]


def test_stress_report_marks_failed_iteration(monkeypatch):
    results = [
        {"iteration": 1, "ok": True, "checks": []},
        {"iteration": 2, "ok": False, "checks": [{"name": "runtime_drift", "ok": False}]},
    ]

    monkeypatch.setattr(stress, "run_iteration", lambda container, health_url, iteration: results[iteration - 1])
    monkeypatch.setattr(stress.time, "sleep", lambda delay: None)
    args = stress.parse_args(["--iterations", "2", "--delay", "0"])

    payload = stress.stress(args)

    assert payload["ok"] is False
    assert payload["failed_iterations"] == [2]


def test_write_report_writes_json(tmp_path):
    report = tmp_path / "stress.json"
    payload = {"ok": True, "status": "ok", "secret_values_output": False}

    stress.write_report(payload, report)

    assert json.loads(report.read_text(encoding="utf-8"))["status"] == "ok"

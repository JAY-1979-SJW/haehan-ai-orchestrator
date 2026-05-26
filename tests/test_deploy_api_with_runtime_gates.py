import json

import pytest

from scripts.ops import deploy_api_with_runtime_gates as deploy_gate


def test_deploy_requires_explicit_approval():
    args = deploy_gate.parse_args([])

    with pytest.raises(RuntimeError, match="deployment_requires_--approved"):
        deploy_gate.deploy(args)


def test_write_report_creates_json_report(tmp_path):
    report = tmp_path / "runtime" / "deploy.json"
    payload = {
        "schema_version": 1,
        "workflow": "deploy_api_with_runtime_gates",
        "ok": True,
        "status": "ok",
        "secret_values_output": False,
    }

    deploy_gate.write_report(payload, report)

    written = json.loads(report.read_text(encoding="utf-8"))
    assert written["status"] == "ok"
    assert written["secret_values_output"] is False


def test_run_json_command_rejects_non_ok_payload(monkeypatch):
    def fake_run(args, *, timeout=240):
        return 0, json.dumps({"ok": False, "status": "failed", "secret_values_output": False}), ""

    monkeypatch.setattr(deploy_gate, "run", fake_run)

    with pytest.raises(RuntimeError) as exc_info:
        deploy_gate.run_json_command(["python", "gate.py"], step="test_gate")

    payload = json.loads(str(exc_info.value))
    assert payload["step"] == "test_gate"
    assert payload["payload"]["status"] == "failed"


def test_run_json_command_accepts_verdict_ok_payload(monkeypatch):
    def fake_run(args, *, timeout=240):
        return 0, json.dumps({"verdict": {"ok": True, "status": "ok"}}), ""

    monkeypatch.setattr(deploy_gate, "run", fake_run)

    payload = deploy_gate.run_json_command(["python", "drift.py"], step="runtime_drift")

    assert payload["ok"] is True
    assert payload["payload"]["verdict"]["ok"] is True


def test_wait_container_healthy_waits_until_docker_health_is_ready(monkeypatch):
    states = [
        {"State": {"Status": "running", "Health": {"Status": "starting"}}, "RestartCount": 0},
        {"State": {"Status": "running", "Health": {"Status": "healthy"}}, "RestartCount": 0},
    ]

    def fake_run(args, *, timeout=30):
        return 0, json.dumps([states.pop(0)]), ""

    monkeypatch.setattr(deploy_gate, "run", fake_run)
    monkeypatch.setattr(deploy_gate.time, "sleep", lambda delay: None)

    payload = deploy_gate.wait_container_healthy("api", attempts=2, delay=0)

    assert payload["ok"] is True
    assert payload["step"] == "container_health"
    assert payload["attempt"] == 2

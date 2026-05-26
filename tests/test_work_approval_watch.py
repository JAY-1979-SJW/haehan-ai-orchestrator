import json

from scripts.ops import work_approval_watch as watch


def test_baseline_status_requires_locked_approval_and_id(tmp_path):
    baseline = tmp_path / "baseline.md"
    baseline.write_text(
        "Status: LOCKED\nBaseline ID: TEST-1\nApproved by: user\n",
        encoding="utf-8",
    )

    payload = watch.baseline_status(baseline)

    assert payload["ok"] is True
    assert payload["status"] == "ok"


def test_scope_status_fails_for_out_of_scope_path():
    payload = watch.scope_status(
        ["scripts/ops/work_approval_watch.py", "scripts/google/router.py"],
        ["scripts/ops/", "tests/"],
    )

    assert payload["ok"] is False
    assert payload["out_of_scope_paths"] == ["scripts/google/router.py"]


def test_runtime_report_status_requires_ok_true(tmp_path):
    ok_report = tmp_path / "ok.json"
    fail_report = tmp_path / "fail.json"
    ok_report.write_text(json.dumps({"ok": True, "status": "ok"}), encoding="utf-8")
    fail_report.write_text(json.dumps({"ok": False, "status": "failed"}), encoding="utf-8")

    payload = watch.runtime_report_status([ok_report, fail_report])

    assert payload["ok"] is False
    assert payload["failed_check_ids"] == ["runtime_reports_not_ok"]


def test_write_payload_writes_latest_and_history(tmp_path):
    latest = tmp_path / "latest.json"
    history = tmp_path / "history.jsonl"
    payload = {"ok": True, "status": "ok", "secret_values_output": False}

    watch.write_payload(payload, latest=latest, history=history)

    assert json.loads(latest.read_text(encoding="utf-8"))["status"] == "ok"
    assert json.loads(history.read_text(encoding="utf-8").strip())["ok"] is True

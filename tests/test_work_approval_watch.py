import json
import subprocess
from unittest.mock import patch

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


def test_git_changed_paths_parses_porcelain_z_rename():
    out = " M docs/baseline/STANDARD_WORKFLOW.md\0R  old.py\0scripts/ops/new.py\0"
    completed = subprocess.CompletedProcess(
        args=["git"],
        returncode=0,
        stdout=out,
        stderr="",
    )
    with patch.object(watch.subprocess, "run", return_value=completed):
        paths = watch.git_changed_paths()

    assert paths == ["docs/baseline/STANDARD_WORKFLOW.md", "scripts/ops/new.py"]


def test_git_changed_paths_can_use_staged_source():
    out = "scripts/ops/work_approval_watch.py\0tests/test_work_approval_watch.py\0"
    completed = subprocess.CompletedProcess(
        args=["git"],
        returncode=0,
        stdout=out,
        stderr="",
    )
    with patch.object(watch.subprocess, "run", return_value=completed) as run:
        paths = watch.git_changed_paths(source="staged")

    assert paths == ["scripts/ops/work_approval_watch.py", "tests/test_work_approval_watch.py"]
    assert run.call_args.args[0] == ["git", "diff", "--cached", "--name-only", "-z"]


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


def test_work_record_status_requires_resumable_record(tmp_path):
    record = tmp_path / "ai_work_record_latest.json"
    record.write_text(
        json.dumps({
            "task_id": "TASK-1",
            "lane": "ops",
            "request_summary": "continue work",
            "approval_status": "approved",
            "status": "in_progress",
            "approved_scopes": ["scripts/ops/"],
            "resume_next_step": "run gate",
            "secret_values_output": False,
        }),
        encoding="utf-8",
    )

    payload = watch.work_record_status(record, lane="ops")

    assert payload["ok"] is True
    assert payload["lane"] == "ops"
    assert payload["resume_next_step"] == "run gate"


def test_work_record_status_fails_lane_mismatch(tmp_path):
    record = tmp_path / "ai_work_record_latest.json"
    record.write_text(
        json.dumps({
            "task_id": "TASK-1",
            "lane": "naver",
            "request_summary": "continue work",
            "approval_status": "approved",
            "status": "in_progress",
            "approved_scopes": ["scripts/naver_mail/"],
            "resume_next_step": "run gate",
            "secret_values_output": False,
        }),
        encoding="utf-8",
    )

    payload = watch.work_record_status(record, lane="ops")

    assert payload["ok"] is False
    assert "work_record_lane_mismatch" in payload["failed_check_ids"]

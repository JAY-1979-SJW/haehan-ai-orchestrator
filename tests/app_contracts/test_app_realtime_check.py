from pathlib import Path
from uuid import uuid4

from tools.runtime import app_realtime_check as check


def _runtime_dir() -> Path:
    path = Path("data") / "test_runtime" / "app_realtime_check" / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_check_audit_log_reports_stale_or_fresh(monkeypatch):
    audit = _runtime_dir() / "audit.jsonl"
    audit.write_text("x\n", encoding="utf-8")
    monkeypatch.setattr(check, "AUDIT_JSONL", audit)

    result = check.check_audit_log(max_age_seconds=3600)

    assert result["name"] == "audit_log_freshness"
    assert result["ok"] is True
    assert result["age_seconds"] is not None


def test_check_latest_dry_run_requires_ok_exit(monkeypatch):
    dry_run = _runtime_dir() / "latest.json"
    dry_run.write_text('{"status":"ok","exit_code":0,"scope":"security"}', encoding="utf-8")
    monkeypatch.setattr(check, "DRY_RUN_LATEST", dry_run)

    result = check.check_latest_dry_run()

    assert result["ok"] is True
    assert result["scope"] == "security"


def test_save_report_writes_latest_and_jsonl(monkeypatch):
    base = _runtime_dir()
    latest = base / "latest.json"
    jsonl = base / "checks.jsonl"
    monkeypatch.setattr(check, "LATEST_PATH", latest)
    monkeypatch.setattr(check, "JSONL_PATH", jsonl)
    monkeypatch.setattr(check, "LOG_DIR", base)

    report = {"schema_version": 1, "timestamp": "t", "status": "ok", "checks": []}
    check.save_report(report)

    assert latest.exists()
    assert jsonl.exists()
    assert '"status": "ok"' in latest.read_text(encoding="utf-8")


def test_check_worktree_index_reads_summary(monkeypatch):
    index = _runtime_dir() / "index.json"
    index.write_text('{"summary":{"changed_count":7}}', encoding="utf-8")
    monkeypatch.setattr(check, "WORKTREE_INDEX", index)

    result = check.check_worktree_index(max_age_seconds=3600)

    assert result["ok"] is True
    assert result["changed_count"] == 7

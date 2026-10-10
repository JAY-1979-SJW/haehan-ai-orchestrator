from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from tools.audits.app.audit_ai_work_session_gate import audit

ROOT = Path(__file__).resolve().parents[2]
SESSION = ROOT / "scripts" / "common" / "ai_work_session.py"


def test_ai_work_session_gate_audit_passes() -> None:
    ok, findings = audit()

    assert ok, findings


def repo_tmp(name: str) -> Path:
    path = ROOT / "tmp" / "ai_work_session_tests" / f"{name}-{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_ai_work_session_saves_lane_separated_record() -> None:
    record_root = repo_tmp("save")
    start = subprocess.run(
        [
            sys.executable,
            str(SESSION),
            "--record-root",
            str(record_root),
            "--lane",
            "google",
            "start",
            "--task-id",
            "google-001",
            "--summary",
            "google work",
            "--scope",
            "scripts/google/",
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    try:
        assert start.returncode == 0, start.stdout + start.stderr
        latest = record_root / "google" / "latest.json"
        history = record_root / "google" / "history.jsonl"
        index = record_root / "latest_lane.json"
        payload = json.loads(latest.read_text(encoding="utf-8"))

        assert latest.exists()
        assert history.exists()
        assert index.exists()
        assert payload["lane"] == "google"
        assert payload["resume_next_step"]
        assert payload["secret_values_output"] is False
    finally:
        shutil.rmtree(record_root, ignore_errors=True)


def test_ai_work_session_rejects_secret_shaped_text() -> None:
    record_root = repo_tmp("reject")
    result = subprocess.run(
        [
            sys.executable,
            str(SESSION),
            "--record-root",
            str(record_root),
            "--lane",
            "bad",
            "start",
            "--task-id",
            "bad-001",
            "--summary",
            "password=abc",
            "--scope",
            "docs/",
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    try:
        assert result.returncode != 0
    finally:
        shutil.rmtree(record_root, ignore_errors=True)

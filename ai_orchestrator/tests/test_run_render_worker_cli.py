"""F-4S-13 run_render_worker CLI 테스트."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.run_render_worker import main


def _write_plan(tmp_path: Path, items: list | None = None) -> Path:
    plan = {
        "generated_at": "2026-04-26T00:00:00Z",
        "ffmpeg_available": False,
        "render_items": items or [
            {
                "render_id": "render_001",
                "command_plan": {
                    "program": "ffmpeg",
                    "args": ["-i", "<planned>", "runs/video/render/output/out.mp4"],
                    "display": "ffmpeg ...",
                    "shell": False,
                    "planned_only": True,
                },
            }
        ],
    }
    p = tmp_path / "render_plan.json"
    p.write_text(json.dumps(plan), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# --execute 없으면 dry-run 유지
# ---------------------------------------------------------------------------


def test_cli_no_execute_is_dry_run(tmp_path):
    plan_path = _write_plan(tmp_path)
    out_dir = tmp_path / "worker_out"

    with patch("subprocess.run") as mock_run, \
         patch("sys.argv", ["run_render_worker.py",
                             "--render-plan", str(plan_path),
                             "--out-dir", str(out_dir),
                             "--json"]):
        rc = main()

    mock_run.assert_not_called()
    assert rc == 0

    result_files = list(out_dir.glob("render_worker_*.json"))
    assert len(result_files) == 1
    data = json.loads(result_files[0].read_text(encoding="utf-8"))
    assert data["dry_run"] is True
    assert data["executed_count"] == 0


# ---------------------------------------------------------------------------
# --execute 있어도 ffmpeg 없으면 blocked
# ---------------------------------------------------------------------------


def test_cli_execute_no_ffmpeg_blocked(tmp_path):
    plan_path = _write_plan(tmp_path)
    out_dir = tmp_path / "worker_out"

    with patch("shutil.which", return_value=None), \
         patch("subprocess.run") as mock_run, \
         patch("sys.argv", ["run_render_worker.py",
                             "--render-plan", str(plan_path),
                             "--out-dir", str(out_dir),
                             "--execute", "--json"]):
        rc = main()

    mock_run.assert_not_called()
    result_files = list(out_dir.glob("render_worker_*.json"))
    assert len(result_files) == 1
    data = json.loads(result_files[0].read_text(encoding="utf-8"))
    assert data["ffmpeg_available"] is False
    assert data["executed_count"] == 0
    assert data["blocked_count"] >= 1


# ---------------------------------------------------------------------------
# JSON/MD 파일 모두 생성
# ---------------------------------------------------------------------------


def test_cli_creates_json_and_md(tmp_path):
    plan_path = _write_plan(tmp_path)
    out_dir = tmp_path / "worker_out"

    with patch("sys.argv", ["run_render_worker.py",
                             "--render-plan", str(plan_path),
                             "--out-dir", str(out_dir)]):
        main()

    assert len(list(out_dir.glob("render_worker_*.json"))) == 1
    assert len(list(out_dir.glob("render_worker_*.md"))) == 1


# ---------------------------------------------------------------------------
# render plan 없으면 exit 1
# ---------------------------------------------------------------------------


def test_cli_missing_plan_exits_nonzero(tmp_path):
    with patch("sys.argv", ["run_render_worker.py",
                             "--render-plan", str(tmp_path / "no_such.json"),
                             "--out-dir", str(tmp_path / "out")]):
        rc = main()
    assert rc == 1

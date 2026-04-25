"""Tests for scripts/run_web_recording_worker.py CLI (F-4S-8a)."""
from __future__ import annotations

import importlib.util
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict

import pytest

from ai_orchestrator.video_production import recording_worker as rw


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CLI_PATH = _REPO_ROOT / "scripts" / "run_web_recording_worker.py"


def _load_cli_module():
    spec = importlib.util.spec_from_file_location("run_web_recording_worker_cli", _CLI_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cli():
    return _load_cli_module()


def _make_queue_file(tmp_path: Path, n_items: int = 2) -> Path:
    items = []
    for i in range(1, n_items + 1):
        rec_id = f"recording_{i:03d}"
        items.append({
            "recording_id": rec_id,
            "source_queue_id": f"video_{i:03d}",
            "status": "draft",
            "title": f"테스트 항목 {i}",
            "target_url": "http://localhost:3000",
            "viewport": {"name": "desktop", "width": 1440, "height": 900},
            "duration_seconds": 30,
            "duration_type": "short",
            "recording_steps": [
                {"step_no": 1, "type": "open_url", "url": "http://localhost:3000"},
                {"step_no": 2, "type": "wait", "wait_seconds": 2},
                {"step_no": 3, "type": "capture_scene", "duration_seconds": 10, "caption": "화면"},
                {"step_no": 4, "type": "overlay_caption", "captions": ["자막"]},
            ],
        })
    payload = {
        "generated_at": "2026-04-26T00:00:00Z",
        "recording_count": n_items,
        "allowed_step_types": list(rw.ALLOWED_STEP_TYPES),
        "forbidden_step_types": list(rw.FORBIDDEN_STEP_TYPES),
        "queue": items,
    }
    p = tmp_path / "web_recording_queue_test.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# parse_args
# ---------------------------------------------------------------------------


def test_parse_args_default_dry_run(cli):
    args = cli.parse_args(["--recording-queue", "dummy.json"])
    assert args.dry_run is True
    assert args.json is False
    assert args.max_items is None
    assert args.out_dir == cli.DEFAULT_OUT_DIR


def test_parse_args_max_items(cli):
    args = cli.parse_args(["--recording-queue", "dummy.json", "--max-items", "3"])
    assert args.max_items == 3


def test_parse_args_json_flag(cli):
    args = cli.parse_args(["--recording-queue", "dummy.json", "--json"])
    assert args.json is True


def test_parse_args_out_dir(cli):
    args = cli.parse_args(["--recording-queue", "dummy.json", "--out-dir", "custom/path"])
    assert args.out_dir == "custom/path"


# ---------------------------------------------------------------------------
# run function — basic
# ---------------------------------------------------------------------------


def test_run_basic(tmp_path: Path, cli):
    queue_file = _make_queue_file(tmp_path, n_items=2)
    args = cli.parse_args([
        "--recording-queue", str(queue_file),
        "--out-dir", str(tmp_path / "worker"),
        "--dry-run",
    ])
    result = cli.run(args)
    plan = result["plan"]
    assert plan["dry_run"] is True
    assert plan["total_items"] == 2
    assert plan["validated_count"] + plan["blocked_count"] == 2


def test_run_max_items(tmp_path: Path, cli):
    queue_file = _make_queue_file(tmp_path, n_items=5)
    args = cli.parse_args([
        "--recording-queue", str(queue_file),
        "--out-dir", str(tmp_path / "worker"),
        "--max-items", "2",
    ])
    result = cli.run(args)
    assert result["plan"]["total_items"] == 2


def test_run_creates_json_and_md(tmp_path: Path, cli):
    queue_file = _make_queue_file(tmp_path)
    args = cli.parse_args([
        "--recording-queue", str(queue_file),
        "--out-dir", str(tmp_path / "worker"),
    ])
    result = cli.run(args)
    files = result["files"]
    assert Path(files["json"]).exists()
    assert Path(files["md"]).exists()


def test_run_json_content_structure(tmp_path: Path, cli):
    queue_file = _make_queue_file(tmp_path)
    args = cli.parse_args([
        "--recording-queue", str(queue_file),
        "--out-dir", str(tmp_path / "worker"),
    ])
    result = cli.run(args)
    data = json.loads(Path(result["files"]["json"]).read_text(encoding="utf-8"))
    assert data["dry_run"] is True
    assert "items" in data
    assert "allowed_step_types" in data
    assert "forbidden_step_types" in data
    for forbidden in ("click", "fill", "type", "press"):
        assert forbidden in data["forbidden_step_types"]


def test_run_no_actual_mp4_created(tmp_path: Path, cli):
    queue_file = _make_queue_file(tmp_path)
    args = cli.parse_args([
        "--recording-queue", str(queue_file),
        "--out-dir", str(tmp_path / "worker"),
    ])
    result = cli.run(args)
    for item_plan in result["plan"]["items"]:
        mp4_path = Path(item_plan["output_video_path"])
        assert not mp4_path.exists(), f"실제 mp4가 생성됨 — dry-run 위반: {mp4_path}"


def test_run_missing_queue_file_raises(tmp_path: Path, cli):
    args = cli.parse_args([
        "--recording-queue", str(tmp_path / "nonexistent.json"),
        "--out-dir", str(tmp_path / "worker"),
    ])
    with pytest.raises(SystemExit):
        cli.run(args)


# ---------------------------------------------------------------------------
# stdout output
# ---------------------------------------------------------------------------


def test_main_stdout_text(tmp_path: Path, cli, monkeypatch):
    queue_file = _make_queue_file(tmp_path)
    monkeypatch.chdir(tmp_path)
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main([
            "--recording-queue", str(queue_file),
            "--out-dir", str(tmp_path / "worker"),
        ])
    out = buf.getvalue()
    assert code == 0
    assert "total_items" in out
    assert "validated_count" in out
    assert "dry_run" in out


def test_main_stdout_json(tmp_path: Path, cli, monkeypatch):
    queue_file = _make_queue_file(tmp_path)
    monkeypatch.chdir(tmp_path)
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main([
            "--recording-queue", str(queue_file),
            "--out-dir", str(tmp_path / "worker"),
            "--json",
        ])
    out = buf.getvalue()
    assert code == 0
    data = json.loads(out)
    assert data["dry_run"] is True
    assert data["total_items"] == 2


# ---------------------------------------------------------------------------
# No execute option
# ---------------------------------------------------------------------------


def test_no_execute_option_in_cli(cli):
    parser = cli.parse_args.__wrapped__ if hasattr(cli.parse_args, "__wrapped__") else None
    # --execute 옵션이 존재하지 않아야 함
    with pytest.raises(SystemExit):
        cli.parse_args(["--recording-queue", "dummy.json", "--execute"])


# ---------------------------------------------------------------------------
# Security: summary_payload has no secrets
# ---------------------------------------------------------------------------


def test_summary_payload_no_secrets(tmp_path: Path, cli):
    queue_file = _make_queue_file(tmp_path)
    args = cli.parse_args([
        "--recording-queue", str(queue_file),
        "--out-dir", str(tmp_path / "worker"),
    ])
    result = cli.run(args)
    serialized = json.dumps(result["summary_payload"], ensure_ascii=False)
    for tok in ("sk-", "AIza", "Bearer ", "client_secret", "Authorization:", "Cookie:"):
        assert tok not in serialized, f"secret-like token in summary: {tok}"

"""F-4S-12 build_render_plan CLI 테스트."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_EDIT_Q_PATH = next((_ROOT / "runs" / "video" / "edits").glob("video_edit_queue_*.json"), None)


def _run_cli(argv):
    from scripts.build_render_plan import main
    return main(argv)


def _make_minimal_edit_queue(tmp_path, n=2):
    items = []
    for i in range(1, n + 1):
        items.append({
            "edit_id": f"edit_{i:03d}",
            "title": f"테스트 항목 {i}",
            "source_video_path": f"/nonexistent/video_{i}.webm",
            "subtitle_srt_path": f"/nonexistent/sub_{i}.srt",
            "tts_expected_audio_path": f"/nonexistent/audio_{i}.wav",
            "output_video_path": str(tmp_path / "output" / f"edit_{i:03d}.mp4"),
            "review_required": False,
        })
    eq = {"edit_items": items}
    p = tmp_path / "edit_queue.json"
    p.write_text(json.dumps(eq, ensure_ascii=False), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# 기본 CLI 동작
# ---------------------------------------------------------------------------


def test_cli_creates_json_md(tmp_path):
    eq_path = _make_minimal_edit_queue(tmp_path)
    rc = _run_cli(["--edit-queue", str(eq_path), "--out-dir", str(tmp_path)])
    assert rc == 0
    assert list(tmp_path.glob("render_plan_*.json"))
    assert list(tmp_path.glob("render_plan_*.md"))


def test_cli_json_output(tmp_path, capsys):
    eq_path = _make_minimal_edit_queue(tmp_path)
    rc = _run_cli(["--edit-queue", str(eq_path), "--out-dir", str(tmp_path), "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert "total_items" in data
    assert data["total_items"] >= 1


def test_cli_json_planned_count(tmp_path, capsys):
    eq_path = _make_minimal_edit_queue(tmp_path, n=3)
    _run_cli(["--edit-queue", str(eq_path), "--out-dir", str(tmp_path), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["planned_count"] == 3
    assert data["blocked_count"] == 0


def test_cli_require_assets_blocks(tmp_path, capsys):
    eq_path = _make_minimal_edit_queue(tmp_path)
    _run_cli(["--edit-queue", str(eq_path), "--out-dir", str(tmp_path), "--require-assets", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["blocked_count"] >= 1


def test_cli_max_items(tmp_path, capsys):
    eq_path = _make_minimal_edit_queue(tmp_path, n=5)
    _run_cli(["--edit-queue", str(eq_path), "--out-dir", str(tmp_path), "--max-items", "2", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["total_items"] == 2


def test_cli_no_mp4_created(tmp_path):
    eq_path = _make_minimal_edit_queue(tmp_path)
    _run_cli(["--edit-queue", str(eq_path), "--out-dir", str(tmp_path)])
    assert len(list(tmp_path.rglob("*.mp4"))) == 0


def test_cli_sample_renders_in_output(tmp_path, capsys):
    eq_path = _make_minimal_edit_queue(tmp_path)
    _run_cli(["--edit-queue", str(eq_path), "--out-dir", str(tmp_path), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert "sample_renders" in data
    for r in data["sample_renders"]:
        assert "render_id" in r
        assert "command_display" in r
        assert r["command_display"].startswith("ffmpeg ")


def test_cli_notes_no_execution(tmp_path, capsys):
    eq_path = _make_minimal_edit_queue(tmp_path)
    _run_cli(["--edit-queue", str(eq_path), "--out-dir", str(tmp_path), "--json"])
    data = json.loads(capsys.readouterr().out)
    notes = " ".join(data.get("notes", []))
    assert "ffmpeg" in notes.lower() or "실행 없음" in notes


def test_cli_missing_edit_queue_arg(tmp_path):
    with pytest.raises(SystemExit):
        _run_cli(["--out-dir", str(tmp_path)])


# ---------------------------------------------------------------------------
# 실제 edit queue 파일 기반
# ---------------------------------------------------------------------------


@pytest.mark.skipif(_EDIT_Q_PATH is None, reason="edit queue not found")
def test_cli_from_real_edit_queue(tmp_path, capsys):
    rc = _run_cli(["--edit-queue", str(_EDIT_Q_PATH), "--out-dir", str(tmp_path), "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["total_items"] >= 1


# ---------------------------------------------------------------------------
# 보안 / 제약 검사 (정적)
# ---------------------------------------------------------------------------


def _cli_src():
    return (_ROOT / "scripts" / "build_render_plan.py").read_text(encoding="utf-8")


def test_cli_no_subprocess():
    src = _cli_src()
    assert "import subprocess" not in src and "subprocess.run" not in src


def test_cli_no_shell_true():
    src = _cli_src()
    assert "shell=True)" not in src and "shell = True" not in src


def test_cli_no_oauth():
    src = _cli_src()
    assert "import oauth" not in src.lower()


def test_cli_no_playwright():
    src = _cli_src()
    assert "import playwright" not in src.lower()
    assert "from playwright" not in src.lower()


def test_cli_no_upload():
    src = _cli_src()
    assert ".upload(" not in src.lower()

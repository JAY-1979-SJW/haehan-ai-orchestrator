"""F-4S-11 build_video_edit_queue CLI 테스트."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_FIXTURE = _ROOT / "samples" / "content_research_fixture.json"
_SUB_Q = next((_ROOT / "runs" / "video" / "subtitles").glob("subtitle_queue_*.json"), None)
_TTS_Q = next((_ROOT / "runs" / "video" / "tts").glob("tts_queue_*.json"), None)


def _run_cli(argv, capsys=None):
    from scripts.build_video_edit_queue import main
    return main(argv)


# ---------------------------------------------------------------------------
# fixture 기반
# ---------------------------------------------------------------------------


def test_cli_fixture_creates_json_md(tmp_path):
    rc = _run_cli(["--fixture", str(_FIXTURE), "--max-items", "2", "--out-dir", str(tmp_path)])
    assert rc == 0
    assert list(tmp_path.glob("video_edit_queue_*.json"))
    assert list(tmp_path.glob("video_edit_queue_*.md"))


def test_cli_fixture_json_output(tmp_path, capsys):
    rc = _run_cli([
        "--fixture", str(_FIXTURE), "--max-items", "2",
        "--out-dir", str(tmp_path), "--json",
    ])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert "edit_items_count" in data
    assert data["edit_items_count"] >= 1


def test_cli_fixture_max_items(tmp_path, capsys):
    _run_cli([
        "--fixture", str(_FIXTURE), "--max-items", "1",
        "--out-dir", str(tmp_path), "--json",
    ])
    data = json.loads(capsys.readouterr().out)
    assert data["edit_items_count"] == 1


def test_cli_fixture_sample_titles_have_layers(tmp_path, capsys):
    _run_cli([
        "--fixture", str(_FIXTURE), "--max-items", "2",
        "--out-dir", str(tmp_path), "--json",
    ])
    data = json.loads(capsys.readouterr().out)
    for s in data["sample_titles"]:
        assert "video" in s["timeline_layers"]


def test_cli_fixture_output_video_path_planned(tmp_path, capsys):
    _run_cli([
        "--fixture", str(_FIXTURE), "--max-items", "2",
        "--out-dir", str(tmp_path), "--json",
    ])
    data = json.loads(capsys.readouterr().out)
    for s in data["sample_titles"]:
        assert s["output_video_path"].endswith(".mp4")
        assert not Path(s["output_video_path"]).exists()


def test_cli_fixture_no_mp4_created(tmp_path):
    _run_cli(["--fixture", str(_FIXTURE), "--max-items", "2", "--out-dir", str(tmp_path)])
    mp4_files = list(tmp_path.rglob("*.mp4"))
    assert len(mp4_files) == 0


def test_cli_fixture_notes_contain_no_ffmpeg(tmp_path, capsys):
    _run_cli([
        "--fixture", str(_FIXTURE), "--max-items", "1",
        "--out-dir", str(tmp_path), "--json",
    ])
    data = json.loads(capsys.readouterr().out)
    notes_combined = " ".join(data.get("notes", []))
    assert "ffmpeg 실행 없음" in notes_combined or "ffmpeg" in notes_combined.lower()


# ---------------------------------------------------------------------------
# subtitle queue 기반
# ---------------------------------------------------------------------------


@pytest.mark.skipif(_SUB_Q is None, reason="subtitle queue not found")
def test_cli_subtitle_queue_creates_files(tmp_path):
    argv = ["--subtitle-queue", str(_SUB_Q), "--out-dir", str(tmp_path)]
    if _TTS_Q:
        argv += ["--tts-queue", str(_TTS_Q)]
    rc = _run_cli(argv)
    assert rc == 0
    assert list(tmp_path.glob("video_edit_queue_*.json"))


@pytest.mark.skipif(_SUB_Q is None, reason="subtitle queue not found")
def test_cli_subtitle_queue_json_output(tmp_path, capsys):
    argv = ["--subtitle-queue", str(_SUB_Q), "--out-dir", str(tmp_path), "--json"]
    if _TTS_Q:
        argv += ["--tts-queue", str(_TTS_Q)]
    _run_cli(argv)
    data = json.loads(capsys.readouterr().out)
    assert data["edit_items_count"] >= 1


# ---------------------------------------------------------------------------
# 보안 / 제약 검사 (정적)
# ---------------------------------------------------------------------------


def _cli_src():
    return (_ROOT / "scripts" / "build_video_edit_queue.py").read_text(encoding="utf-8")


def test_cli_no_ffmpeg_subprocess():
    src = _cli_src()
    assert "subprocess" not in src or "ffmpeg" not in src


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


def test_cli_no_ltx_api():
    src = _cli_src()
    assert "ltx_api" not in src.lower()


def test_cli_requires_source(tmp_path):
    with pytest.raises(SystemExit):
        _run_cli(["--out-dir", str(tmp_path)])

"""F-4S-9 build_subtitle_queue CLI 테스트."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_FIXTURE = _ROOT / "samples" / "content_research_fixture.json"
_VIDEO_QUEUE = _ROOT / "runs" / "video" / "video_queue_20260425_162052.json"


def _run_cli(argv, capsys=None):
    from scripts.build_subtitle_queue import main
    return main(argv)


# ---------------------------------------------------------------------------
# fixture 기반
# ---------------------------------------------------------------------------


def test_cli_fixture_creates_files(tmp_path):
    rc = _run_cli([
        "--fixture", str(_FIXTURE),
        "--max-items", "2",
        "--language", "ko",
        "--out-dir", str(tmp_path),
    ])
    assert rc == 0
    jsons = list(tmp_path.glob("subtitle_queue_*.json"))
    assert len(jsons) == 1
    mds = list(tmp_path.glob("subtitle_queue_*.md"))
    assert len(mds) == 1


def test_cli_fixture_creates_srt_vtt(tmp_path):
    _run_cli([
        "--fixture", str(_FIXTURE),
        "--max-items", "2",
        "--out-dir", str(tmp_path),
    ])
    srts = list(tmp_path.glob("*.srt"))
    vtts = list(tmp_path.glob("*.vtt"))
    assert len(srts) >= 1
    assert len(vtts) >= 1


def test_cli_fixture_max_items(tmp_path):
    _run_cli([
        "--fixture", str(_FIXTURE),
        "--max-items", "1",
        "--out-dir", str(tmp_path),
    ])
    srts = list(tmp_path.glob("subtitle_*.srt"))
    assert len(srts) == 1


def test_cli_fixture_json_output(tmp_path, capsys):
    rc = _run_cli([
        "--fixture", str(_FIXTURE),
        "--max-items", "2",
        "--out-dir", str(tmp_path),
        "--json",
    ])
    assert rc == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "subtitle_items_count" in data
    assert data["subtitle_items_count"] >= 1


def test_cli_fixture_srt_content_valid(tmp_path):
    _run_cli([
        "--fixture", str(_FIXTURE),
        "--max-items", "1",
        "--out-dir", str(tmp_path),
    ])
    srt = list(tmp_path.glob("*.srt"))[0].read_text(encoding="utf-8")
    assert "1\n" in srt
    assert " --> " in srt


def test_cli_fixture_vtt_content_valid(tmp_path):
    _run_cli([
        "--fixture", str(_FIXTURE),
        "--max-items", "1",
        "--out-dir", str(tmp_path),
    ])
    vtt = list(tmp_path.glob("*.vtt"))[0].read_text(encoding="utf-8")
    assert vtt.startswith("WEBVTT")
    assert " --> " in vtt


# ---------------------------------------------------------------------------
# video queue 기반
# ---------------------------------------------------------------------------


def test_cli_video_queue_creates_files(tmp_path):
    if not _VIDEO_QUEUE.exists():
        pytest.skip("video queue file not found")
    rc = _run_cli([
        "--video-queue", str(_VIDEO_QUEUE),
        "--max-items", "2",
        "--out-dir", str(tmp_path),
    ])
    assert rc == 0
    jsons = list(tmp_path.glob("subtitle_queue_*.json"))
    assert jsons


def test_cli_video_queue_json_output(tmp_path, capsys):
    if not _VIDEO_QUEUE.exists():
        pytest.skip("video queue file not found")
    rc = _run_cli([
        "--video-queue", str(_VIDEO_QUEUE),
        "--max-items", "3",
        "--out-dir", str(tmp_path),
        "--json",
    ])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["subtitle_items_count"] >= 1
    for s in data["sample_segments"]:
        assert s["segments_count"] > 0


# ---------------------------------------------------------------------------
# 보안 / 제약 검사 (정적)
# ---------------------------------------------------------------------------


def _cli_src():
    return (_ROOT / "scripts" / "build_subtitle_queue.py").read_text(encoding="utf-8")


def test_cli_no_tts_stt_call():
    src = _cli_src()
    for kw in ("tts_api", "stt_api", "openai.audio", "whisper.transcribe"):
        assert kw not in src.lower()


def test_cli_no_ltx_api():
    src = _cli_src()
    assert "ltx_api" not in src.lower()


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


def test_cli_no_click_fill():
    src = _cli_src()
    assert "page.click(" not in src
    assert "page.fill(" not in src


def test_cli_requires_source_arg(tmp_path):
    with pytest.raises(SystemExit):
        _run_cli(["--out-dir", str(tmp_path)])

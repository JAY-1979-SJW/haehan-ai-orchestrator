"""F-4S-10 build_tts_queue CLI 테스트."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_FIXTURE = _ROOT / "samples" / "content_research_fixture.json"
_SUBTITLE_QUEUE = next(
    (_ROOT / "runs" / "video" / "subtitles").glob("subtitle_queue_*.json"),
    None,
)
_SRT_FILE = _ROOT / "runs" / "video" / "subtitles" / "subtitle_001.srt"
_VTT_FILE = _ROOT / "runs" / "video" / "subtitles" / "subtitle_001.vtt"


def _run_cli(argv, capsys=None):
    from scripts.build_tts_queue import main
    return main(argv)


# ---------------------------------------------------------------------------
# fixture 기반
# ---------------------------------------------------------------------------


def test_cli_fixture_creates_json_md(tmp_path):
    rc = _run_cli(["--fixture", str(_FIXTURE), "--max-items", "2", "--out-dir", str(tmp_path)])
    assert rc == 0
    assert list(tmp_path.glob("tts_queue_*.json"))
    assert list(tmp_path.glob("tts_queue_*.md"))


def test_cli_fixture_json_output(tmp_path, capsys):
    rc = _run_cli([
        "--fixture", str(_FIXTURE), "--max-items", "2",
        "--out-dir", str(tmp_path), "--json",
    ])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert "tts_items_count" in data
    assert data["tts_items_count"] >= 1


def test_cli_fixture_max_items(tmp_path, capsys):
    _run_cli([
        "--fixture", str(_FIXTURE), "--max-items", "1",
        "--out-dir", str(tmp_path), "--json",
    ])
    data = json.loads(capsys.readouterr().out)
    assert data["tts_items_count"] == 1


def test_cli_fixture_voice_profile(tmp_path, capsys):
    _run_cli([
        "--fixture", str(_FIXTURE), "--max-items", "1",
        "--voice-profile", "ko_female_neutral",
        "--out-dir", str(tmp_path), "--json",
    ])
    data = json.loads(capsys.readouterr().out)
    assert data["voice_profile"] == "ko_female_neutral"


def test_cli_fixture_no_wav_created(tmp_path):
    _run_cli(["--fixture", str(_FIXTURE), "--max-items", "2", "--out-dir", str(tmp_path)])
    wav_files = list(tmp_path.rglob("*.wav"))
    assert len(wav_files) == 0, "실제 음성 파일이 생성되면 안 됨"


def test_cli_fixture_expected_audio_path_in_json(tmp_path, capsys):
    _run_cli([
        "--fixture", str(_FIXTURE), "--max-items", "1",
        "--out-dir", str(tmp_path), "--json",
    ])
    data = json.loads(capsys.readouterr().out)
    for s in data["sample_texts"]:
        assert s["expected_audio_path"].endswith(".wav")


# ---------------------------------------------------------------------------
# subtitle_queue 기반
# ---------------------------------------------------------------------------


@pytest.mark.skipif(_SUBTITLE_QUEUE is None, reason="subtitle queue JSON not found")
def test_cli_subtitle_queue_creates_files(tmp_path):
    rc = _run_cli([
        "--subtitle-queue", str(_SUBTITLE_QUEUE),
        "--max-items", "2", "--out-dir", str(tmp_path),
    ])
    assert rc == 0
    assert list(tmp_path.glob("tts_queue_*.json"))


# ---------------------------------------------------------------------------
# SRT 단독
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _SRT_FILE.exists(), reason="SRT file not found")
def test_cli_srt_creates_files(tmp_path):
    rc = _run_cli(["--srt", str(_SRT_FILE), "--out-dir", str(tmp_path)])
    assert rc == 0
    assert list(tmp_path.glob("tts_queue_*.json"))


@pytest.mark.skipif(not _SRT_FILE.exists(), reason="SRT file not found")
def test_cli_srt_json_output(tmp_path, capsys):
    _run_cli(["--srt", str(_SRT_FILE), "--out-dir", str(tmp_path), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["tts_items_count"] >= 1
    assert data["sample_texts"][0]["segments_count"] > 0


# ---------------------------------------------------------------------------
# VTT 단독
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _VTT_FILE.exists(), reason="VTT file not found")
def test_cli_vtt_creates_files(tmp_path):
    rc = _run_cli(["--vtt", str(_VTT_FILE), "--out-dir", str(tmp_path)])
    assert rc == 0


# ---------------------------------------------------------------------------
# 보안 / 제약 검사 (정적)
# ---------------------------------------------------------------------------


def _cli_src():
    return (_ROOT / "scripts" / "build_tts_queue.py").read_text(encoding="utf-8")


def test_cli_no_tts_api_call():
    src = _cli_src()
    for kw in ("openai.audio", "elevenlabs", "google.cloud.texttospeech"):
        assert kw not in src.lower()


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

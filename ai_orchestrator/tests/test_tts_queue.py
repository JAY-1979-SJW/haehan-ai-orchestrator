"""F-4S-10 tts_queue 단위 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ai_orchestrator.video_production.tts_queue import (
    normalize_tts_text,
    _split_long_sentence,
    _check_review,
    _check_warn,
    _check_secret,
    parse_srt,
    parse_vtt,
    extract_tts_segments,
    build_tts_queue,
    render_tts_queue_markdown,
    write_tts_queue_files,
    VALID_VOICE_PROFILES,
    DEFAULT_VOICE_PROFILE,
)

_SRT_FILE = _ROOT / "runs" / "video" / "subtitles" / "subtitle_001.srt"
_VTT_FILE = _ROOT / "runs" / "video" / "subtitles" / "subtitle_001.vtt"


# ---------------------------------------------------------------------------
# normalize_tts_text
# ---------------------------------------------------------------------------


def test_normalize_newline():
    assert "\n" not in normalize_tts_text("안녕\n하세요")


def test_normalize_ellipsis():
    result = normalize_tts_text("확인해야…")
    assert "…" not in result


def test_normalize_strip():
    assert normalize_tts_text("  텍스트  ") == "텍스트"


def test_normalize_multi_space():
    assert "  " not in normalize_tts_text("안녕  하세요")


# ---------------------------------------------------------------------------
# _split_long_sentence
# ---------------------------------------------------------------------------


def test_split_short_text_unchanged():
    text = "짧은 텍스트"
    assert _split_long_sentence(text) == [text]


def test_split_long_text():
    long = "이것은 매우 긴 문장입니다. 여기서 분할이 일어나야 합니다. 맞습니다."
    parts = _split_long_sentence(long)
    assert len(parts) >= 1
    for p in parts:
        assert p.strip()


# ---------------------------------------------------------------------------
# _check_review / _check_warn / _check_secret
# ---------------------------------------------------------------------------


def test_check_review_legal():
    assert _check_review("법령 제5조에 따라") is True


def test_check_review_safe():
    assert _check_review("소방공사 견적 안내") is False


def test_check_warn_exaggerated():
    warns = _check_warn("100% 무조건 보장됩니다")
    assert len(warns) > 0


def test_check_warn_clean():
    assert _check_warn("소방안전 핵심 정보") == []


def test_check_secret_api_key():
    secs = _check_secret("api_key=abc123")
    assert "api_key" in secs


def test_check_secret_clean():
    assert _check_secret("소방공사 정보") == []


# ---------------------------------------------------------------------------
# parse_srt
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _SRT_FILE.exists(), reason="SRT file not found")
def test_parse_srt_returns_list():
    segs = parse_srt(_SRT_FILE)
    assert isinstance(segs, list)
    assert len(segs) > 0


@pytest.mark.skipif(not _SRT_FILE.exists(), reason="SRT file not found")
def test_parse_srt_segment_keys():
    segs = parse_srt(_SRT_FILE)
    for seg in segs:
        assert "index" in seg
        assert "start_seconds" in seg
        assert "end_seconds" in seg
        assert "text" in seg


@pytest.mark.skipif(not _SRT_FILE.exists(), reason="SRT file not found")
def test_parse_srt_timestamps_numeric():
    segs = parse_srt(_SRT_FILE)
    for seg in segs:
        assert isinstance(seg["start_seconds"], float)
        assert isinstance(seg["end_seconds"], float)
        assert seg["end_seconds"] > seg["start_seconds"]


@pytest.mark.skipif(not _SRT_FILE.exists(), reason="SRT file not found")
def test_parse_srt_text_not_empty():
    segs = parse_srt(_SRT_FILE)
    for seg in segs:
        assert seg["text"].strip()


def test_parse_srt_from_string(tmp_path):
    srt = tmp_path / "test.srt"
    srt.write_text(
        "1\n00:00:00,000 --> 00:00:03,500\n안녕하세요\n\n2\n00:00:03,500 --> 00:00:07,000\n테스트 문장\n",
        encoding="utf-8",
    )
    segs = parse_srt(srt)
    assert len(segs) == 2
    assert segs[0]["start_seconds"] == 0.0
    assert abs(segs[0]["end_seconds"] - 3.5) < 0.01
    assert segs[0]["text"] == "안녕하세요"


# ---------------------------------------------------------------------------
# parse_vtt
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _VTT_FILE.exists(), reason="VTT file not found")
def test_parse_vtt_returns_list():
    segs = parse_vtt(_VTT_FILE)
    assert len(segs) > 0


@pytest.mark.skipif(not _VTT_FILE.exists(), reason="VTT file not found")
def test_parse_vtt_segment_structure():
    segs = parse_vtt(_VTT_FILE)
    for seg in segs:
        assert "start_seconds" in seg and "end_seconds" in seg and "text" in seg


def test_parse_vtt_from_string(tmp_path):
    vtt = tmp_path / "test.vtt"
    vtt.write_text(
        "WEBVTT\n\n00:00:00.000 --> 00:00:04.000\n소방안전\n\n00:00:04.000 --> 00:00:08.000\n건설 정보\n",
        encoding="utf-8",
    )
    segs = parse_vtt(vtt)
    assert len(segs) == 2
    assert segs[0]["text"] == "소방안전"
    assert abs(segs[1]["start_seconds"] - 4.0) < 0.01


# ---------------------------------------------------------------------------
# extract_tts_segments
# ---------------------------------------------------------------------------


def _make_subtitle_item(**kwargs):
    base = {
        "subtitle_id": "subtitle_001",
        "source_queue_id": "video_001",
        "title": "소방안전 핵심 정보",
        "language": "ko",
        "duration_seconds": 30,
        "review_required": False,
        "warnings": [],
        "segments": [
            {"index": 1, "start_seconds": 0.0, "end_seconds": 4.5, "text": "왜 소방안전인가?", "source": "hook", "review_required": False},
            {"index": 2, "start_seconds": 4.5, "end_seconds": 9.0, "text": "핵심 수치 3가지", "source": "scene_caption", "review_required": False},
            {"index": 3, "start_seconds": 9.0, "end_seconds": 30.0, "text": "실천 방법", "source": "scene_caption", "review_required": False},
        ],
    }
    base.update(kwargs)
    return base


def test_extract_tts_segments_count():
    item = _make_subtitle_item()
    segs = extract_tts_segments(item)
    assert len(segs) == 3


def test_extract_tts_segments_voice_profile():
    item = _make_subtitle_item()
    segs = extract_tts_segments(item, voice_profile="ko_female_neutral")
    for seg in segs:
        assert seg["voice_profile"] == "ko_female_neutral"


def test_extract_tts_segments_segment_id_format():
    item = _make_subtitle_item()
    segs = extract_tts_segments(item)
    for seg in segs:
        assert seg["segment_id"].startswith("tts_")
        assert "_" in seg["segment_id"]


def test_extract_tts_segments_tone_hook():
    item = _make_subtitle_item()
    segs = extract_tts_segments(item)
    assert segs[0]["tone"] == "informative"


def test_extract_tts_segments_review_propagated():
    item = _make_subtitle_item(segments=[
        {"index": 1, "start_seconds": 0.0, "end_seconds": 5.0,
         "text": "법령 기준 반드시 확인", "source": "hook", "review_required": True},
    ])
    segs = extract_tts_segments(item)
    assert segs[0]["review_required"] is True


def test_extract_tts_segments_secret_warning():
    item = _make_subtitle_item(segments=[
        {"index": 1, "start_seconds": 0.0, "end_seconds": 5.0,
         "text": "api_key=secret123", "source": "hook", "review_required": False},
    ])
    segs = extract_tts_segments(item)
    assert any("secret_keyword" in w for w in segs[0]["warnings"])


def test_extract_tts_segments_text_normalized():
    item = _make_subtitle_item(segments=[
        {"index": 1, "start_seconds": 0.0, "end_seconds": 5.0,
         "text": "안녕\n하세요…", "source": "hook", "review_required": False},
    ])
    segs = extract_tts_segments(item)
    assert "\n" not in segs[0]["text"]
    assert "…" not in segs[0]["text"]


# ---------------------------------------------------------------------------
# build_tts_queue
# ---------------------------------------------------------------------------


def test_build_tts_queue_basic():
    items = [_make_subtitle_item()]
    q = build_tts_queue(items)
    assert q["total_items"] == 1
    assert q["tts_items"][0]["tts_id"] == "tts_001"


def test_build_tts_queue_max_items():
    items = [_make_subtitle_item() for _ in range(10)]
    q = build_tts_queue(items, max_items=3)
    assert q["total_items"] == 3


def test_build_tts_queue_invalid_voice_profile():
    items = [_make_subtitle_item()]
    q = build_tts_queue(items, voice_profile="invalid_profile")
    assert q["voice_profile"] == DEFAULT_VOICE_PROFILE


def test_build_tts_queue_expected_audio_path():
    items = [_make_subtitle_item()]
    q = build_tts_queue(items, output_dir=Path("runs/video/tts"))
    path = q["tts_items"][0]["expected_audio_path"]
    assert path.endswith(".wav")
    assert "tts_001" in path


def test_build_tts_queue_no_actual_file_created():
    items = [_make_subtitle_item()]
    q = build_tts_queue(items, output_dir=Path("runs/video/tts"))
    audio_path = Path(q["tts_items"][0]["expected_audio_path"])
    assert not audio_path.exists(), "expected_audio_path must NOT be created (plan only)"


def test_build_tts_queue_voice_profile_set():
    items = [_make_subtitle_item()]
    q = build_tts_queue(items, voice_profile="ko_female_friendly")
    assert q["tts_items"][0]["voice_profile"] == "ko_female_friendly"


def test_build_tts_queue_notes_no_api_call():
    items = [_make_subtitle_item()]
    q = build_tts_queue(items)
    notes_combined = " ".join(q["notes"])
    assert "TTS API 호출 없음" in notes_combined or "실제 TTS" in notes_combined


# ---------------------------------------------------------------------------
# write_tts_queue_files
# ---------------------------------------------------------------------------


def test_write_tts_queue_files(tmp_path):
    items = [_make_subtitle_item(), _make_subtitle_item(subtitle_id="subtitle_002")]
    q = build_tts_queue(items, output_dir=tmp_path)
    files = write_tts_queue_files(q, tmp_path, timestamp="20260101_000000")
    assert files["json"].exists()
    assert files["md"].exists()
    assert files["json"].stat().st_size > 0
    md_content = files["md"].read_text(encoding="utf-8")
    assert "TTS 큐 PoC" in md_content


def test_write_tts_queue_no_audio_file(tmp_path):
    items = [_make_subtitle_item()]
    q = build_tts_queue(items, output_dir=tmp_path)
    write_tts_queue_files(q, tmp_path, timestamp="20260101_000001")
    wav_files = list(tmp_path.glob("*.wav"))
    assert len(wav_files) == 0, "실제 음성 파일이 생성되면 안 됨"


# ---------------------------------------------------------------------------
# valid voice profiles
# ---------------------------------------------------------------------------


def test_valid_voice_profiles_exist():
    assert "ko_male_neutral" in VALID_VOICE_PROFILES
    assert "ko_female_neutral" in VALID_VOICE_PROFILES
    assert "ko_male_energetic" in VALID_VOICE_PROFILES
    assert "ko_female_friendly" in VALID_VOICE_PROFILES


# ---------------------------------------------------------------------------
# 보안 / 제약 검사 (정적)
# ---------------------------------------------------------------------------


def _module_src():
    return (_ROOT / "ai_orchestrator" / "video_production" / "tts_queue.py").read_text(encoding="utf-8")


def test_no_playwright_import():
    src = _module_src()
    assert "import playwright" not in src.lower()
    assert "from playwright" not in src.lower()


def test_no_oauth_import():
    src = _module_src()
    assert "import oauth" not in src.lower()


def test_no_tts_api_call():
    src = _module_src()
    for kw in ("openai.audio", "elevenlabs", "google.cloud.texttospeech", "azure.cognitiveservices.speech"):
        assert kw not in src.lower()


def test_no_upload_call():
    src = _module_src()
    assert ".upload(" not in src.lower()


def test_no_ltx_api():
    src = _module_src()
    assert "ltx_api" not in src.lower()

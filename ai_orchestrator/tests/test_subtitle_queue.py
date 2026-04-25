"""F-4S-9 subtitle_queue 단위 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ai_orchestrator.video_production.subtitle_queue import (
    format_srt_timestamp,
    format_vtt_timestamp,
    build_subtitle_segments,
    render_srt,
    render_vtt,
    build_subtitle_queue,
    extract_video_queue_items,
    extract_recording_metadata,
    write_subtitle_queue_files,
    _distribute_times,
    _check_review,
)
import pytest


# ---------------------------------------------------------------------------
# timestamp format
# ---------------------------------------------------------------------------


def test_srt_timestamp_zero():
    assert format_srt_timestamp(0.0) == "00:00:00,000"


def test_srt_timestamp_basic():
    assert format_srt_timestamp(3.5) == "00:00:03,500"


def test_srt_timestamp_minute():
    assert format_srt_timestamp(65.0) == "00:01:05,000"


def test_srt_timestamp_hour():
    assert format_srt_timestamp(3661.25) == "01:01:01,250"


def test_vtt_timestamp_dot():
    ts = format_vtt_timestamp(3.5)
    assert "." in ts
    assert "," not in ts
    assert ts == "00:00:03.500"


def test_vtt_starts_with_webvtt():
    segments = [{"index": 1, "start_seconds": 0.0, "end_seconds": 3.0, "text": "테스트"}]
    vtt = render_vtt(segments)
    assert vtt.startswith("WEBVTT")


# ---------------------------------------------------------------------------
# distribute_times
# ---------------------------------------------------------------------------


def test_distribute_times_count():
    slots = _distribute_times(4, 30.0)
    assert len(slots) == 4


def test_distribute_times_start_zero():
    slots = _distribute_times(3, 30.0)
    assert slots[0][0] == 0.0


def test_distribute_times_end_equals_total():
    total = 30.0
    slots = _distribute_times(5, total)
    assert abs(slots[-1][1] - total) < 0.01


def test_distribute_times_monotonic():
    slots = _distribute_times(6, 30.0)
    for i in range(len(slots) - 1):
        assert slots[i][1] <= slots[i + 1][0] + 0.001


def test_distribute_times_min_duration():
    slots = _distribute_times(10, 30.0)
    for start, end in slots:
        assert end - start >= 2.4  # SEG_MIN_SEC with float tolerance


# ---------------------------------------------------------------------------
# build_subtitle_segments
# ---------------------------------------------------------------------------


def _make_vitem(**kwargs):
    base = {
        "queue_id": "test_001",
        "title": "소방안전 핵심 정보",
        "hook": "왜 소방안전이 중요한가?",
        "duration_type": "short",
        "scene_plan": [
            {"scene_no": 1, "purpose": "문제 제기", "caption": "소방안전 현황", "narration": "소방안전 현황을 알아봅니다."},
            {"scene_no": 2, "purpose": "핵심 정보", "caption": "핵심 수치 3가지", "narration": "3가지 핵심 수치를 소개합니다."},
            {"scene_no": 3, "purpose": "마무리", "caption": "실천 방법", "narration": "실천 방법을 정리합니다."},
        ],
        "subtitle_points": ["소방 점검 필수", "비상구 확인"],
        "risk_notes": [],
        "review_required": False,
    }
    base.update(kwargs)
    return base


def test_segments_not_empty():
    vitem = _make_vitem()
    segs = build_subtitle_segments(vitem)
    assert len(segs) > 0


def test_segments_index_sequential():
    segs = build_subtitle_segments(_make_vitem())
    for i, seg in enumerate(segs, start=1):
        assert seg["index"] == i


def test_segments_start_at_zero():
    segs = build_subtitle_segments(_make_vitem())
    assert segs[0]["start_seconds"] == 0.0


def test_segments_end_matches_duration():
    vitem = _make_vitem(duration_type="short")
    segs = build_subtitle_segments(vitem)
    assert abs(segs[-1]["end_seconds"] - 30.0) < 0.1


def test_segments_time_monotonic():
    segs = build_subtitle_segments(_make_vitem())
    for i in range(len(segs) - 1):
        assert segs[i]["end_seconds"] <= segs[i + 1]["start_seconds"] + 0.001


def test_segments_text_not_empty():
    segs = build_subtitle_segments(_make_vitem())
    for seg in segs:
        assert seg["text"].strip() != ""


def test_segments_long_duration():
    vitem = _make_vitem(duration_type="long")
    segs = build_subtitle_segments(vitem)
    assert segs[-1]["end_seconds"] <= 60.5


def test_segments_metadata_duration_override():
    vitem = _make_vitem(duration_type="short")
    meta = {"duration_seconds": 45}
    segs = build_subtitle_segments(vitem, meta)
    assert abs(segs[-1]["end_seconds"] - 45.0) < 0.1


def test_segments_review_required_for_legal():
    vitem = _make_vitem(subtitle_points=["법령 제5조에 따라 반드시 점검"])
    segs = build_subtitle_segments(vitem)
    legal_segs = [s for s in segs if "법령" in s["text"] or s["review_required"]]
    assert any(s["review_required"] for s in segs)


def test_segments_text_max_lines():
    long_text = "이것은 매우 긴 자막 텍스트입니다. " * 5
    vitem = _make_vitem(hook=long_text)
    segs = build_subtitle_segments(vitem)
    first = segs[0]["text"]
    assert first.count("\n") <= 1  # max 2줄


# ---------------------------------------------------------------------------
# SRT / VTT render
# ---------------------------------------------------------------------------


def test_render_srt_format():
    segs = build_subtitle_segments(_make_vitem())
    srt = render_srt(segs)
    assert "00:00:00,000 --> " in srt
    assert "1\n" in srt


def test_render_vtt_format():
    segs = build_subtitle_segments(_make_vitem())
    vtt = render_vtt(segs)
    assert vtt.startswith("WEBVTT")
    assert "00:00:00.000 --> " in vtt


def test_srt_segment_count_matches():
    segs = build_subtitle_segments(_make_vitem())
    srt = render_srt(segs)
    # 각 segment 는 index 번호로 시작
    count = sum(1 for line in srt.split("\n") if line.strip().isdigit())
    assert count == len(segs)


# ---------------------------------------------------------------------------
# build_subtitle_queue
# ---------------------------------------------------------------------------


def test_build_subtitle_queue_basic():
    items = [_make_vitem()]
    q = build_subtitle_queue(items)
    assert q["total_items"] == 1
    assert q["subtitle_items"][0]["subtitle_id"] == "subtitle_001"


def test_build_subtitle_queue_max_items():
    items = [_make_vitem() for _ in range(10)]
    q = build_subtitle_queue(items, max_items=3)
    assert q["total_items"] == 3


def test_build_subtitle_queue_language():
    items = [_make_vitem()]
    q = build_subtitle_queue(items, language="ko")
    assert q["language"] == "ko"
    assert q["subtitle_items"][0]["language"] == "ko"


def test_build_subtitle_queue_no_secret():
    items = [_make_vitem(title="api_key=secret123")]
    q = build_subtitle_queue(items)
    raw_json = str(q)
    # secret 이 title 에 있어도 segment text 에는 truncate 되어 들어가야 하며,
    # api_key= 패턴이 warnings 에 잡혀야 함
    warnings = q["subtitle_items"][0]["warnings"]
    assert any("secret_keyword" in w for w in warnings)


def test_extract_video_queue_items_dict():
    vq = {"queue": [_make_vitem(), _make_vitem()]}
    items = extract_video_queue_items(vq)
    assert len(items) == 2


def test_extract_video_queue_items_list():
    items = extract_video_queue_items([_make_vitem()])
    assert len(items) == 1


def test_extract_recording_metadata_single():
    meta = {"recording_id": "rec_001", "duration_seconds": 45}
    mapping = extract_recording_metadata(meta)
    assert "rec_001" in mapping
    assert mapping["rec_001"]["duration_seconds"] == 45


def test_extract_recording_metadata_worker_result():
    worker = {"items": [
        {"recording_id": "rec_001", "duration_seconds": 30},
        {"recording_id": "rec_002", "duration_seconds": 60},
    ]}
    mapping = extract_recording_metadata(worker)
    assert "rec_001" in mapping
    assert "rec_002" in mapping


# ---------------------------------------------------------------------------
# write_subtitle_queue_files
# ---------------------------------------------------------------------------


def test_write_subtitle_queue_files(tmp_path):
    items = [_make_vitem(), _make_vitem(queue_id="test_002", title="건설안전 정보")]
    q = build_subtitle_queue(items)
    files = write_subtitle_queue_files(q, tmp_path, timestamp="20260101_000000")

    assert files["json"].exists()
    assert files["md"].exists()
    assert len(files["srt_files"]) == 2
    assert len(files["vtt_files"]) == 2
    for p in files["srt_files"]:
        assert Path(p).exists()
        assert Path(p).stat().st_size > 0
    for p in files["vtt_files"]:
        assert Path(p).exists()
        content = Path(p).read_text(encoding="utf-8")
        assert content.startswith("WEBVTT")


def test_srt_path_updated_in_queue(tmp_path):
    items = [_make_vitem()]
    q = build_subtitle_queue(items)
    write_subtitle_queue_files(q, tmp_path, timestamp="20260101_000001")
    assert q["subtitle_items"][0]["srt_path"] is not None


# ---------------------------------------------------------------------------
# security / constraint checks
# ---------------------------------------------------------------------------


def test_no_playwright_import():
    src = (
        _ROOT / "ai_orchestrator" / "video_production" / "subtitle_queue.py"
    ).read_text(encoding="utf-8")
    assert "import playwright" not in src.lower()
    assert "from playwright" not in src.lower()


def test_no_oauth_import():
    src = (
        _ROOT / "ai_orchestrator" / "video_production" / "subtitle_queue.py"
    ).read_text(encoding="utf-8")
    assert "import oauth" not in src.lower()
    assert "from oauth" not in src.lower()


def test_no_tts_stt_call():
    src = (
        _ROOT / "ai_orchestrator" / "video_production" / "subtitle_queue.py"
    ).read_text(encoding="utf-8")
    for kw in ("tts_api", "stt_api", "speech_to_text", "text_to_speech", "openai.audio", "whisper.transcribe"):
        assert kw not in src.lower(), f"subtitle_queue must not call {kw}"


def test_no_ltx_api_call():
    src = (
        _ROOT / "ai_orchestrator" / "video_production" / "subtitle_queue.py"
    ).read_text(encoding="utf-8")
    assert "ltx_api" not in src.lower()
    assert "import ltx" not in src.lower()


def test_no_upload_call():
    src = (
        _ROOT / "ai_orchestrator" / "video_production" / "subtitle_queue.py"
    ).read_text(encoding="utf-8")
    assert ".upload(" not in src.lower()


def test_notes_contain_no_stt_tts():
    items = [_make_vitem()]
    q = build_subtitle_queue(items)
    for note in q["notes"]:
        assert "stt" not in note.lower() or "없음" in note

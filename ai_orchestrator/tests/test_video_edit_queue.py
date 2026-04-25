"""F-4S-11 edit_queue 단위 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ai_orchestrator.video_production.edit_queue import (
    extract_recording_assets,
    extract_subtitle_assets,
    extract_tts_assets,
    build_edit_queue,
    build_edit_timeline,
    _build_edit_steps,
    render_edit_queue_markdown,
    write_edit_queue_files,
    ALLOWED_STEP_TYPES,
    FORBIDDEN_STEP_TYPES,
)

_META_PATH = (
    _ROOT / "runs" / "video" / "smoke" / "recordings" /
    "smoke_localhost_20260425_231935" /
    "smoke_localhost_20260425_231935_metadata.json"
)
_SUB_Q_PATH = next(
    (_ROOT / "runs" / "video" / "subtitles").glob("subtitle_queue_*.json"), None
)
_TTS_Q_PATH = next(
    (_ROOT / "runs" / "video" / "tts").glob("tts_queue_*.json"), None
)


# ---------------------------------------------------------------------------
# fixtures helpers
# ---------------------------------------------------------------------------


def _make_rec_asset(**kw):
    base = {
        "recording_id": "rec_001",
        "source_queue_id": "video_001",
        "video_path": "runs/video/smoke/recordings/rec_001/test.webm",
        "video_dir": "runs/video/smoke/recordings/rec_001",
        "duration_seconds": 30,
        "success": True,
        "planned_only": False,
    }
    base.update(kw)
    return base


def _make_sub_asset(**kw):
    base = {
        "subtitle_id": "subtitle_001",
        "source_queue_id": "video_001",
        "title": "소방안전 핵심 정보",
        "srt_path": "runs/video/subtitles/subtitle_001.srt",
        "vtt_path": "runs/video/subtitles/subtitle_001.vtt",
        "duration_seconds": 30,
        "review_required": False,
    }
    base.update(kw)
    return base


def _make_tts_asset(**kw):
    base = {
        "tts_id": "tts_001",
        "subtitle_id": "subtitle_001",
        "source_queue_id": "video_001",
        "title": "소방안전 핵심 정보",
        "expected_audio_path": "runs/video/tts/audio/tts_001.wav",
        "voice_profile": "ko_male_neutral",
        "review_required": False,
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# extract_recording_assets
# ---------------------------------------------------------------------------


def test_extract_recording_assets_single_metadata():
    meta = {
        "recording_id": "rec_001",
        "source_queue_id": "q_001",
        "video_path": "/tmp/test.webm",
        "video_dir": "/tmp",
        "success": True,
        "started_at": "2026-04-25T23:00:00Z",
        "finished_at": "2026-04-25T23:00:30Z",
    }
    assets = extract_recording_assets(meta)
    assert len(assets) == 1
    assert assets[0]["recording_id"] == "rec_001"
    assert assets[0]["video_path"] == "/tmp/test.webm"


def test_extract_recording_assets_worker_result():
    worker = {
        "items": [
            {"recording_id": "rec_001", "video_path": "/tmp/a.webm", "success": True,
             "started_at": "2026-04-25T23:00:00Z", "finished_at": "2026-04-25T23:00:30Z"},
            {"recording_id": "rec_002", "video_path": "/tmp/b.webm", "success": True,
             "started_at": "2026-04-25T23:00:00Z", "finished_at": "2026-04-25T23:01:00Z"},
        ]
    }
    assets = extract_recording_assets(worker)
    assert len(assets) == 2


def test_extract_recording_assets_empty():
    assert extract_recording_assets({}) == []
    assert extract_recording_assets("invalid") == []


def test_extract_recording_assets_planned_only_when_no_video():
    meta = {
        "recording_id": "rec_001",
        "video_path": "",
        "video_dir": "/tmp",
        "success": False,
        "started_at": "2026-04-25T23:00:00Z",
        "finished_at": "2026-04-25T23:00:05Z",
    }
    assets = extract_recording_assets(meta)
    assert assets[0]["planned_only"] is True


@pytest.mark.skipif(not _META_PATH.exists(), reason="metadata file not found")
def test_extract_recording_assets_from_file():
    from ai_orchestrator.video_production.edit_queue import load_json
    meta = load_json(_META_PATH)
    assets = extract_recording_assets(meta)
    assert len(assets) == 1
    assert assets[0]["video_path"]


# ---------------------------------------------------------------------------
# extract_subtitle_assets
# ---------------------------------------------------------------------------


def test_extract_subtitle_assets_basic():
    sub_q = {
        "subtitle_items": [
            {"subtitle_id": "subtitle_001", "source_queue_id": "video_001",
             "title": "테스트", "srt_path": "/tmp/s.srt", "vtt_path": "/tmp/s.vtt",
             "duration_seconds": 30, "review_required": False},
        ]
    }
    assets = extract_subtitle_assets(sub_q)
    assert len(assets) == 1
    assert assets[0]["subtitle_id"] == "subtitle_001"
    assert assets[0]["srt_path"] == "/tmp/s.srt"


def test_extract_subtitle_assets_empty():
    assert extract_subtitle_assets({}) == []
    assert extract_subtitle_assets({"subtitle_items": []}) == []


@pytest.mark.skipif(_SUB_Q_PATH is None, reason="subtitle queue file not found")
def test_extract_subtitle_assets_from_file():
    from ai_orchestrator.video_production.edit_queue import load_json
    sub_q = load_json(_SUB_Q_PATH)
    assets = extract_subtitle_assets(sub_q)
    assert len(assets) > 0
    assert all("srt_path" in a for a in assets)


# ---------------------------------------------------------------------------
# extract_tts_assets
# ---------------------------------------------------------------------------


def test_extract_tts_assets_basic():
    tts_q = {
        "tts_items": [
            {"tts_id": "tts_001", "subtitle_id": "subtitle_001",
             "source_queue_id": "video_001", "title": "테스트",
             "expected_audio_path": "/tmp/t.wav", "voice_profile": "ko_male_neutral",
             "review_required": False},
        ]
    }
    assets = extract_tts_assets(tts_q)
    assert len(assets) == 1
    assert assets[0]["expected_audio_path"] == "/tmp/t.wav"


def test_extract_tts_assets_empty():
    assert extract_tts_assets({}) == []


# ---------------------------------------------------------------------------
# build_edit_timeline
# ---------------------------------------------------------------------------


def test_timeline_has_video_layer():
    tl = build_edit_timeline(30, source_video_path="/tmp/v.webm", srt_path="/tmp/s.srt", tts_audio_path="/tmp/a.wav")
    layers = [t["layer"] for t in tl]
    assert "video" in layers


def test_timeline_has_subtitle_layer():
    tl = build_edit_timeline(30, source_video_path="/tmp/v.webm", srt_path="/tmp/s.srt", tts_audio_path="")
    layers = [t["layer"] for t in tl]
    assert "subtitle" in layers


def test_timeline_voiceover_planned_only():
    tl = build_edit_timeline(30, source_video_path="/tmp/v.webm", srt_path="/tmp/s.srt", tts_audio_path="/tmp/a.wav")
    vo = next(t for t in tl if t["layer"] == "voiceover")
    assert vo["planned_only"] is True


def test_timeline_no_subtitle_layer_when_empty():
    tl = build_edit_timeline(30, source_video_path="/tmp/v.webm", srt_path="", tts_audio_path="")
    layers = [t["layer"] for t in tl]
    assert "subtitle" not in layers


def test_timeline_end_equals_duration():
    tl = build_edit_timeline(45, source_video_path="/tmp/v.webm", srt_path="/tmp/s.srt", tts_audio_path="")
    for layer in tl:
        assert layer["end_seconds"] == 45


# ---------------------------------------------------------------------------
# _build_edit_steps
# ---------------------------------------------------------------------------


def test_edit_steps_all_allowed_types():
    steps = _build_edit_steps(has_video=True, has_subtitle=True, has_audio=True)
    for step in steps:
        assert step["type"] in ALLOWED_STEP_TYPES
        assert step["type"] not in FORBIDDEN_STEP_TYPES


def test_edit_steps_sequential():
    steps = _build_edit_steps(has_video=True, has_subtitle=True, has_audio=True)
    for i, step in enumerate(steps, start=1):
        assert step["step_no"] == i


def test_edit_steps_no_ffmpeg():
    steps = _build_edit_steps(has_video=True, has_subtitle=True, has_audio=True)
    types = [s["type"] for s in steps]
    assert "ffmpeg_run" not in types
    assert "render_video" not in types
    assert "upload" not in types


# ---------------------------------------------------------------------------
# build_edit_queue
# ---------------------------------------------------------------------------


def test_build_edit_queue_basic():
    q = build_edit_queue(
        [_make_rec_asset()],
        [_make_sub_asset()],
        [_make_tts_asset()],
    )
    assert q["total_items"] == 1
    assert q["edit_items"][0]["edit_id"] == "edit_001"


def test_build_edit_queue_max_items():
    recs = [_make_rec_asset(recording_id=f"rec_{i}", source_queue_id=f"video_{i:03d}") for i in range(8)]
    subs = [_make_sub_asset(subtitle_id=f"subtitle_{i:03d}", source_queue_id=f"video_{i:03d}") for i in range(8)]
    tts = [_make_tts_asset(tts_id=f"tts_{i:03d}", source_queue_id=f"video_{i:03d}") for i in range(8)]
    q = build_edit_queue(recs, subs, tts, max_items=3)
    assert q["total_items"] == 3


def test_build_edit_queue_without_recording():
    q = build_edit_queue([], [_make_sub_asset()], [_make_tts_asset()])
    assert q["total_items"] == 1
    item = q["edit_items"][0]
    assert item["source_video_path"] is None
    assert "source_video_missing" in " ".join(item["warnings"])


def test_build_edit_queue_output_video_path():
    q = build_edit_queue([_make_rec_asset()], [_make_sub_asset()], [_make_tts_asset()])
    path = q["edit_items"][0]["output_video_path"]
    assert path.endswith(".mp4")
    assert "edit_001" in path


def test_build_edit_queue_no_actual_mp4_created():
    q = build_edit_queue([_make_rec_asset()], [_make_sub_asset()], [_make_tts_asset()],
                         output_dir=Path("runs/video/edits"))
    out_path = Path(q["edit_items"][0]["output_video_path"])
    assert not out_path.exists(), "output_video_path must NOT be created (plan only)"


def test_build_edit_queue_review_required_propagated():
    sub = _make_sub_asset(review_required=True)
    q = build_edit_queue([], [sub], [])
    assert q["edit_items"][0]["review_required"] is True


def test_build_edit_queue_secret_warning():
    sub = _make_sub_asset(title="api_key=abc 정보")
    q = build_edit_queue([], [sub], [])
    warnings = q["edit_items"][0]["warnings"]
    assert any("secret_keyword" in w for w in warnings)


def test_build_edit_queue_notes_no_ffmpeg():
    q = build_edit_queue([], [_make_sub_asset()], [])
    notes = " ".join(q["notes"])
    assert "ffmpeg" in notes.lower() or "실제" in notes


# ---------------------------------------------------------------------------
# write_edit_queue_files
# ---------------------------------------------------------------------------


def test_write_edit_queue_files(tmp_path):
    q = build_edit_queue([_make_rec_asset()], [_make_sub_asset()], [_make_tts_asset()],
                         output_dir=tmp_path)
    files = write_edit_queue_files(q, tmp_path, timestamp="20260101_000000")
    assert files["json"].exists()
    assert files["md"].exists()
    md_content = files["md"].read_text(encoding="utf-8")
    assert "영상 편집 큐 PoC" in md_content
    assert "timeline" in md_content.lower()


def test_write_no_mp4_created(tmp_path):
    q = build_edit_queue([], [_make_sub_asset()], [], output_dir=tmp_path)
    write_edit_queue_files(q, tmp_path, timestamp="20260101_000001")
    mp4_files = list(tmp_path.rglob("*.mp4"))
    assert len(mp4_files) == 0


# ---------------------------------------------------------------------------
# 보안 / 제약 검사 (정적)
# ---------------------------------------------------------------------------


def _module_src():
    return (_ROOT / "ai_orchestrator" / "video_production" / "edit_queue.py").read_text(encoding="utf-8")


def test_no_ffmpeg_call():
    src = _module_src()
    assert "subprocess" not in src or "ffmpeg" not in src
    assert "ffmpeg" not in src.lower() or "FORBIDDEN" in src


def test_no_playwright_import():
    src = _module_src()
    assert "import playwright" not in src.lower()
    assert "from playwright" not in src.lower()


def test_no_oauth_import():
    src = _module_src()
    assert "import oauth" not in src.lower()


def test_no_upload_call():
    src = _module_src()
    assert ".upload(" not in src.lower()


def test_no_render_video_step():
    assert "render_video" in FORBIDDEN_STEP_TYPES
    assert "ffmpeg_run" in FORBIDDEN_STEP_TYPES
    assert "upload" in FORBIDDEN_STEP_TYPES


def test_allowed_steps_no_destructive():
    for st in ALLOWED_STEP_TYPES:
        assert st not in FORBIDDEN_STEP_TYPES

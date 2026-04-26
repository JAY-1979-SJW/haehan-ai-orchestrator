"""F-4S-12 render_plan 단위 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ai_orchestrator.video_production.render_plan import (
    check_ffmpeg_available,
    validate_render_assets,
    build_ffmpeg_command_plan,
    build_render_plan,
    write_render_plan_files,
    render_render_plan_markdown,
)

_EDIT_Q_PATH = next((_ROOT / "runs" / "video" / "edits").glob("video_edit_queue_*.json"), None)


def _make_edit_item(**kw):
    base = {
        "edit_id": "edit_001",
        "title": "소방안전 핵심 정보",
        "source_video_path": "runs/video/smoke/recordings/rec_001/test.webm",
        "subtitle_srt_path": "runs/video/subtitles/subtitle_001.srt",
        "tts_expected_audio_path": "runs/video/tts/audio/tts_001.wav",
        "output_video_path": "runs/video/edits/output/edit_001.mp4",
        "review_required": False,
    }
    base.update(kw)
    return base


def _make_edit_queue(items=None):
    if items is None:
        items = [_make_edit_item()]
    return {"edit_items": items}


# ---------------------------------------------------------------------------
# check_ffmpeg_available
# ---------------------------------------------------------------------------


def test_check_ffmpeg_available_returns_bool():
    result = check_ffmpeg_available()
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# validate_render_assets
# ---------------------------------------------------------------------------


def test_validate_render_assets_missing_files():
    item = _make_edit_item(
        source_video_path="/nonexistent/video.webm",
        subtitle_srt_path="/nonexistent/sub.srt",
        tts_expected_audio_path="/nonexistent/audio.wav",
    )
    assets = validate_render_assets(item)
    assert assets["video_exists"] is False
    assert assets["subtitle_exists"] is False
    assert assets["audio_exists"] is False


def test_validate_render_assets_paths_preserved():
    item = _make_edit_item(
        source_video_path="/tmp/v.webm",
        subtitle_srt_path="/tmp/s.srt",
        tts_expected_audio_path="/tmp/a.wav",
        output_video_path="/tmp/out.mp4",
    )
    assets = validate_render_assets(item)
    assert assets["video_path"] == "/tmp/v.webm"
    assert assets["subtitle_path"] == "/tmp/s.srt"
    assert assets["audio_path"] == "/tmp/a.wav"
    assert assets["output_path"] == "/tmp/out.mp4"


def test_validate_render_assets_empty_paths():
    item = _make_edit_item(
        source_video_path="",
        subtitle_srt_path="",
        tts_expected_audio_path="",
        output_video_path="",
    )
    assets = validate_render_assets(item)
    assert assets["video_path"] is None
    assert assets["subtitle_path"] is None
    assert assets["audio_path"] is None


# ---------------------------------------------------------------------------
# build_ffmpeg_command_plan
# ---------------------------------------------------------------------------


def test_command_plan_shell_false():
    cmd = build_ffmpeg_command_plan(_make_edit_item())
    assert cmd["shell"] is False


def test_command_plan_planned_only():
    cmd = build_ffmpeg_command_plan(_make_edit_item())
    assert cmd["planned_only"] is True


def test_command_plan_program_ffmpeg():
    cmd = build_ffmpeg_command_plan(_make_edit_item())
    assert cmd["program"] == "ffmpeg"


def test_command_plan_has_output():
    item = _make_edit_item(output_video_path="/tmp/out.mp4")
    cmd = build_ffmpeg_command_plan(item)
    assert "/tmp/out.mp4" in cmd["args"]


def test_command_plan_has_codec_flags():
    cmd = build_ffmpeg_command_plan(_make_edit_item())
    assert "-c:v" in cmd["args"]
    assert "libx264" in cmd["args"]
    assert "-c:a" in cmd["args"]
    assert "aac" in cmd["args"]


def test_command_plan_subtitle_vf():
    item = _make_edit_item(subtitle_srt_path="/tmp/sub.srt")
    cmd = build_ffmpeg_command_plan(item)
    assert "-vf" in cmd["args"]
    vf_idx = cmd["args"].index("-vf")
    assert "subtitles=" in cmd["args"][vf_idx + 1]


def test_command_plan_display_starts_with_ffmpeg():
    cmd = build_ffmpeg_command_plan(_make_edit_item())
    assert cmd["display"].startswith("ffmpeg ")


def test_command_plan_secret_redacted():
    item = _make_edit_item(output_video_path="/tmp/api_key=abc.mp4")
    cmd = build_ffmpeg_command_plan(item)
    assert "<redacted>" in cmd["display"]
    assert any("secret_like_arg_blocked" in w for w in cmd["warnings"])


# ---------------------------------------------------------------------------
# build_render_plan
# ---------------------------------------------------------------------------


def test_build_render_plan_basic(tmp_path):
    eq = _make_edit_queue()
    plan = build_render_plan(eq, out_dir=tmp_path)
    assert plan["total_items"] == 1
    assert plan["planned_count"] == 1
    assert plan["blocked_count"] == 0


def test_build_render_plan_render_id_format(tmp_path):
    eq = _make_edit_queue()
    plan = build_render_plan(eq, out_dir=tmp_path)
    assert plan["render_items"][0]["render_id"] == "render_001"


def test_build_render_plan_status_planned_when_no_require(tmp_path):
    eq = _make_edit_queue([_make_edit_item(source_video_path="/nonexistent/v.webm")])
    plan = build_render_plan(eq, out_dir=tmp_path, require_assets=False)
    assert plan["render_items"][0]["status"] == "planned"


def test_build_render_plan_status_blocked_when_require(tmp_path):
    eq = _make_edit_queue([_make_edit_item(source_video_path="/nonexistent/v.webm")])
    plan = build_render_plan(eq, out_dir=tmp_path, require_assets=True)
    assert plan["render_items"][0]["status"] == "blocked"
    assert plan["blocked_count"] == 1


def test_build_render_plan_max_items(tmp_path):
    items = [_make_edit_item(edit_id=f"edit_{i:03d}") for i in range(5)]
    eq = _make_edit_queue(items)
    plan = build_render_plan(eq, out_dir=tmp_path, max_items=2)
    assert plan["total_items"] == 2


def test_build_render_plan_has_notes(tmp_path):
    plan = build_render_plan(_make_edit_queue(), out_dir=tmp_path)
    notes = " ".join(plan["notes"])
    assert "ffmpeg" in notes.lower() or "실행 없음" in notes


def test_build_render_plan_command_plan_no_execution(tmp_path):
    plan = build_render_plan(_make_edit_queue(), out_dir=tmp_path)
    for item in plan["render_items"]:
        assert item["command_plan"]["planned_only"] is True
        assert item["command_plan"]["shell"] is False


def test_build_render_plan_empty_edit_queue(tmp_path):
    plan = build_render_plan({"edit_items": []}, out_dir=tmp_path)
    assert plan["total_items"] == 0


def test_build_render_plan_invalid_input(tmp_path):
    plan = build_render_plan("not_a_dict", out_dir=tmp_path)
    assert plan["total_items"] == 0


def test_build_render_plan_warnings_on_missing_assets(tmp_path):
    eq = _make_edit_queue([_make_edit_item(source_video_path="/nonexistent/v.webm")])
    plan = build_render_plan(eq, out_dir=tmp_path)
    warnings = plan["render_items"][0]["warnings"]
    assert any("input_video_missing" in w for w in warnings)


# ---------------------------------------------------------------------------
# write_render_plan_files
# ---------------------------------------------------------------------------


def test_write_render_plan_files_creates_json_md(tmp_path):
    plan = build_render_plan(_make_edit_queue(), out_dir=tmp_path)
    files = write_render_plan_files(plan, tmp_path, timestamp="20260101_000000")
    assert files["json"].exists()
    assert files["md"].exists()


def test_write_render_plan_files_json_valid(tmp_path):
    import json
    plan = build_render_plan(_make_edit_queue(), out_dir=tmp_path)
    files = write_render_plan_files(plan, tmp_path, timestamp="20260101_000001")
    data = json.loads(files["json"].read_text(encoding="utf-8"))
    assert "render_items" in data
    assert data["total_items"] >= 1


def test_write_render_plan_files_md_has_header(tmp_path):
    plan = build_render_plan(_make_edit_queue(), out_dir=tmp_path)
    files = write_render_plan_files(plan, tmp_path, timestamp="20260101_000002")
    md = files["md"].read_text(encoding="utf-8")
    assert "Render Plan" in md
    assert "F-4S-12" in md


def test_write_no_mp4_created(tmp_path):
    plan = build_render_plan(_make_edit_queue(), out_dir=tmp_path)
    write_render_plan_files(plan, tmp_path, timestamp="20260101_000003")
    assert len(list(tmp_path.rglob("*.mp4"))) == 0


# ---------------------------------------------------------------------------
# 파일 기반 (runs/ 디렉토리)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(_EDIT_Q_PATH is None, reason="edit queue not found")
def test_build_render_plan_from_file(tmp_path):
    import json
    eq = json.loads(_EDIT_Q_PATH.read_text(encoding="utf-8"))
    plan = build_render_plan(eq, out_dir=tmp_path)
    assert plan["total_items"] >= 1
    for item in plan["render_items"]:
        assert item["command_plan"]["planned_only"] is True


# ---------------------------------------------------------------------------
# 보안 / 제약 검사 (정적)
# ---------------------------------------------------------------------------


def _module_src():
    return (_ROOT / "ai_orchestrator" / "video_production" / "render_plan.py").read_text(encoding="utf-8")


def test_no_subprocess():
    src = _module_src()
    assert "import subprocess" not in src


def test_no_shell_true():
    src = _module_src()
    # Actual call pattern must not appear (docstring mentions it as forbidden, that's OK)
    assert "shell=True)" not in src and "shell = True" not in src


def test_no_os_system():
    src = _module_src()
    assert "os.system(" not in src


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


def test_ffmpeg_check_uses_which_only():
    src = _module_src()
    assert "shutil.which" in src
    # --version must not appear in actual code (only docstring mentions it as forbidden)
    code_lines = [l for l in src.splitlines() if not l.strip().startswith("-") and not l.strip().startswith("#")]
    assert not any('"--version"' in l or "'--version'" in l for l in code_lines)

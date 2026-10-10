from pathlib import Path
from uuid import uuid4

from scripts.youtube import recording, uploader


def _runtime_dir() -> Path:
    path = Path("data") / "test_runtime" / "youtube_workflow" / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_prepare_upload_plan_blocks_missing_file(monkeypatch):
    base = _runtime_dir()
    monkeypatch.setattr(uploader, "PLAN_DIR", base / "plans")
    monkeypatch.setattr(uploader, "LATEST_PLAN", base / "latest_plan.json")

    plan, path = uploader.prepare_upload_plan(
        base / "missing.mp4",
        {"title": "업무 기록", "privacy": "private"},
    )

    assert path.exists()
    assert plan["ready_for_approval"] is False
    assert "local_video_file" in plan["missing_requirements"]


def test_prepare_upload_plan_accepts_existing_video(monkeypatch):
    base = _runtime_dir()
    video = base / "work.mp4"
    video.write_bytes(b"not a real mp4 but enough for manifest tests")
    monkeypatch.setattr(uploader, "PLAN_DIR", base / "plans")
    monkeypatch.setattr(uploader, "LATEST_PLAN", base / "latest_plan.json")

    plan, _path = uploader.prepare_upload_plan(
        video,
        {"title": "Local Work", "description": "demo", "privacy": "private", "tags": "work,local"},
    )

    assert plan["ready_for_approval"] is True
    assert plan["metadata"]["privacy_status"] == "private"
    assert plan["metadata"]["tags"] == ["work", "local"]


def test_upload_execute_requires_approval(monkeypatch):
    base = _runtime_dir()
    video = base / "work.mp4"
    video.write_bytes(b"video")
    monkeypatch.setattr(uploader, "PLAN_DIR", base / "plans")
    monkeypatch.setattr(uploader, "RESULT_DIR", base / "results")
    monkeypatch.setattr(uploader, "LATEST_PLAN", base / "latest_plan.json")
    monkeypatch.setattr(uploader, "LATEST_RESULT", base / "latest_result.json")
    _plan, path = uploader.prepare_upload_plan(video, {"title": "Local Work"})

    result, result_path = uploader.execute_upload_plan(path, approved=False, confirm="", dry_run=True)

    assert result_path.exists()
    assert result["status"] == "blocked"
    assert result["state_change"] is False


def test_upload_execute_dry_run_with_approval(monkeypatch):
    base = _runtime_dir()
    video = base / "work.mp4"
    video.write_bytes(b"video")
    monkeypatch.setattr(uploader, "PLAN_DIR", base / "plans")
    monkeypatch.setattr(uploader, "RESULT_DIR", base / "results")
    monkeypatch.setattr(uploader, "LATEST_PLAN", base / "latest_plan.json")
    monkeypatch.setattr(uploader, "LATEST_RESULT", base / "latest_result.json")
    _plan, path = uploader.prepare_upload_plan(video, {"title": "Local Work"})

    result, _result_path = uploader.execute_upload_plan(
        path,
        approved=True,
        confirm=uploader.APPROVAL_PHRASE,
        dry_run=True,
    )

    assert result["status"] == "dry_run_ok"
    assert result["state_change"] is False


def test_prepare_recording_plan_records_ffmpeg_requirement(monkeypatch):
    base = _runtime_dir()
    monkeypatch.setattr(recording, "PLAN_DIR", base / "plans")
    monkeypatch.setattr(recording, "LATEST_PLAN", base / "latest_plan.json")
    monkeypatch.setattr(recording.shutil, "which", lambda _name: None)

    plan, path = recording.prepare_recording_plan(
        {"duration": "3", "output": str(base / "capture.mp4"), "ffmpeg": "definitely_missing_ffmpeg"}
    )

    assert path.exists()
    assert plan["ready_for_approval"] is False
    assert "ffmpeg" in plan["missing_requirements"]

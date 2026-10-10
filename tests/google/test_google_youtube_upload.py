from pathlib import Path
from uuid import uuid4

from scripts.google import youtube
from scripts.google.common import youtube_upload


def _video_fixture() -> Path:
    path = Path("tmp") / "google_tests" / f"{uuid4().hex}.mp4"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not-a-real-video-but-valid-test-extension")
    return path


def test_youtube_upload_plan_validates_inputs_without_uploading() -> None:
    video = _video_fixture()

    plan = youtube_upload.build_youtube_upload_plan(
        {
            "video_path": str(video),
            "title": "Haehan dry run",
            "description": "No final submit",
            "visibility": "private",
            "made_for_kids": "no",
            "tags": "haehan,dry-run",
        }
    )

    assert plan["status"] == "ready_for_user_approval_handoff"
    assert plan["safe_automation_boundary"]["local_file_validation"] == "allowed"
    assert plan["safe_automation_boundary"]["file_select_upload_draft"] == "approval_required"
    assert plan["safe_automation_boundary"]["final_publish"] == "blocked_without_approval_phrase"
    assert plan["workflow_ready_for_approval"] is True
    assert plan["workflow_missing_inputs"] == []
    assert any(item["surface_key"] == "youtube_studio" for item in plan["youtube_page_tabs"])


def test_youtube_upload_plan_blocks_missing_made_for_kids() -> None:
    video = _video_fixture()

    plan = youtube.upload_plan(
        {
            "video_path": str(video),
            "title": "Haehan dry run",
            "description": "No final submit",
            "visibility": "private",
        }
    )

    failed = {item["key"] for item in plan["checks"] if not item["ok"]}
    assert plan["status"] == "blocked_missing_or_invalid_inputs"
    assert "made_for_kids_declared" in failed


def test_youtube_upload_plan_blocks_bad_extension() -> None:
    bad = Path("tmp") / "google_tests" / f"{uuid4().hex}.txt"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("bad", encoding="utf-8")

    plan = youtube_upload.build_youtube_upload_plan(
        {
            "video_path": str(bad),
            "title": "Haehan dry run",
            "description": "No final submit",
            "visibility": "private",
            "made_for_kids": "no",
        }
    )

    failed = {item["key"] for item in plan["checks"] if not item["ok"]}
    assert "video_extension_allowed" in failed

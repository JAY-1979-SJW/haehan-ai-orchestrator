"""Unit tests for ai_orchestrator/video_production/recording_worker.py (F-4S-8a)."""
from __future__ import annotations

import inspect
import json
import tokenize
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List

import pytest

from ai_orchestrator.video_production import recording_worker as rw


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_item(
    recording_id: str = "recording_001",
    title: str = "스마트팩토리 핵심",
    target_url: str = "http://localhost:3000",
    duration_seconds: int = 30,
    viewport: Dict[str, Any] | None = None,
    extra_steps: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    vp = viewport or {"name": "desktop", "width": 1440, "height": 900}
    steps: List[Dict[str, Any]] = [
        {"step_no": 1, "type": "open_url", "url": target_url},
        {"step_no": 2, "type": "wait", "wait_seconds": 2},
        {"step_no": 3, "type": "capture_scene", "duration_seconds": 10, "caption": "핵심 화면"},
        {"step_no": 4, "type": "scroll_plan", "direction": "down", "amount_px": 600},
        {"step_no": 5, "type": "capture_scene", "duration_seconds": 10, "caption": "세부 화면"},
        {"step_no": 6, "type": "overlay_caption", "captions": ["자막1"]},
    ]
    if extra_steps:
        steps.extend(extra_steps)
    return {
        "recording_id": recording_id,
        "source_queue_id": "video_001",
        "status": "draft",
        "title": title,
        "target_url": target_url,
        "viewport": vp,
        "duration_seconds": duration_seconds,
        "duration_type": "short",
        "recording_steps": steps,
    }


def _make_queue(*items: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "generated_at": "2026-04-26T00:00:00Z",
        "recording_count": len(items),
        "allowed_step_types": list(rw.ALLOWED_STEP_TYPES),
        "forbidden_step_types": list(rw.FORBIDDEN_STEP_TYPES),
        "queue": list(items),
    }


# ---------------------------------------------------------------------------
# load_recording_queue
# ---------------------------------------------------------------------------


def test_load_recording_queue_roundtrip(tmp_path: Path):
    q = _make_queue(_make_item())
    p = tmp_path / "queue.json"
    p.write_text(json.dumps(q, ensure_ascii=False), encoding="utf-8")
    loaded = rw.load_recording_queue(p)
    assert loaded["recording_count"] == 1
    assert loaded["queue"][0]["recording_id"] == "recording_001"


def test_load_recording_queue_not_dict_raises(tmp_path: Path):
    p = tmp_path / "bad.json"
    p.write_text(json.dumps([{"a": 1}]), encoding="utf-8")
    with pytest.raises(ValueError, match="must be an object"):
        rw.load_recording_queue(p)


# ---------------------------------------------------------------------------
# validate_recording_queue
# ---------------------------------------------------------------------------


def test_validate_recording_queue_ok():
    q = _make_queue(_make_item())
    result = rw.validate_recording_queue(q)
    assert result["errors"] == []
    assert len(result["items"]) == 1


def test_validate_recording_queue_missing_queue_field():
    result = rw.validate_recording_queue({"recording_count": 0})
    assert any("queue_field_missing" in e for e in result["errors"])


def test_validate_recording_queue_list_input():
    result = rw.validate_recording_queue([_make_item()])
    assert len(result["items"]) == 1
    assert result["errors"] == []


def test_validate_recording_queue_non_object_input():
    result = rw.validate_recording_queue("not a queue")
    assert any("not_object_or_list" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# validate_recording_item — allowed steps
# ---------------------------------------------------------------------------


def test_validate_item_all_allowed_steps():
    item = _make_item()
    result = rw.validate_recording_item(item)
    assert result["blocked_steps"] == []
    assert result["errors"] == []
    assert len(result["allowed_steps"]) == 6


def test_validate_item_external_target_warns():
    item = _make_item(target_url="https://www.youtube.com/watch?v=abc")
    result = rw.validate_recording_item(item)
    assert any("external_target_review_required" in w for w in result["warnings"])


def test_validate_item_missing_target_url_warns():
    item = _make_item(target_url="")
    result = rw.validate_recording_item(item)
    assert any("target_url_missing" in w for w in result["warnings"])


def test_validate_item_invalid_target_url_warns():
    item = _make_item(target_url="not-a-url")
    result = rw.validate_recording_item(item)
    assert any("target_url_invalid" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# validate_recording_item — forbidden step detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("forbidden_type", list(rw.FORBIDDEN_STEP_TYPES))
def test_validate_item_detects_forbidden_step(forbidden_type: str):
    bad_step = {"step_no": 99, "type": forbidden_type}
    item = _make_item(extra_steps=[bad_step])
    result = rw.validate_recording_item(item)
    blocked_types = [b["type"] for b in result["blocked_steps"]]
    assert forbidden_type in blocked_types


def test_validate_item_click_is_blocked():
    item = _make_item(extra_steps=[{"step_no": 10, "type": "click"}])
    result = rw.validate_recording_item(item)
    assert any(b["type"] == "click" for b in result["blocked_steps"])


def test_validate_item_fill_is_blocked():
    item = _make_item(extra_steps=[{"step_no": 11, "type": "fill"}])
    result = rw.validate_recording_item(item)
    assert any(b["type"] == "fill" for b in result["blocked_steps"])


def test_validate_item_type_is_blocked():
    item = _make_item(extra_steps=[{"step_no": 12, "type": "type"}])
    result = rw.validate_recording_item(item)
    assert any(b["type"] == "type" for b in result["blocked_steps"])


def test_validate_item_press_is_blocked():
    item = _make_item(extra_steps=[{"step_no": 13, "type": "press"}])
    result = rw.validate_recording_item(item)
    assert any(b["type"] == "press" for b in result["blocked_steps"])


def test_validate_item_upload_is_blocked():
    item = _make_item(extra_steps=[{"step_no": 14, "type": "upload"}])
    result = rw.validate_recording_item(item)
    assert any(b["type"] == "upload" for b in result["blocked_steps"])


def test_validate_item_login_is_blocked():
    item = _make_item(extra_steps=[{"step_no": 15, "type": "login"}])
    result = rw.validate_recording_item(item)
    assert any(b["type"] == "login" for b in result["blocked_steps"])


def test_validate_item_purchase_is_blocked():
    item = _make_item(extra_steps=[{"step_no": 16, "type": "purchase"}])
    result = rw.validate_recording_item(item)
    assert any(b["type"] == "purchase" for b in result["blocked_steps"])


def test_validate_item_comment_is_blocked():
    item = _make_item(extra_steps=[{"step_no": 17, "type": "comment"}])
    result = rw.validate_recording_item(item)
    assert any(b["type"] == "comment" for b in result["blocked_steps"])


def test_validate_item_post_is_blocked():
    item = _make_item(extra_steps=[{"step_no": 18, "type": "post"}])
    result = rw.validate_recording_item(item)
    assert any(b["type"] == "post" for b in result["blocked_steps"])


def test_validate_item_download_is_blocked():
    item = _make_item(extra_steps=[{"step_no": 19, "type": "download"}])
    result = rw.validate_recording_item(item)
    assert any(b["type"] == "download" for b in result["blocked_steps"])


# ---------------------------------------------------------------------------
# viewport validation
# ---------------------------------------------------------------------------


def test_validate_item_viewport_desktop():
    item = _make_item(viewport={"name": "desktop", "width": 1440, "height": 900})
    result = rw.simulate_recording_item(item)
    assert result["viewport"] == {"name": "desktop", "width": 1440, "height": 900}


def test_validate_item_viewport_mobile():
    item = _make_item(viewport={"name": "mobile", "width": 390, "height": 844})
    result = rw.simulate_recording_item(item)
    assert result["viewport"]["name"] == "mobile"


def test_validate_item_viewport_unknown_falls_back_to_desktop():
    item = _make_item(viewport={"name": "ultrawide", "width": 5120, "height": 1440})
    result = rw.simulate_recording_item(item)
    assert result["viewport"]["name"] == "desktop"


# ---------------------------------------------------------------------------
# simulate_recording_item
# ---------------------------------------------------------------------------


def test_simulate_item_validated_status():
    item = _make_item()
    result = rw.simulate_recording_item(item)
    assert result["status"] == "validated"
    assert result["dry_run"] is True
    assert result["would_open_url"] == "http://localhost:3000"
    assert result["would_record_seconds"] == 30


def test_simulate_item_blocked_when_no_target_url():
    item = _make_item(target_url="")
    result = rw.simulate_recording_item(item)
    assert result["status"] == "blocked"
    assert result["would_record_seconds"] == 0
    assert any("target_url_missing" in w for w in result["warnings"])


def test_simulate_item_blocked_when_forbidden_step():
    item = _make_item(extra_steps=[{"step_no": 99, "type": "click"}])
    result = rw.simulate_recording_item(item)
    assert result["status"] == "blocked"
    assert any(b["type"] == "click" for b in result["blocked_steps"])


def test_simulate_item_output_path_planning():
    item = _make_item()
    result = rw.simulate_recording_item(item, output_dir=Path("runs/video/worker"))
    assert result["output_video_path"].endswith("recording_001.mp4")
    assert result["output_metadata_path"].endswith("recording_001.json")
    assert "recordings" in result["output_video_path"]


def test_simulate_item_no_actual_mp4_created(tmp_path: Path):
    item = _make_item()
    result = rw.simulate_recording_item(item, output_dir=tmp_path)
    mp4_path = Path(result["output_video_path"])
    assert not mp4_path.exists(), "실제 mp4 파일이 생성되었다 — dry-run 위반"


# ---------------------------------------------------------------------------
# build_execution_plan
# ---------------------------------------------------------------------------


def test_build_execution_plan_dry_run():
    q = _make_queue(_make_item(), _make_item(recording_id="recording_002", title="두 번째"))
    plan = rw.build_execution_plan(q, output_dir=Path("runs/video/worker"), dry_run=True)
    assert plan["dry_run"] is True
    assert plan["total_items"] == 2
    assert plan["validated_count"] >= 0
    assert plan["blocked_count"] >= 0


def test_build_execution_plan_not_dry_run_raises():
    q = _make_queue(_make_item())
    with pytest.raises(NotImplementedError):
        rw.build_execution_plan(q, output_dir=Path("runs/video/worker"), dry_run=False)


def test_build_execution_plan_max_items():
    q = _make_queue(
        _make_item(recording_id="recording_001"),
        _make_item(recording_id="recording_002"),
        _make_item(recording_id="recording_003"),
    )
    plan = rw.build_execution_plan(q, output_dir=Path("runs/video/worker"), max_items=2)
    assert plan["total_items"] == 2


def test_build_execution_plan_json_md_output(tmp_path: Path):
    q = _make_queue(_make_item())
    plan = rw.build_execution_plan(q, output_dir=tmp_path / "worker", dry_run=True)
    files = rw.write_worker_result_files(plan, tmp_path / "worker", timestamp="20260426_010101")
    assert files["json"].exists()
    assert files["md"].exists()
    data = json.loads(files["json"].read_text(encoding="utf-8"))
    assert data["dry_run"] is True
    assert data["total_items"] == 1
    assert "allowed_step_types" in data
    assert "forbidden_step_types" in data


def test_build_execution_plan_forbidden_step_types_in_output(tmp_path: Path):
    q = _make_queue(_make_item())
    plan = rw.build_execution_plan(q, output_dir=tmp_path, dry_run=True)
    forbidden_in_plan = plan["forbidden_step_types"]
    for f in ("click", "fill", "type", "press", "submit", "upload", "login"):
        assert f in forbidden_in_plan


def test_build_execution_plan_output_path_planning(tmp_path: Path):
    item = _make_item()
    q = _make_queue(item)
    plan = rw.build_execution_plan(q, output_dir=tmp_path / "worker", dry_run=True)
    plan_item = plan["items"][0]
    assert plan_item["output_video_path"].endswith("recording_001.mp4")
    assert not Path(plan_item["output_video_path"]).exists()


# ---------------------------------------------------------------------------
# render_worker_markdown_report
# ---------------------------------------------------------------------------


def test_render_markdown_contains_key_sections():
    q = _make_queue(_make_item())
    plan = rw.build_execution_plan(q, output_dir=Path("runs/video/worker"), dry_run=True)
    md = rw.render_worker_markdown_report(plan)
    assert "dry-run" in md
    assert "validated" in md or "blocked" in md
    assert "허용 step" in md
    assert "금지 step" in md
    assert "F-4S-8b" in md


def test_render_markdown_empty_items():
    plan = rw.build_execution_plan(
        {"queue": []}, output_dir=Path("runs/video/worker"), dry_run=True
    )
    md = rw.render_worker_markdown_report(plan)
    assert "비어 있음" in md or "total_items: 0" in md or "0" in md


# ---------------------------------------------------------------------------
# Security boundary checks — no Playwright / browser / secrets
# ---------------------------------------------------------------------------


def _module_source() -> str:
    src_path = Path(inspect.getsourcefile(rw))  # type: ignore[arg-type]
    return src_path.read_text(encoding="utf-8")


def _strip_comments_and_strings(src: str) -> str:
    out_tokens: List[str] = []
    try:
        for tok in tokenize.generate_tokens(StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                continue
            if tok.type == tokenize.STRING:
                out_tokens.append('""')
                continue
            out_tokens.append(tok.string)
    except tokenize.TokenizeError:
        return src
    return " ".join(out_tokens)


def test_module_does_not_import_playwright():
    src = _strip_comments_and_strings(_module_source())
    for needle in (
        "import playwright",
        "from playwright",
        "import selenium",
        "from selenium",
        "import requests",
        "from requests",
        "import httpx",
        "from httpx",
    ):
        assert needle not in src, f"forbidden import found: {needle}"


def test_module_has_no_browser_launch_or_goto():
    src = _strip_comments_and_strings(_module_source())
    for needle in (
        "page.goto(",
        "browser.launch(",
        "new_context(",
        ".new_page(",
        "storage_state(",
        "context.cookies(",
        ".upload(",
        "ltx_client.",
        "page.click(",
        "page.fill(",
        "page.type(",
        "page.press(",
    ):
        assert needle not in src, f"forbidden browser call found: {needle}"


def test_execution_plan_no_secret_tokens():
    q = _make_queue(_make_item())
    plan = rw.build_execution_plan(q, output_dir=Path("runs/video/worker"), dry_run=True)
    serialized = json.dumps(plan, ensure_ascii=False)
    for tok in ("sk-", "AIza", "Bearer ", "Authorization:", "Cookie:", "Set-Cookie:", "client_secret"):
        assert tok not in serialized, f"unexpected secret-like token: {tok}"


def test_execution_plan_no_oauth_or_write_action():
    q = _make_queue(_make_item())
    plan = rw.build_execution_plan(q, output_dir=Path("runs/video/worker"), dry_run=True)
    serialized = json.dumps(plan, ensure_ascii=False)
    for tok in ("oauth", "OAuth", "upload_video", "publish_post", "comment_post"):
        assert tok not in serialized, f"unexpected write/oauth token: {tok}"

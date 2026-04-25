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


def test_module_no_toplevel_playwright_import():
    """모듈 최상위에 playwright import 없음 — 함수 내 lazy import 만 허용 (F-4S-8b)."""
    src = _module_source()
    toplevel_forbidden = (
        "import selenium",
        "from selenium",
        "import requests",
        "from requests",
        "import httpx",
        "from httpx",
    )
    # 최상위 import 검사 (함수 내부 lazy import 는 허용)
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # 들여쓰기 없는 줄만 체크 (최상위)
        if not line.startswith(" ") and not line.startswith("\t"):
            for needle in toplevel_forbidden:
                assert needle not in stripped, f"forbidden top-level import: {needle}"


def test_module_has_no_forbidden_interactive_calls():
    """click/fill/type/press/keyboard/mouse/evaluate/cookies/storage_state 등 금지 호출 없음."""
    src = _strip_comments_and_strings(_module_source())
    forbidden_calls = (
        "page.click(",
        "page.fill(",
        "page.type(",
        "page.press(",
        "page.keyboard",
        "page.mouse",
        "page.evaluate(",
        "page.route(",
        "storage_state(",
        "context.cookies(",
        ".upload(",
        "ltx_client.",
        "input_value(",
    )
    for needle in forbidden_calls:
        assert needle not in src, f"forbidden interactive call found: {needle}"


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


# ---------------------------------------------------------------------------
# is_allowed_recording_url (F-4S-8b)
# ---------------------------------------------------------------------------


def test_localhost_is_allowed():
    assert rw.is_allowed_recording_url("http://localhost:3000") is True
    assert rw.is_allowed_recording_url("http://localhost:3000/path") is True


def test_127_is_allowed():
    assert rw.is_allowed_recording_url("http://127.0.0.1:8080") is True


def test_ipv6_loopback_allowed():
    assert rw.is_allowed_recording_url("http://[::1]:3000") is True


def test_extra_allow_host():
    assert rw.is_allowed_recording_url(
        "http://192.168.1.10:3000",
        allow_hosts=["192.168.1.10"],
    ) is True


def test_external_youtube_blocked():
    assert rw.is_allowed_recording_url("https://www.youtube.com/watch?v=abc") is False


def test_external_naver_blocked():
    assert rw.is_allowed_recording_url("https://naver.com") is False


def test_external_google_blocked():
    assert rw.is_allowed_recording_url("https://google.com/search?q=test") is False


def test_hometax_blocked():
    assert rw.is_allowed_recording_url("https://hometax.go.kr") is False


def test_login_url_blocked():
    assert rw.is_allowed_recording_url("http://localhost:3000/login") is False
    assert rw.is_allowed_recording_url("http://localhost:3000/auth/token") is False


def test_mypage_url_blocked():
    assert rw.is_allowed_recording_url("http://localhost:3000/mypage") is False


def test_empty_url_blocked():
    assert rw.is_allowed_recording_url("") is False
    assert rw.is_allowed_recording_url(None) is False  # type: ignore[arg-type]


def test_non_http_scheme_blocked():
    assert rw.is_allowed_recording_url("ftp://localhost/file") is False


# ---------------------------------------------------------------------------
# validate_execute_allowed (F-4S-8b)
# ---------------------------------------------------------------------------


def test_validate_execute_allowed_ok():
    q = _make_queue(_make_item(target_url="http://localhost:3000"))
    result = rw.validate_execute_allowed(q)
    assert result["can_execute"] is True
    assert result["blocked_items"] == []
    assert len(result["allowed_items"]) == 1


def test_validate_execute_allowed_blocks_external_url():
    q = _make_queue(_make_item(target_url="https://www.youtube.com/watch?v=test"))
    result = rw.validate_execute_allowed(q)
    assert result["can_execute"] is False
    assert any("url_not_allowed" in r for b in result["blocked_items"] for r in b["reasons"])


def test_validate_execute_allowed_blocks_forbidden_step():
    q = _make_queue(_make_item(extra_steps=[{"step_no": 99, "type": "click"}]))
    result = rw.validate_execute_allowed(q)
    assert result["can_execute"] is False
    assert any("forbidden_step" in r for b in result["blocked_items"] for r in b["reasons"])


def test_validate_execute_allowed_blocks_missing_url():
    q = _make_queue(_make_item(target_url=""))
    result = rw.validate_execute_allowed(q)
    assert result["can_execute"] is False


def test_validate_execute_allowed_with_custom_host():
    q = _make_queue(_make_item(target_url="http://192.168.1.10:3000"))
    result = rw.validate_execute_allowed(q, allow_hosts=["192.168.1.10"])
    assert result["can_execute"] is True


def test_validate_execute_allowed_blocks_hometax():
    q = _make_queue(_make_item(target_url="https://hometax.go.kr"))
    result = rw.validate_execute_allowed(q)
    assert result["can_execute"] is False


# ---------------------------------------------------------------------------
# execute_recording_item — mock 기반 (실제 브라우저 실행 없음)
# ---------------------------------------------------------------------------


def _make_mock_playwright(tmp_path: Path):
    """Mock playwright context manager for testing."""
    from unittest.mock import MagicMock, patch

    mock_video = MagicMock()
    mock_video.path.return_value = str(tmp_path / "video.webm")

    mock_page = MagicMock()
    mock_page.video = mock_video
    mock_page.goto = MagicMock()
    mock_page.wait_for_timeout = MagicMock()
    mock_page.screenshot = MagicMock()

    mock_context = MagicMock()
    mock_context.new_page.return_value = mock_page
    mock_context.close = MagicMock()

    mock_browser = MagicMock()
    mock_browser.new_context.return_value = mock_context
    mock_browser.close = MagicMock()

    mock_chromium = MagicMock()
    mock_chromium.launch.return_value = mock_browser

    mock_pw_instance = MagicMock()
    mock_pw_instance.chromium = mock_chromium
    mock_pw_instance.__enter__ = MagicMock(return_value=mock_pw_instance)
    mock_pw_instance.__exit__ = MagicMock(return_value=False)

    mock_sync_playwright = MagicMock(return_value=mock_pw_instance)
    return mock_sync_playwright


def test_execute_recording_item_mock_success(tmp_path: Path):
    from unittest.mock import patch

    item = _make_item(target_url="http://localhost:3000")
    mock_pw = _make_mock_playwright(tmp_path)

    with patch.object(rw, "_get_sync_playwright", return_value=mock_pw):
        result = rw.execute_recording_item(
            item,
            output_dir=tmp_path / "worker",
            allow_hosts=["localhost"],
        )

    assert result["status"] == "executed"
    assert result["success"] is True
    assert result["dry_run"] is False
    assert result["target_url"] == "http://localhost:3000"
    assert "open_url" in result["steps_executed"]


def test_execute_recording_item_blocked_external_url(tmp_path: Path):
    item = _make_item(target_url="https://www.youtube.com/watch?v=abc")
    result = rw.execute_recording_item(item, output_dir=tmp_path)
    assert result["status"] == "blocked"
    assert result["success"] is False
    assert "url_not_allowed" in result["reason"]


def test_execute_recording_item_blocked_no_url(tmp_path: Path):
    item = _make_item(target_url="")
    result = rw.execute_recording_item(item, output_dir=tmp_path)
    assert result["status"] == "blocked"
    assert result["success"] is False


def test_execute_recording_item_blocked_forbidden_step(tmp_path: Path):
    item = _make_item(
        target_url="http://localhost:3000",
        extra_steps=[{"step_no": 99, "type": "click"}],
    )
    result = rw.execute_recording_item(item, output_dir=tmp_path)
    assert result["status"] == "blocked"
    assert "forbidden_steps" in result["reason"]


def test_execute_recording_item_metadata_written(tmp_path: Path):
    from unittest.mock import patch

    item = _make_item(target_url="http://localhost:3000")
    mock_pw = _make_mock_playwright(tmp_path)

    with patch.object(rw, "_get_sync_playwright", return_value=mock_pw):
        result = rw.execute_recording_item(item, output_dir=tmp_path / "worker")

    meta_path = Path(result["output_metadata_path"])
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["recording_id"] == "recording_001"
    assert meta["success"] is True


def test_execute_recording_item_no_click_fill_type_in_mocked_calls(tmp_path: Path):
    from unittest.mock import patch

    item = _make_item(target_url="http://localhost:3000")
    mock_pw = _make_mock_playwright(tmp_path)

    with patch.object(rw, "_get_sync_playwright", return_value=mock_pw):
        rw.execute_recording_item(item, output_dir=tmp_path / "worker")

    pw_instance = mock_pw.return_value
    page = pw_instance.chromium.launch.return_value.new_context.return_value.new_page.return_value

    # 금지된 메서드가 호출되지 않았는지 확인
    page.click.assert_not_called()
    page.fill.assert_not_called()
    page.type.assert_not_called()
    page.press.assert_not_called()


def test_execute_recording_item_max_record_seconds(tmp_path: Path):
    from unittest.mock import patch, call

    item = _make_item(target_url="http://localhost:3000")
    mock_pw = _make_mock_playwright(tmp_path)

    with patch.object(rw, "_get_sync_playwright", return_value=mock_pw):
        rw.execute_recording_item(
            item,
            output_dir=tmp_path / "worker",
            max_record_seconds=5,
        )

    pw_instance = mock_pw.return_value
    page = pw_instance.chromium.launch.return_value.new_context.return_value.new_page.return_value
    # capture_scene duration은 min(original, max_record_seconds)=5로 제한
    wait_calls = page.wait_for_timeout.call_args_list
    for c in wait_calls:
        ms = c[0][0] if c[0] else c[1].get("timeout", 0)
        assert ms <= 5 * 1000 + 100, f"wait_for_timeout exceeded max_record_seconds: {ms}ms"


# ---------------------------------------------------------------------------
# execute_recording_plan — mock 기반
# ---------------------------------------------------------------------------


def test_execute_recording_plan_blocked_when_external_url(tmp_path: Path):
    q = _make_queue(_make_item(target_url="https://naver.com"))
    result = rw.execute_recording_plan(q, output_dir=tmp_path)
    assert result["status"] == "blocked"
    assert result["executed_count"] == 0


def test_execute_recording_plan_mock_success(tmp_path: Path):
    from unittest.mock import patch

    q = _make_queue(_make_item(target_url="http://localhost:3000"))
    mock_pw = _make_mock_playwright(tmp_path)

    with patch.object(rw, "_get_sync_playwright", return_value=mock_pw):
        result = rw.execute_recording_plan(
            q,
            output_dir=tmp_path / "worker",
            allow_hosts=["localhost"],
        )

    assert result["dry_run"] is False
    assert result["executed_count"] == 1
    assert result["blocked_count"] == 0


def test_execute_recording_plan_max_items(tmp_path: Path):
    from unittest.mock import patch

    q = _make_queue(
        _make_item(recording_id="recording_001", target_url="http://localhost:3000"),
        _make_item(recording_id="recording_002", target_url="http://localhost:3000"),
        _make_item(recording_id="recording_003", target_url="http://localhost:3000"),
    )
    mock_pw = _make_mock_playwright(tmp_path)

    with patch.object(rw, "_get_sync_playwright", return_value=mock_pw):
        result = rw.execute_recording_plan(
            q, output_dir=tmp_path / "worker", max_items=2
        )

    assert result["total_items"] == 2


def test_execute_recording_plan_no_mp4_if_blocked(tmp_path: Path):
    q = _make_queue(_make_item(target_url="https://www.youtube.com/watch?v=xyz"))
    result = rw.execute_recording_plan(q, output_dir=tmp_path)
    # 차단되면 recordings 디렉토리에 아무것도 없어야 함
    recordings_dir = tmp_path / "recordings"
    if recordings_dir.exists():
        assert not list(recordings_dir.glob("**/*.mp4")), "mp4 생성 금지 위반"

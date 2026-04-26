"""F-4S-13 render_worker 유닛 테스트."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ai_orchestrator.video_production.render_worker import (
    execute_render_item,
    execute_render_plan,
    load_render_plan,
    render_render_worker_markdown,
    validate_ffmpeg_args,
    validate_render_item_for_execute,
    write_render_worker_result_files,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

ALLOWED_INPUT = "runs/video/samples/test.mp4"
ALLOWED_OUTPUT = "runs/video/render/output/test_out.mp4"


def _make_item(
    render_id: str = "render_001",
    input_path: str = ALLOWED_INPUT,
    output_path: str = ALLOWED_OUTPUT,
    program: str = "ffmpeg",
    args: list | None = None,
) -> dict:
    if args is None:
        args = ["-i", input_path, "-c:v", "libx264", output_path]
    return {
        "render_id": render_id,
        "command_plan": {
            "program": program,
            "args": args,
            "display": f"ffmpeg {' '.join(args)}",
            "shell": False,
            "planned_only": False,
        },
    }


def _make_plan(items: list | None = None) -> dict:
    return {
        "generated_at": "2026-04-26T00:00:00Z",
        "ffmpeg_available": False,
        "render_items": items or [],
    }


# ---------------------------------------------------------------------------
# dry_run 기본 동작 — subprocess.run 미호출
# ---------------------------------------------------------------------------


def test_dry_run_does_not_call_subprocess():
    item = _make_item()
    with patch("subprocess.run") as mock_run:
        result = execute_render_item(item, dry_run=True)
    mock_run.assert_not_called()
    assert result["dry_run"] is True
    assert result["executed"] is False
    assert result["status"] == "dry_run"


def test_execute_render_plan_dry_run_no_subprocess():
    plan = _make_plan([_make_item()])
    with patch("subprocess.run") as mock_run:
        result = execute_render_plan(plan, dry_run=True)
    mock_run.assert_not_called()
    assert result["executed_count"] == 0
    assert result["dry_run"] is True


# ---------------------------------------------------------------------------
# ffmpeg_path 없으면 blocked
# ---------------------------------------------------------------------------


def test_blocked_when_no_ffmpeg(tmp_path):
    item = _make_item()
    with patch("shutil.which", return_value=None):
        result = execute_render_item(item, ffmpeg_path=None, dry_run=False)
    assert result["status"] == "blocked"
    assert result["executed"] is False
    assert "ffmpeg_not_found" in result["error"]


# ---------------------------------------------------------------------------
# shell=True 사용 없음 — subprocess.run 호출 시 shell=False
# ---------------------------------------------------------------------------


def test_subprocess_called_with_shell_false(tmp_path):
    inp = tmp_path / "runs" / "video" / "samples" / "in.mp4"
    inp.parent.mkdir(parents=True)
    inp.write_bytes(b"fake")
    out_path = str(tmp_path / "runs" / "video" / "render" / "output" / "out.mp4")

    item = _make_item(input_path=str(inp), output_path=out_path)

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""

    with patch("shutil.which", return_value="/usr/bin/ffmpeg"), \
         patch("subprocess.run", return_value=mock_result) as mock_run, \
         patch(
             "ai_orchestrator.video_production.render_worker.validate_render_item_for_execute",
             return_value=(True, []),
         ):
        execute_render_item(item, ffmpeg_path="/usr/bin/ffmpeg", dry_run=False)

    _, kwargs = mock_run.call_args
    assert kwargs.get("shell") is False or mock_run.call_args[1].get("shell") is False or \
           (len(mock_run.call_args[0]) > 0 and mock_run.call_args[1].get("shell", False) is False)
    # direct check
    assert not mock_run.call_args.kwargs.get("shell", False)


# ---------------------------------------------------------------------------
# args list 검증
# ---------------------------------------------------------------------------


def test_validate_ffmpeg_args_ok():
    ok, issues = validate_ffmpeg_args(["-i", "runs/video/a.mp4", "runs/video/render/output/b.mp4"])
    assert ok
    assert issues == []


def test_validate_ffmpeg_args_non_str():
    ok, issues = validate_ffmpeg_args(["-i", 123])
    assert not ok
    assert any("non_str" in i for i in issues)


def test_validate_ffmpeg_args_shell_metachar():
    ok, issues = validate_ffmpeg_args(["-i", "runs/video/a.mp4; rm -rf /"])
    assert not ok
    assert any("shell_metachar" in i for i in issues)


# ---------------------------------------------------------------------------
# 외부 URL 입력 차단
# ---------------------------------------------------------------------------


def test_external_url_in_input_blocked():
    item = _make_item(input_path="https://example.com/video.mp4")
    ok, reasons = validate_render_item_for_execute(item)
    assert not ok
    assert any("external_url" in r or "url" in r.lower() for r in reasons)


def test_external_url_in_args_blocked():
    item = _make_item(args=["-i", "https://evil.com/x.mp4", ALLOWED_OUTPUT])
    ok, reasons = validate_render_item_for_execute(item)
    assert not ok
    assert any("external_url" in r or "url" in r.lower() for r in reasons)


# ---------------------------------------------------------------------------
# 허용 root 밖 입력 차단
# ---------------------------------------------------------------------------


def test_input_outside_allowed_roots_blocked():
    item = _make_item(input_path="/tmp/secret/video.mp4")
    ok, reasons = validate_render_item_for_execute(item)
    assert not ok
    assert any("outside_allowed_roots" in r or "input_outside" in r for r in reasons)


# ---------------------------------------------------------------------------
# 출력 root 밖 차단
# ---------------------------------------------------------------------------


def test_output_outside_allowed_root_blocked():
    item = _make_item(output_path="/tmp/out.mp4")
    ok, reasons = validate_render_item_for_execute(item)
    assert not ok
    assert any("outside_allowed_root" in r or "output_outside" in r for r in reasons)


# ---------------------------------------------------------------------------
# .mp4 외 출력 차단
# ---------------------------------------------------------------------------


def test_output_non_mp4_blocked():
    item = _make_item(output_path="runs/video/render/output/out.avi")
    ok, reasons = validate_render_item_for_execute(item)
    assert not ok
    assert any("not_mp4" in r or "ext" in r for r in reasons)


# ---------------------------------------------------------------------------
# 존재하지 않는 input 차단
# ---------------------------------------------------------------------------


def test_input_not_found_blocked():
    item = _make_item(input_path="runs/video/nonexistent_xyz.mp4")
    ok, reasons = validate_render_item_for_execute(item)
    assert not ok
    assert any("not_found" in r for r in reasons)


# ---------------------------------------------------------------------------
# valid item mock subprocess 호출 확인
# ---------------------------------------------------------------------------


def test_valid_item_calls_subprocess(tmp_path):
    inp = tmp_path / "runs" / "video" / "in.mp4"
    inp.parent.mkdir(parents=True)
    inp.write_bytes(b"fake")
    out_path = "runs/video/render/output/result.mp4"

    item = _make_item(input_path=str(inp), output_path=out_path)

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""

    with patch("shutil.which", return_value="/usr/bin/ffmpeg"), \
         patch("subprocess.run", return_value=mock_result) as mock_run, \
         patch(
             "ai_orchestrator.video_production.render_worker.validate_render_item_for_execute",
             return_value=(True, []),
         ):
        result = execute_render_item(item, ffmpeg_path="/usr/bin/ffmpeg", dry_run=False)

    mock_run.assert_called_once()
    assert result["executed"] is True
    assert result["status"] == "done"


# ---------------------------------------------------------------------------
# subprocess error 안전 반환
# ---------------------------------------------------------------------------


def test_subprocess_timeout_safe_return():
    item = _make_item()
    with patch("shutil.which", return_value="/usr/bin/ffmpeg"), \
         patch(
             "ai_orchestrator.video_production.render_worker.validate_render_item_for_execute",
             return_value=(True, []),
         ), \
         patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=300)):
        result = execute_render_item(item, ffmpeg_path="/usr/bin/ffmpeg", dry_run=False)

    assert result["status"] == "error"
    assert "timeout" in result["error"]


def test_subprocess_exception_safe_return():
    item = _make_item()
    with patch("shutil.which", return_value="/usr/bin/ffmpeg"), \
         patch(
             "ai_orchestrator.video_production.render_worker.validate_render_item_for_execute",
             return_value=(True, []),
         ), \
         patch("subprocess.run", side_effect=OSError("permission denied")):
        result = execute_render_item(item, ffmpeg_path="/usr/bin/ffmpeg", dry_run=False)

    assert result["status"] == "error"
    assert "exception" in result["error"]


# ---------------------------------------------------------------------------
# JSON/MD 파일 생성
# ---------------------------------------------------------------------------


def test_write_result_files_creates_json_and_md(tmp_path):
    result = execute_render_plan(_make_plan([_make_item()]), dry_run=True)
    paths = write_render_worker_result_files(result, tmp_path / "out")
    assert Path(paths["json"]).exists()
    assert Path(paths["md"]).exists()
    data = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
    assert "results" in data


# ---------------------------------------------------------------------------
# secret 문자열 미포함
# ---------------------------------------------------------------------------


def test_no_secret_in_output():
    result = execute_render_plan(_make_plan([_make_item()]), dry_run=True)
    serialized = json.dumps(result)
    for kw in ("api_key", "client_secret", "password"):
        assert kw not in serialized.lower()


# ---------------------------------------------------------------------------
# 브라우저/Playwright import 없음
# ---------------------------------------------------------------------------


def test_no_playwright_import():
    import ai_orchestrator.video_production.render_worker as m
    src = Path(m.__file__).read_text(encoding="utf-8")
    # 실제 import/사용이 없어야 함 (주석/docstring 제외)
    code_lines = [l for l in src.splitlines() if not l.strip().startswith("#") and '"""' not in l and "'''" not in l]
    code_body = "\n".join(code_lines).lower()
    assert "import playwright" not in code_body
    assert "from playwright" not in code_body
    assert "chromium.launch" not in code_body


# ---------------------------------------------------------------------------
# OAuth/upload/write action 없음
# ---------------------------------------------------------------------------


def test_no_oauth_upload_in_source():
    import ai_orchestrator.video_production.render_worker as m
    src = Path(m.__file__).read_text(encoding="utf-8")
    # 실제 코드에 OAuth 구현/upload 호출이 없어야 함 (주석 제외)
    code_lines = [l for l in src.splitlines() if not l.strip().startswith("#") and '"""' not in l and "'''" not in l]
    code_body = "\n".join(code_lines).lower()
    assert "import oauth" not in code_body
    assert "requests_oauthlib" not in code_body
    assert "youtube.upload" not in code_body
    assert ".upload(" not in code_body

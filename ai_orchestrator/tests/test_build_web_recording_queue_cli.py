"""Tests for scripts/build_web_recording_queue.py CLI (F-4S-7)."""
from __future__ import annotations

import importlib.util
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CLI_PATH = _REPO_ROOT / "scripts" / "build_web_recording_queue.py"
_FIXTURE_PATH = _REPO_ROOT / "samples" / "content_research_fixture.json"


def _load_cli_module():
    spec = importlib.util.spec_from_file_location("build_web_recording_queue_cli", _CLI_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cli(monkeypatch):
    for var in (
        "NAVER_CLIENT_ID",
        "NAVER_CLIENT_SECRET",
        "YOUTUBE_DATA_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    return _load_cli_module()


def _read_json_file(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_video_queue_file(tmp_path: Path) -> Path:
    """F-4S-6 build_video_queue 호출해 실제 video_queue JSON 파일 생성."""
    from ai_orchestrator.content_research import report_builder as rb
    from ai_orchestrator.video_production import queue_builder as qb

    items, fixture_keywords, _ = rb.load_fixture_items(_FIXTURE_PATH)
    keywords = fixture_keywords or rb.normalize_keywords(
        [str(it.get("keyword") or "") for it in items if it.get("keyword")]
    )
    briefs = rb.build_ltx_video_briefs(items, keywords, max_count=20)
    queue = qb.build_video_queue(briefs, max_items=5)
    files = qb.write_video_queue_files(queue, tmp_path / "video_queue_dir", timestamp="20260426_010000")
    return files["json"]


# ---------------------------------------------------------------------------
# Fixture inputs
# ---------------------------------------------------------------------------


def test_cli_fixture_creates_json_and_md(cli, tmp_path: Path):
    out_dir = tmp_path / "video"
    rc = cli.main(
        [
            "--fixture",
            str(_FIXTURE_PATH),
            "--base-url",
            "http://localhost:3000",
            "--out-dir",
            str(out_dir),
            "--max-items",
            "5",
            "--viewport",
            "desktop",
        ]
    )
    assert rc == 0
    files = list(out_dir.iterdir())
    suffixes = {p.suffix for p in files}
    assert {".json", ".md"} <= suffixes
    json_files = [p for p in files if p.suffix == ".json"]
    payload = _read_json_file(json_files[0])
    assert payload["recording_count"] >= 1
    assert "click" in payload["forbidden_step_types"]


def test_cli_fixture_json_summary(cli, tmp_path: Path):
    out_dir = tmp_path / "video"
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.main(
            [
                "--fixture",
                str(_FIXTURE_PATH),
                "--base-url",
                "http://localhost:3000",
                "--out-dir",
                str(out_dir),
                "--max-items",
                "5",
                "--viewport",
                "desktop",
                "--json",
            ]
        )
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["recording_items_count"] >= 1
    assert payload["recording_items_count"] <= 5
    assert payload["max_items"] == 5
    assert payload["viewport"] == "desktop"
    assert payload["base_url_provided"] is True
    assert "files" in payload
    assert payload["sample_titles"]


# ---------------------------------------------------------------------------
# video-queue input
# ---------------------------------------------------------------------------


def test_cli_with_video_queue_file(cli, tmp_path: Path):
    video_queue_path = _build_video_queue_file(tmp_path)
    out_dir = tmp_path / "video_out"
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.main(
            [
                "--video-queue",
                str(video_queue_path),
                "--base-url",
                "http://localhost:3000",
                "--out-dir",
                str(out_dir),
                "--max-items",
                "3",
                "--json",
            ]
        )
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["source"].startswith("video_queue:")
    assert payload["recording_items_count"] == 3
    queue_payload = _read_json_file(Path(payload["files"]["json"]))
    assert queue_payload["queue"][0]["recording_id"] == "recording_001"


def test_cli_with_content_report_path(cli, tmp_path: Path):
    report = {
        "ltx_video_briefs": [
            {
                "title": "테스트 제목",
                "hook": "왜 지금?",
                "scene_ideas": ["오프닝"],
                "subtitle_points": ["핵심"],
                "source_basis": [
                    {"platform": "naver", "source_type": "blog", "url": "https://e.com/x", "title": "t"}
                ],
                "target_platform": "naver_blog",
                "risk_notes": [],
                "score": 1.0,
            }
        ]
    }
    report_path = tmp_path / "content_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    out_dir = tmp_path / "video"
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.main(
            [
                "--content-report",
                str(report_path),
                "--base-url",
                "http://localhost:3000",
                "--out-dir",
                str(out_dir),
                "--max-items",
                "5",
                "--json",
            ]
        )
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["source"].startswith("content_report:")
    assert payload["recording_items_count"] == 1


# ---------------------------------------------------------------------------
# Viewport / max_items / errors
# ---------------------------------------------------------------------------


def test_cli_max_items_caps_queue(cli, tmp_path: Path):
    out_dir = tmp_path / "video"
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.main(
            [
                "--fixture",
                str(_FIXTURE_PATH),
                "--base-url",
                "http://localhost:3000",
                "--out-dir",
                str(out_dir),
                "--max-items",
                "2",
                "--json",
            ]
        )
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["recording_items_count"] == 2


def test_cli_viewport_mobile_applied(cli, tmp_path: Path):
    out_dir = tmp_path / "video"
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.main(
            [
                "--fixture",
                str(_FIXTURE_PATH),
                "--base-url",
                "http://localhost:3000",
                "--out-dir",
                str(out_dir),
                "--max-items",
                "1",
                "--viewport",
                "mobile",
                "--json",
            ]
        )
    assert rc == 0
    payload = json.loads(buf.getvalue())
    queue_payload = _read_json_file(Path(payload["files"]["json"]))
    assert queue_payload["queue"][0]["viewport"]["name"] == "mobile"
    assert queue_payload["queue"][0]["viewport"]["width"] == 390


def test_cli_viewport_wide_applied(cli, tmp_path: Path):
    out_dir = tmp_path / "video"
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.main(
            [
                "--fixture",
                str(_FIXTURE_PATH),
                "--base-url",
                "http://localhost:3000",
                "--out-dir",
                str(out_dir),
                "--max-items",
                "1",
                "--viewport",
                "wide",
                "--json",
            ]
        )
    assert rc == 0
    payload = json.loads(buf.getvalue())
    queue_payload = _read_json_file(Path(payload["files"]["json"]))
    assert queue_payload["queue"][0]["viewport"]["name"] == "wide"


def test_cli_no_base_url_warns_missing_target(cli, tmp_path: Path):
    out_dir = tmp_path / "video"
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.main(
            [
                "--fixture",
                str(_FIXTURE_PATH),
                "--out-dir",
                str(out_dir),
                "--max-items",
                "5",
                "--json",
            ]
        )
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["base_url_provided"] is False
    queue_payload = _read_json_file(Path(payload["files"]["json"]))
    risks_combined = " ".join(
        " ".join(item.get("risk_notes") or [])
        for item in queue_payload["queue"]
    )
    # 적어도 일부 item 은 target_url_missing 또는 external_target 경고가 떠야 한다
    assert ("target_url_missing" in risks_combined) or ("external_target" in risks_combined)


def test_cli_requires_input(cli, tmp_path: Path):
    with pytest.raises(SystemExit):
        cli.main(["--out-dir", str(tmp_path / "video")])


def test_cli_rejects_multiple_inputs(cli, tmp_path: Path):
    with pytest.raises(SystemExit):
        cli.main(
            [
                "--fixture",
                str(_FIXTURE_PATH),
                "--content-report",
                str(_FIXTURE_PATH),
                "--out-dir",
                str(tmp_path / "video"),
            ]
        )


def test_cli_missing_video_queue_raises(cli, tmp_path: Path):
    with pytest.raises(SystemExit):
        cli.main(
            [
                "--video-queue",
                str(tmp_path / "no_such.json"),
                "--out-dir",
                str(tmp_path / "video"),
            ]
        )


def test_cli_invalid_viewport_choice_rejected(cli, tmp_path: Path):
    with pytest.raises(SystemExit):
        cli.main(
            [
                "--fixture",
                str(_FIXTURE_PATH),
                "--out-dir",
                str(tmp_path / "video"),
                "--viewport",
                "ultrawide_4k",
            ]
        )


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------


def test_cli_outputs_no_secret_strings(cli, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "should-not-leak-naver-id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "should-not-leak-naver-secret")
    monkeypatch.setenv("YOUTUBE_DATA_API_KEY", "should-not-leak-yt-key")
    out_dir = tmp_path / "video"
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.main(
            [
                "--fixture",
                str(_FIXTURE_PATH),
                "--base-url",
                "http://localhost:3000",
                "--out-dir",
                str(out_dir),
                "--json",
            ]
        )
    assert rc == 0
    stdout_text = buf.getvalue()
    forbidden = [
        "should-not-leak-naver-id",
        "should-not-leak-naver-secret",
        "should-not-leak-yt-key",
    ]
    for s in forbidden:
        assert s not in stdout_text
    for p in out_dir.iterdir():
        text = p.read_text(encoding="utf-8")
        for s in forbidden:
            assert s not in text


def test_cli_module_does_not_import_browser_or_oauth():
    text = _CLI_PATH.read_text(encoding="utf-8")
    forbidden = (
        "import playwright",
        "from playwright",
        "import selenium",
        "from selenium",
        "import puppeteer",
        "from puppeteer",
        "import requests",
        "from requests",
        "import httpx",
        "from httpx",
        "OAuth2",
        "client_secret=",
        "access_token=",
    )
    for needle in forbidden:
        assert needle not in text, f"forbidden token in CLI: {needle}"

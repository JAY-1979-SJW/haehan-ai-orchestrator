"""Tests for scripts/build_video_queue.py CLI (F-4S-6)."""
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
_CLI_PATH = _REPO_ROOT / "scripts" / "build_video_queue.py"
_FIXTURE_PATH = _REPO_ROOT / "samples" / "content_research_fixture.json"


def _load_cli_module():
    spec = importlib.util.spec_from_file_location("build_video_queue_cli", _CLI_PATH)
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


def test_cli_fixture_creates_json_and_md(cli, tmp_path: Path):
    out_dir = tmp_path / "video"
    rc = cli.main(
        [
            "--fixture",
            str(_FIXTURE_PATH),
            "--out-dir",
            str(out_dir),
            "--max-items",
            "5",
            "--duration",
            "short",
        ]
    )
    assert rc == 0
    files = list(out_dir.iterdir())
    suffixes = {p.suffix for p in files}
    assert {".json", ".md"} <= suffixes


def test_cli_fixture_json_summary_payload(cli, tmp_path: Path):
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
                "--duration",
                "short",
                "--json",
            ]
        )
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["queue_items_count"] >= 1
    assert payload["queue_items_count"] <= 5
    assert payload["max_items"] == 5
    assert payload["default_duration_type"] == "short"
    assert "files" in payload
    assert "json" in payload["files"]
    assert "md" in payload["files"]
    assert payload["sample_titles"]


def test_cli_max_items_caps_queue(cli, tmp_path: Path):
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
                "2",
                "--json",
            ]
        )
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["queue_items_count"] == 2
    queue_json_path = Path(payload["files"]["json"])
    queue_payload = _read_json_file(queue_json_path)
    assert len(queue_payload["queue"]) == 2
    assert queue_payload["queue"][0]["queue_id"] == "video_001"
    assert queue_payload["queue"][1]["queue_id"] == "video_002"


def test_cli_long_duration_for_naver(cli, tmp_path: Path):
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
                "--duration",
                "long",
                "--json",
            ]
        )
    assert rc == 0
    payload = json.loads(buf.getvalue())
    queue_payload = _read_json_file(Path(payload["files"]["json"]))
    # naver_blog/cafe_post 계열은 default_duration=long 을 따라야 함
    naver_items = [
        q for q in queue_payload["queue"]
        if q["target_platform"] in ("naver_blog", "cafe_post")
    ]
    if naver_items:
        assert all(q["duration_type"] == "long" for q in naver_items)


def test_cli_content_report_path(cli, tmp_path: Path):
    # 가짜 content report 작성 — ltx_video_briefs 키만 들어 있어도 동작해야 함
    report = {
        "ltx_video_briefs": [
            {
                "title": "테스트 제목 1",
                "hook": "왜 지금?",
                "scene_ideas": ["오프닝 hook"],
                "subtitle_points": ["핵심 메시지"],
                "source_basis": [
                    {"platform": "naver", "source_type": "blog", "url": "https://e.com", "title": "t"}
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
                "--out-dir",
                str(out_dir),
                "--max-items",
                "5",
                "--json",
            ]
        )
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["queue_items_count"] == 1
    assert "content_report" in payload["source"]


def test_cli_requires_input(cli, tmp_path: Path):
    with pytest.raises(SystemExit):
        cli.main(["--out-dir", str(tmp_path / "video")])


def test_cli_rejects_both_inputs(cli, tmp_path: Path):
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


def test_cli_missing_file_raises(cli, tmp_path: Path):
    with pytest.raises(SystemExit):
        cli.main(
            [
                "--fixture",
                str(tmp_path / "no_such.json"),
                "--out-dir",
                str(tmp_path / "video"),
            ]
        )


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


def test_cli_module_does_not_import_browser_or_ltx_client():
    text = _CLI_PATH.read_text(encoding="utf-8")
    forbidden = (
        "import playwright",
        "from playwright",
        "import selenium",
        "from selenium",
        "import requests",
        "from requests",
        "import httpx",
        "from httpx",
        "ltx_client",
    )
    # 'ltx_video_briefs' / 'build_ltx_video_briefs' / 'build_ltx_prompt' 는 정상 식별자로 허용
    for needle in forbidden:
        assert needle not in text, f"forbidden token in CLI: {needle}"

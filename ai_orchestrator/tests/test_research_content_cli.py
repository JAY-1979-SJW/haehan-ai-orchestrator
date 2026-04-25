"""Tests for scripts/research_content.py CLI (F-4S-4)."""
from __future__ import annotations

import csv
import importlib.util
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CLI_PATH = _REPO_ROOT / "scripts" / "research_content.py"


def _load_cli_module():
    spec = importlib.util.spec_from_file_location("research_content_cli", _CLI_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cli(monkeypatch):
    # CLI 가 .env 의 실제 키를 못 읽도록, 테스트 동안 키를 모두 비운다
    for var in (
        "NAVER_CLIENT_ID",
        "NAVER_CLIENT_SECRET",
        "NAVER_SEARCH_API_BASE_URL",
        "NAVER_SEARCH_API_TIMEOUT_SECONDS",
        "YOUTUBE_DATA_API_KEY",
        "YOUTUBE_DATA_API_BASE_URL",
        "YOUTUBE_DATA_API_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(var, raising=False)
    return _load_cli_module()


def test_cli_dry_run_creates_three_files(cli, tmp_path: Path):
    out_dir = tmp_path / "content"
    rc = cli.main(
        [
            "--keyword",
            "소방공사",
            "--naver-types",
            "blog,news",
            "--youtube-with-details",
            "--out-dir",
            str(out_dir),
        ]
    )
    assert rc == 0
    files = list(out_dir.iterdir())
    suffixes = {p.suffix for p in files}
    assert {".json", ".csv", ".md"} <= suffixes


def test_cli_json_summary_payload_shape(cli, tmp_path: Path):
    out_dir = tmp_path / "content"
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.main(
            [
                "--keyword",
                "소방공사",
                "--naver-types",
                "blog,news,cafearticle",
                "--youtube-with-details",
                "--json",
                "--out-dir",
                str(out_dir),
            ]
        )
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["mode"] == "dry_run"
    assert payload["summary"]["keywords_count"] == 1
    assert payload["summary"]["total_items"] == 0
    assert payload["summary"]["naver_items"] == 0
    assert payload["summary"]["youtube_items"] == 0
    # 키 미설정이므로 dry_run 경고 + global live=False 경고가 누적
    assert payload["warnings_count"] >= 1
    assert "json" in payload["files"]
    assert "csv" in payload["files"]
    assert "md" in payload["files"]


def test_cli_handles_one_side_missing_key(cli, tmp_path: Path, monkeypatch):
    # 네이버 키만 살아 있고 유튜브 키 없음
    monkeypatch.setenv("NAVER_CLIENT_ID", "fake-id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "fake-secret")
    out_dir = tmp_path / "content"
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.main(
            [
                "--keyword",
                "소방공사",
                "--live",
                "--naver-types",
                "blog",
                "--out-dir",
                str(out_dir),
                "--json",
            ]
        )
    # 한쪽 disabled 여도 전체 FAIL 처리되지 않음
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["mode"] == "live"
    # YouTube 쪽은 mock_or_disabled 경고가 붙어야 함
    assert any("youtube" in w.lower() for w in (payload.get("summary", {}).get("platforms_attempted") or []))


def test_cli_keywords_file_loads_lines(cli, tmp_path: Path):
    kw_file = tmp_path / "kw.txt"
    kw_file.write_text("소방공사\n# comment line\n\n스마트팩토리\n", encoding="utf-8")
    out_dir = tmp_path / "content"
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.main(
            [
                "--keywords-file",
                str(kw_file),
                "--out-dir",
                str(out_dir),
                "--json",
            ]
        )
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["summary"]["keywords_count"] == 2


def test_cli_requires_keyword(cli, tmp_path: Path):
    with pytest.raises(SystemExit):
        cli.main(["--out-dir", str(tmp_path / "content")])


def test_cli_outputs_no_secret_strings(cli, tmp_path: Path, monkeypatch):
    # 키를 환경변수에 넣되, 출력 어디에도 노출되지 않아야 함 (live 호출 안 함)
    monkeypatch.setenv("NAVER_CLIENT_ID", "should-not-leak-naver-id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "should-not-leak-naver-secret")
    monkeypatch.setenv("YOUTUBE_DATA_API_KEY", "should-not-leak-yt-key")

    out_dir = tmp_path / "content"
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.main(
            [
                "--keyword",
                "소방공사",
                "--out-dir",
                str(out_dir),
                "--json",
            ]
        )
    assert rc == 0
    stdout_text = buf.getvalue()
    forbidden = ["should-not-leak-naver-id", "should-not-leak-naver-secret", "should-not-leak-yt-key"]
    for s in forbidden:
        assert s not in stdout_text
    # 파일 내용도 검증
    for p in out_dir.iterdir():
        text = p.read_text(encoding="utf-8")
        for s in forbidden:
            assert s not in text


def _strip_string_literals(src: str) -> str:
    import io as _io
    import tokenize as _tok

    out = []
    try:
        tokens = list(_tok.generate_tokens(_io.StringIO(src).readline))
    except Exception:
        return src
    for tok in tokens:
        if tok.type in (
            _tok.STRING,
            _tok.COMMENT,
            _tok.FSTRING_START,
            _tok.FSTRING_MIDDLE,
            _tok.FSTRING_END,
        ):
            continue
        out.append(tok.string)
    return " ".join(out)


def test_cli_module_has_no_browser_or_oauth_imports():
    src = _CLI_PATH.read_text(encoding="utf-8")
    code_only = _strip_string_literals(src)
    forbidden_idents = [
        "playwright",
        "selenium",
        "oauth2",
        "google_auth",
    ]
    for token in forbidden_idents:
        assert token not in code_only, f"forbidden ident in CLI code: {token}"
    assert "import requests" not in code_only
    assert "from requests" not in code_only

    forbidden_calls = [
        "videos().insert(",
        "videos().update(",
        "videos().delete(",
        "comments().insert(",
    ]
    for call in forbidden_calls:
        assert call not in src, f"forbidden write call in CLI: {call}"


# ---------------------------------------------------------------------------
# F-4S-5: fixture / analysis-only CLI
# ---------------------------------------------------------------------------


def _write_cli_fixture(tmp_path: Path) -> Path:
    payload = {
        "keywords": ["소방공사"],
        "items": [
            {
                "platform": "naver",
                "source_type": "blog",
                "keyword": "소방공사",
                "title": "소방공사 비용 5가지 체크리스트",
                "url": "https://example.com/blog/1",
                "summary": "비용 정리",
                "published_at": "20260120",
                "metrics": {"view_count": None, "like_count": None, "comment_count": None},
                "raw_rank": 1,
                "risk_flags": [],
            },
            {
                "platform": "youtube",
                "source_type": "youtube_video",
                "keyword": "소방공사",
                "title": "소방공사 어떻게 하나요? 5가지 핵심",
                "url": "https://www.youtube.com/watch?v=fixq",
                "summary": "초보 가이드",
                "published_at": "2026-02-01T10:00:00Z",
                "metrics": {"view_count": 50000, "like_count": 1000, "comment_count": 80},
                "raw_rank": 1,
                "risk_flags": [],
            },
        ],
    }
    fp = tmp_path / "fix.json"
    fp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return fp


def test_cli_fixture_mode_runs_without_api(cli, tmp_path: Path):
    fp = _write_cli_fixture(tmp_path)
    out_dir = tmp_path / "content"
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.main(
            [
                "--fixture",
                str(fp),
                "--analysis-only",
                "--out-dir",
                str(out_dir),
                "--json",
            ]
        )
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["mode"] == "fixture"
    assert payload["summary"]["total_items"] == 2
    assert payload["ranked_youtube_count"] >= 1
    assert payload["ltx_video_briefs_count"] >= 1


def test_cli_fixture_mode_writes_three_files_with_analysis_md(cli, tmp_path: Path):
    fp = _write_cli_fixture(tmp_path)
    out_dir = tmp_path / "content"
    rc = cli.main(
        [
            "--fixture",
            str(fp),
            "--analysis-only",
            "--out-dir",
            str(out_dir),
        ]
    )
    assert rc == 0
    files = list(out_dir.iterdir())
    suffixes = {p.suffix for p in files}
    assert {".json", ".csv", ".md"} <= suffixes
    md_text = next(p for p in files if p.suffix == ".md").read_text(encoding="utf-8")
    for section in (
        "## YouTube 후보 랭킹",
        "## Naver 후보 랭킹",
        "## 콘텐츠 패턴 분포",
        "## 플랫폼별 권장 전략",
        "## LTX 영상 brief",
    ):
        assert section in md_text


def test_cli_fixture_json_contains_analysis_block(cli, tmp_path: Path):
    fp = _write_cli_fixture(tmp_path)
    out_dir = tmp_path / "content"
    rc = cli.main(
        [
            "--fixture",
            str(fp),
            "--analysis-only",
            "--out-dir",
            str(out_dir),
        ]
    )
    assert rc == 0
    json_path = next(p for p in out_dir.iterdir() if p.suffix == ".json")
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert "analysis" in payload
    assert "ranked_youtube" in payload["analysis"]
    assert "ranked_naver" in payload["analysis"]
    assert "patterns" in payload["analysis"]
    assert "platform_strategy" in payload["analysis"]
    assert "ltx_video_briefs" in payload


def test_cli_fixture_does_not_leak_secret_env(cli, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "should-not-leak-naver-id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "should-not-leak-naver-secret")
    monkeypatch.setenv("YOUTUBE_DATA_API_KEY", "should-not-leak-yt-key")

    fp = _write_cli_fixture(tmp_path)
    out_dir = tmp_path / "content"
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.main(
            [
                "--fixture",
                str(fp),
                "--analysis-only",
                "--out-dir",
                str(out_dir),
                "--json",
            ]
        )
    assert rc == 0
    forbidden = ["should-not-leak-naver-id", "should-not-leak-naver-secret", "should-not-leak-yt-key"]
    for s in forbidden:
        assert s not in buf.getvalue()
    for p in out_dir.iterdir():
        text = p.read_text(encoding="utf-8")
        for s in forbidden:
            assert s not in text


def test_cli_existing_dry_run_still_works(cli, tmp_path: Path):
    """기존 CLI dry-run 동작이 fixture 옵션 추가로 깨지지 않아야 함."""
    out_dir = tmp_path / "content"
    rc = cli.main(
        [
            "--keyword",
            "소방공사",
            "--out-dir",
            str(out_dir),
        ]
    )
    assert rc == 0
    files = list(out_dir.iterdir())
    suffixes = {p.suffix for p in files}
    assert {".json", ".csv", ".md"} <= suffixes


def test_cli_fixture_path_missing_raises(cli, tmp_path: Path):
    with pytest.raises(SystemExit):
        cli.main(
            [
                "--fixture",
                str(tmp_path / "nope.json"),
                "--analysis-only",
                "--out-dir",
                str(tmp_path / "content"),
            ]
        )

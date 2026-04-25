"""Tests for scripts/search_youtube.py CLI (F-4S-3)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "search_youtube.py"


def _load_cli_module():
    spec = importlib.util.spec_from_file_location("search_youtube_cli", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["search_youtube_cli"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def cli_mod():
    return _load_cli_module()


def _clear_env(monkeypatch):
    from ai_orchestrator.connectors import youtube_data_api_config as cfg_mod
    for k in (cfg_mod.ENV_API_KEY, cfg_mod.ENV_BASE_URL, cfg_mod.ENV_TIMEOUT_SECONDS):
        monkeypatch.delenv(k, raising=False)


def test_cli_dry_run_creates_files_and_does_not_call_api(tmp_path, monkeypatch, cli_mod):
    _clear_env(monkeypatch)
    from ai_orchestrator.connectors import youtube_data_api_client as client_mod

    def boom(*a, **kw):
        raise AssertionError("transport must not be called in dry-run")

    monkeypatch.setattr(client_mod, "_default_transport", boom)

    out_dir = tmp_path / "youtube_runs"
    rc = cli_mod.run([
        "--query", "소방공사",
        "--max-results", "3",
        "--out-dir", str(out_dir),
    ])
    assert rc == 0
    files = list(out_dir.iterdir())
    json_files = [f for f in files if f.suffix == ".json"]
    md_files = [f for f in files if f.suffix == ".md"]
    assert len(json_files) == 1
    assert len(md_files) == 1
    payload = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert payload["search"]["mode"] == "mock_or_disabled"
    assert payload["config"]["api_key_present"] is False
    assert payload["quota_cost_total"] == 0


def test_cli_live_without_keys_warns_and_falls_back(tmp_path, monkeypatch, cli_mod, capsys):
    _clear_env(monkeypatch)
    from ai_orchestrator.connectors import youtube_data_api_client as client_mod
    monkeypatch.setattr(
        client_mod, "_default_transport",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no call")),
    )

    out_dir = tmp_path / "youtube_runs"
    rc = cli_mod.run([
        "--query", "소방",
        "--max-results", "2",
        "--live",
        "--out-dir", str(out_dir),
    ])
    assert rc == 0
    captured = capsys.readouterr()
    assert "WARN" in captured.out
    files = list(out_dir.iterdir())
    json_files = [f for f in files if f.suffix == ".json"]
    payload = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert payload["search"]["mode"] == "mock_or_disabled"


def test_cli_outputs_redacted_config_only(tmp_path, monkeypatch, cli_mod, capsys):
    _clear_env(monkeypatch)
    secret = "cli-secret-yt-XYZ"
    monkeypatch.setenv("YOUTUBE_DATA_API_KEY", secret)

    out_dir = tmp_path / "youtube_runs"
    rc = cli_mod.run([
        "--query", "x",
        "--max-results", "3",
        "--out-dir", str(out_dir),
    ])
    assert rc == 0
    captured = capsys.readouterr()
    # console
    assert secret not in captured.out
    # files
    json_path = next(p for p in out_dir.iterdir() if p.suffix == ".json")
    md_path = next(p for p in out_dir.iterdir() if p.suffix == ".md")
    assert secret not in json_path.read_text(encoding="utf-8")
    assert secret not in md_path.read_text(encoding="utf-8")


def test_cli_validation_error_exits_nonzero(tmp_path, monkeypatch, cli_mod):
    _clear_env(monkeypatch)
    out_dir = tmp_path / "youtube_runs"
    rc = cli_mod.run([
        "--query", "x",
        "--max-results", "999",  # out of range
        "--out-dir", str(out_dir),
    ])
    assert rc == 2


def test_cli_live_calls_transport_when_key_present(tmp_path, monkeypatch, cli_mod):
    _clear_env(monkeypatch)
    monkeypatch.setenv("YOUTUBE_DATA_API_KEY", "KEY")

    from ai_orchestrator.connectors import youtube_data_api_client as client_mod

    captured: List[Dict[str, Any]] = []

    def fake_transport(url: str, headers: Dict[str, str], timeout: float) -> Tuple[int, str]:
        captured.append({"url": url, "headers": dict(headers), "timeout": timeout})
        body = json.dumps(
            {
                "items": [
                    {
                        "id": {"videoId": "vid001"},
                        "snippet": {
                            "title": "T",
                            "channelTitle": "C",
                            "publishedAt": "2026-04-01T00:00:00Z",
                        },
                    }
                ]
            }
        )
        return 200, body

    monkeypatch.setattr(client_mod, "_default_transport", fake_transport)

    out_dir = tmp_path / "youtube_runs"
    rc = cli_mod.run([
        "--query", "y",
        "--max-results", "1",
        "--live",
        "--out-dir", str(out_dir),
    ])
    assert rc == 0
    assert len(captured) == 1
    assert "/search" in captured[0]["url"]


def test_cli_with_details_calls_videos_endpoint(tmp_path, monkeypatch, cli_mod):
    _clear_env(monkeypatch)
    monkeypatch.setenv("YOUTUBE_DATA_API_KEY", "KEY")

    from ai_orchestrator.connectors import youtube_data_api_client as client_mod

    captured: List[Dict[str, Any]] = []

    def fake_transport(url: str, headers: Dict[str, str], timeout: float) -> Tuple[int, str]:
        captured.append({"url": url, "headers": dict(headers), "timeout": timeout})
        if "/search" in url:
            body = json.dumps(
                {
                    "items": [
                        {
                            "id": {"videoId": "vid001"},
                            "snippet": {
                                "title": "T1",
                                "channelTitle": "C1",
                                "publishedAt": "2026-04-01T00:00:00Z",
                            },
                        }
                    ]
                }
            )
            return 200, body
        if "/videos" in url:
            body = json.dumps(
                {
                    "items": [
                        {
                            "id": "vid001",
                            "snippet": {
                                "title": "T1",
                                "channelTitle": "C1",
                                "publishedAt": "2026-04-01T00:00:00Z",
                            },
                            "statistics": {
                                "viewCount": "100",
                                "likeCount": "5",
                                "commentCount": "1",
                            },
                            "contentDetails": {"duration": "PT45S"},
                        }
                    ]
                }
            )
            return 200, body
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(client_mod, "_default_transport", fake_transport)

    out_dir = tmp_path / "youtube_runs"
    rc = cli_mod.run([
        "--query", "y",
        "--max-results", "1",
        "--with-details",
        "--live",
        "--out-dir", str(out_dir),
    ])
    assert rc == 0
    assert len(captured) == 2
    assert "/search" in captured[0]["url"]
    assert "/videos" in captured[1]["url"]

    json_path = next(p for p in out_dir.iterdir() if p.suffix == ".json")
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    # quota: search 100 + videos 1 = 101
    assert payload["quota_cost_total"] == 101
    assert payload["details"]["items"][0]["viewCount"] == "100"


def test_cli_does_not_import_browser_or_oauth():
    src = SCRIPT_PATH.read_text(encoding="utf-8")
    lowered = src.lower()
    assert "import playwright" not in lowered
    assert "from playwright" not in lowered
    assert "import selenium" not in lowered
    assert "from selenium" not in lowered
    assert "import requests" not in src
    assert "google.oauth2" not in lowered
    assert "google_auth_oauthlib" not in lowered
    forbidden_actions = [
        "videos.insert",
        "videos.update",
        "videos.delete",
        "comments.insert",
        "commentThreads.insert",
    ]
    for token in forbidden_actions:
        assert token not in src

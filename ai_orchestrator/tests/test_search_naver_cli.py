"""Tests for scripts/search_naver.py CLI (F-4S-2)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "search_naver.py"


def _load_cli_module():
    spec = importlib.util.spec_from_file_location("search_naver_cli", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["search_naver_cli"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def cli_mod():
    return _load_cli_module()


def _clear_env(monkeypatch):
    from ai_orchestrator.connectors import naver_search_api_config as cfg_mod
    for k in (cfg_mod.ENV_CLIENT_ID, cfg_mod.ENV_CLIENT_SECRET,
              cfg_mod.ENV_BASE_URL, cfg_mod.ENV_TIMEOUT_SECONDS):
        monkeypatch.delenv(k, raising=False)


def test_cli_dry_run_creates_files_and_does_not_call_api(tmp_path, monkeypatch, cli_mod, capsys):
    _clear_env(monkeypatch)

    from ai_orchestrator.connectors import naver_search_api_client as client_mod

    def boom(*a, **kw):
        raise AssertionError("transport must not be called in dry-run")

    # patch the default transport — if any code path used it, this would fire
    monkeypatch.setattr(client_mod, "_default_transport", boom)

    out_dir = tmp_path / "naver_runs"
    rc = cli_mod.run([
        "--type", "blog",
        "--query", "소방공사",
        "--display", "3",
        "--out-dir", str(out_dir),
    ])
    assert rc == 0
    files = list(out_dir.iterdir())
    json_files = [f for f in files if f.suffix == ".json"]
    md_files = [f for f in files if f.suffix == ".md"]
    assert len(json_files) == 1
    assert len(md_files) == 1
    payload = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert payload["result"]["mode"] == "mock_or_disabled"
    assert payload["config"]["client_id_present"] is False


def test_cli_live_without_keys_warns_and_falls_back(tmp_path, monkeypatch, cli_mod, capsys):
    _clear_env(monkeypatch)

    from ai_orchestrator.connectors import naver_search_api_client as client_mod
    monkeypatch.setattr(client_mod, "_default_transport",
                        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no call")))

    out_dir = tmp_path / "naver_runs"
    rc = cli_mod.run([
        "--type", "news",
        "--query", "소방",
        "--display", "2",
        "--live",
        "--out-dir", str(out_dir),
    ])
    assert rc == 0
    captured = capsys.readouterr()
    assert "WARN" in captured.out
    files = list(out_dir.iterdir())
    json_files = [f for f in files if f.suffix == ".json"]
    payload = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert payload["result"]["mode"] == "mock_or_disabled"
    warnings = payload["result"].get("warnings") or []
    assert any("missing" in w.lower() or "WARN" in w for w in warnings)


def test_cli_outputs_redacted_config_only(tmp_path, monkeypatch, cli_mod, capsys):
    _clear_env(monkeypatch)
    secret_id = "cli-secret-id-AAA"
    secret_val = "cli-secret-value-BBB"
    monkeypatch.setenv("NAVER_CLIENT_ID", secret_id)
    monkeypatch.setenv("NAVER_CLIENT_SECRET", secret_val)

    out_dir = tmp_path / "naver_runs"
    rc = cli_mod.run([
        "--type", "blog",
        "--query", "x",
        "--display", "3",
        "--out-dir", str(out_dir),
    ])
    assert rc == 0
    captured = capsys.readouterr()
    # console
    assert secret_id not in captured.out
    assert secret_val not in captured.out
    # files
    json_path = next(p for p in out_dir.iterdir() if p.suffix == ".json")
    md_path = next(p for p in out_dir.iterdir() if p.suffix == ".md")
    json_text = json_path.read_text(encoding="utf-8")
    md_text = md_path.read_text(encoding="utf-8")
    assert secret_id not in json_text
    assert secret_val not in json_text
    assert secret_id not in md_text
    assert secret_val not in md_text


def test_cli_validation_error_exits_nonzero(tmp_path, monkeypatch, cli_mod, capsys):
    _clear_env(monkeypatch)
    out_dir = tmp_path / "naver_runs"
    rc = cli_mod.run([
        "--type", "blog",
        "--query", "x",
        "--display", "999",  # out of range
        "--out-dir", str(out_dir),
    ])
    assert rc == 2


def test_cli_live_calls_transport_when_keys_present(tmp_path, monkeypatch, cli_mod):
    _clear_env(monkeypatch)
    monkeypatch.setenv("NAVER_CLIENT_ID", "ID")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "SEC")

    from ai_orchestrator.connectors import naver_search_api_client as client_mod

    captured: List[Dict[str, Any]] = []

    def fake_transport(url: str, headers: Dict[str, str], timeout: float) -> Tuple[int, str]:
        captured.append({"url": url, "headers": dict(headers), "timeout": timeout})
        body = json.dumps({"total": 1, "start": 1, "display": 1,
                           "items": [{"title": "T", "link": "https://x", "description": "d"}]})
        return 200, body

    monkeypatch.setattr(client_mod, "_default_transport", fake_transport)

    out_dir = tmp_path / "naver_runs"
    rc = cli_mod.run([
        "--type", "blog",
        "--query", "y",
        "--display", "1",
        "--live",
        "--out-dir", str(out_dir),
    ])
    assert rc == 0
    assert len(captured) == 1
    assert "/blog.json" in captured[0]["url"]


def test_cli_does_not_import_browser():
    src = SCRIPT_PATH.read_text(encoding="utf-8")
    lowered = src.lower()
    assert "import playwright" not in lowered
    assert "from playwright" not in lowered
    assert "import selenium" not in lowered
    assert "from selenium" not in lowered
    assert "import requests" not in src
    forbidden_actions = ["cafe_join", "cafe_post", "cafe_comment", "join_cafe", "write_post"]
    for token in forbidden_actions:
        assert token not in src

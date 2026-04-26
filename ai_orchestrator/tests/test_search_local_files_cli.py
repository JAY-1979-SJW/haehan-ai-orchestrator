"""LOCAL-FS-1 CLI 테스트 — search_local_files.py 검증."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

_CLI_PATH = REPO_ROOT / "scripts" / "search_local_files.py"
_spec = importlib.util.spec_from_file_location("search_local_files", _CLI_PATH)
_cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cli)


def _run(args: list[str], tmp_path: Path) -> tuple[int, str]:
    """CLI main()을 argv를 통해 실행하고 stdout을 캡처한다."""
    import io
    out = io.StringIO()
    with patch.object(sys, "argv", ["search_local_files.py"] + args), \
         patch("sys.stdout", out):
        try:
            code = _cli.main()
        except SystemExit as e:
            code = int(e.code) if e.code is not None else 0
    return code, out.getvalue()


def _make_project(tmp_path: Path) -> Path:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "kakao_runner.py").write_text("# kakao integration\nstorage_state = None", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "kakao.md").write_text("## Kakao 설정\nstorage_state 보안 등급", encoding="utf-8")
    (tmp_path / "ai_orchestrator").mkdir()
    (tmp_path / "ai_orchestrator" / "config.py").write_text("api_key=placeholder\n# kakao", encoding="utf-8")
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "token.json").write_text('{"token":"secret123"}', encoding="utf-8")
    (tmp_path / ".env").write_text("PASSWORD=topsecret", encoding="utf-8")
    return tmp_path


def test_cli_query_returns_results(tmp_path):
    _make_project(tmp_path)
    code, out = _run(["--root", str(tmp_path), "--query", "kakao", "--json",
                       "--out-dir", str(tmp_path / "out")], tmp_path)
    assert code == 0
    data = json.loads(out)
    assert data["result_count"] > 0


def test_cli_index_mode_no_query(tmp_path):
    _make_project(tmp_path)
    code, out = _run(["--root", str(tmp_path), "--json",
                       "--out-dir", str(tmp_path / "out")], tmp_path)
    assert code == 0
    data = json.loads(out)
    assert data["mode"] == "index"
    assert data["total_files"] > 0


def test_cli_no_secrets_in_results(tmp_path):
    _make_project(tmp_path)
    code, out = _run(["--root", str(tmp_path), "--query", "token", "--json", "--preview",
                       "--out-dir", str(tmp_path / "out")], tmp_path)
    assert code == 0
    # secrets/ 파일은 결과에 없어야 함
    data = json.loads(out)
    paths = data.get("result_paths", [])
    assert not any("secrets" in p for p in paths)


def test_cli_no_env_in_results(tmp_path):
    _make_project(tmp_path)
    code, out = _run(["--root", str(tmp_path), "--query", "PASSWORD", "--json",
                       "--out-dir", str(tmp_path / "out")], tmp_path)
    assert code == 0
    data = json.loads(out)
    paths = data.get("result_paths", [])
    assert not any(".env" in p for p in paths)


def test_cli_file_type_filter(tmp_path):
    _make_project(tmp_path)
    code, out = _run(["--root", str(tmp_path), "--query", "kakao",
                       "--file-type", "md", "--json",
                       "--out-dir", str(tmp_path / "out")], tmp_path)
    assert code == 0
    data = json.loads(out)
    for p in data.get("result_paths", []):
        assert p.endswith(".md")


def test_cli_max_results(tmp_path):
    (tmp_path / "scripts").mkdir()
    for i in range(30):
        (tmp_path / "scripts" / f"file_{i}.py").write_text("keyword found", encoding="utf-8")
    code, out = _run(["--root", str(tmp_path), "--query", "keyword",
                       "--max-results", "5", "--json",
                       "--out-dir", str(tmp_path / "out")], tmp_path)
    assert code == 0
    data = json.loads(out)
    assert data["result_count"] <= 5


def test_cli_creates_result_files(tmp_path):
    _make_project(tmp_path)
    out_dir = tmp_path / "out"
    code, out = _run(["--root", str(tmp_path), "--query", "kakao", "--json",
                       "--out-dir", str(out_dir)], tmp_path)
    assert code == 0
    data = json.loads(out)
    assert Path(data["output_json"]).exists()
    assert Path(data["output_md"]).exists()


def test_cli_glob_filter(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("guide content", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "run.py").write_text("# guide code", encoding="utf-8")
    code, out = _run(["--root", str(tmp_path), "--query", "guide",
                       "--glob", "*.md", "--json",
                       "--out-dir", str(tmp_path / "out")], tmp_path)
    assert code == 0
    data = json.loads(out)
    for p in data.get("result_paths", []):
        assert p.endswith(".md")


def test_cli_preview_redacts_api_key(tmp_path):
    secret = "a" * 40
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "config.py").write_text(
        f"# kakao config\napi_key={secret}\n", encoding="utf-8"
    )
    out_dir = tmp_path / "out"
    code, out = _run(["--root", str(tmp_path), "--query", "kakao", "--preview", "--json",
                       "--out-dir", str(out_dir)], tmp_path)
    assert code == 0
    result_json = json.loads(out)
    json_text = Path(result_json["output_json"]).read_text(encoding="utf-8")
    assert secret not in json_text

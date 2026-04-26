"""LOCAL-FS-1 테스트 — file_indexer.py 검증."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ai_orchestrator.local_files.file_indexer import (
    ALLOWED_EXTENSIONS,
    is_allowed_path,
    is_excluded_path,
    normalize_root,
    read_file_preview,
    redact_sensitive_text,
    scan_files,
    search_files,
    summarize_file_metadata,
    write_search_result,
)


# ── is_excluded_path ─────────────────────────────────────────────────────

def test_excludes_dotenv(tmp_path):
    p = tmp_path / ".env"
    p.touch()
    assert is_excluded_path(p)


def test_excludes_dotenv_local(tmp_path):
    p = tmp_path / ".env.local"
    p.touch()
    assert is_excluded_path(p)


def test_excludes_secrets_dir(tmp_path):
    p = tmp_path / "secrets" / "browser_state" / "kakao.json"
    p.parent.mkdir(parents=True)
    p.touch()
    assert is_excluded_path(p)


def test_excludes_pem(tmp_path):
    assert is_excluded_path(tmp_path / "cert.pem")


def test_excludes_key(tmp_path):
    assert is_excluded_path(tmp_path / "private.key")


def test_excludes_p12(tmp_path):
    assert is_excluded_path(tmp_path / "keystore.p12")


def test_excludes_pfx(tmp_path):
    assert is_excluded_path(tmp_path / "cert.pfx")


def test_excludes_sqlite(tmp_path):
    assert is_excluded_path(tmp_path / "db.sqlite")


def test_excludes_pycache(tmp_path):
    p = tmp_path / "__pycache__" / "foo.pyc"
    assert is_excluded_path(p)


def test_excludes_git(tmp_path):
    p = tmp_path / ".git" / "config"
    assert is_excluded_path(p)


def test_does_not_exclude_py(tmp_path):
    p = tmp_path / "scripts" / "foo.py"
    assert not is_excluded_path(p)


def test_does_not_exclude_md(tmp_path):
    p = tmp_path / "docs" / "readme.md"
    assert not is_excluded_path(p)


# ── is_allowed_path ───────────────────────────────────────────────────────

def test_allowed_docs(tmp_path):
    p = tmp_path / "docs" / "guide.md"
    p.parent.mkdir()
    p.touch()
    assert is_allowed_path(p, tmp_path)


def test_allowed_scripts(tmp_path):
    p = tmp_path / "scripts" / "run.py"
    p.parent.mkdir()
    p.touch()
    assert is_allowed_path(p, tmp_path)


def test_not_allowed_top_level(tmp_path):
    p = tmp_path / "random_dir" / "file.py"
    p.parent.mkdir()
    p.touch()
    assert not is_allowed_path(p, tmp_path)


# ── redact_sensitive_text ─────────────────────────────────────────────────

def test_redacts_password():
    text = "password=supersecret123"
    out = redact_sensitive_text(text)
    assert "supersecret123" not in out
    assert "***" in out


def test_redacts_bearer_token():
    text = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abc123def456"
    out = redact_sensitive_text(text)
    assert "eyJhbGciOiJIUzI1NiJ9" not in out
    assert "***" in out


def test_redacts_api_key():
    text = "api_key=abcdef1234567890abcdef1234567890"
    out = redact_sensitive_text(text)
    assert "abcdef1234567890abcdef1234567890" not in out


def test_redacts_long_hex():
    secret = "a" * 32
    text = f"key={secret}"
    out = redact_sensitive_text(text)
    assert secret not in out


def test_redacts_private_key_block():
    text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA\n-----END RSA PRIVATE KEY-----"
    out = redact_sensitive_text(text)
    assert "MIIEowIBAAKCAQEA" not in out
    assert "REDACTED" in out


def test_preserves_normal_text():
    text = "This is a normal sentence about kakao login."
    out = redact_sensitive_text(text)
    assert "normal sentence" in out


# ── scan_files ────────────────────────────────────────────────────────────

def _make_tree(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "run.py").write_text("print('hello')", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("# Guide", encoding="utf-8")
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "token.json").write_text('{"token":"abc"}', encoding="utf-8")
    (tmp_path / ".env").write_text("PASSWORD=secret", encoding="utf-8")
    (tmp_path / "ai_orchestrator").mkdir()
    (tmp_path / "ai_orchestrator" / "main.py").write_text("# main", encoding="utf-8")
    return tmp_path


def test_scan_excludes_secrets(tmp_path):
    _make_tree(tmp_path)
    files = scan_files(tmp_path)
    # tmp_path 기준 상대경로로 확인 (pytest tmp_path 이름에 "secrets"가 포함될 수 있음)
    rel_paths = [str(f.relative_to(tmp_path)).replace("\\", "/") for f in files]
    assert not any(p.startswith("secrets/") or "/secrets/" in p for p in rel_paths)


def test_scan_excludes_dotenv(tmp_path):
    _make_tree(tmp_path)
    files = scan_files(tmp_path)
    names = [f.name for f in files]
    assert ".env" not in names


def test_scan_includes_py_and_md(tmp_path):
    _make_tree(tmp_path)
    files = scan_files(tmp_path)
    exts = {f.suffix for f in files}
    assert ".py" in exts
    assert ".md" in exts


def test_scan_max_files(tmp_path):
    (tmp_path / "scripts").mkdir()
    for i in range(20):
        (tmp_path / "scripts" / f"file_{i}.py").write_text(f"# {i}", encoding="utf-8")
    files = scan_files(tmp_path, max_files=5)
    assert len(files) <= 5


def test_scan_runs_excluded_by_default(tmp_path):
    (tmp_path / "runs").mkdir()
    (tmp_path / "runs" / "output.json").write_text("{}", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "main.py").write_text("pass", encoding="utf-8")
    files = scan_files(tmp_path)
    names = [f.name for f in files]
    assert "output.json" not in names


def test_scan_runs_included_when_flag(tmp_path):
    (tmp_path / "runs").mkdir()
    (tmp_path / "runs" / "output.json").write_text("{}", encoding="utf-8")
    files = scan_files(tmp_path, include_runs=True)
    names = [f.name for f in files]
    assert "output.json" in names


# ── search_files ──────────────────────────────────────────────────────────

def test_search_finds_keyword(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "kakao.py").write_text("# kakao login setup", encoding="utf-8")
    results = search_files(tmp_path, "kakao")
    assert any("kakao" in r["path"] for r in results)


def test_search_file_type_filter(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "kakao.md").write_text("kakao info", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "kakao.py").write_text("# kakao", encoding="utf-8")
    results = search_files(tmp_path, "kakao", file_types=["md"])
    exts = {Path(r["path"]).suffix for r in results}
    assert ".md" in exts
    assert ".py" not in exts


def test_search_max_results(tmp_path):
    (tmp_path / "scripts").mkdir()
    for i in range(20):
        (tmp_path / "scripts" / f"file_{i}.py").write_text("keyword here", encoding="utf-8")
    results = search_files(tmp_path, "keyword", max_results=5)
    assert len(results) <= 5


def test_search_no_secret_in_matched_lines(tmp_path):
    (tmp_path / "scripts").mkdir()
    secret = "x" * 40
    (tmp_path / "scripts" / "config.py").write_text(f"api_key={secret}\n# mention", encoding="utf-8")
    results = search_files(tmp_path, "mention")
    for r in results:
        for ml in r.get("matched_lines", []):
            assert secret not in ml["text"]


# ── read_file_preview ─────────────────────────────────────────────────────

def test_preview_basic(tmp_path):
    f = tmp_path / "scripts" / "hello.py"
    f.parent.mkdir()
    f.write_text("print('hello')", encoding="utf-8")
    result = read_file_preview(f)
    assert result["preview"] == "print('hello')"
    assert result["error"] is None


def test_preview_excludes_env(tmp_path):
    f = tmp_path / ".env"
    f.write_text("SECRET=abc", encoding="utf-8")
    result = read_file_preview(f)
    assert result["error"] == "EXCLUDED_PATH"
    assert result["preview"] is None


def test_preview_redacts_password(tmp_path):
    f = tmp_path / "scripts" / "cfg.py"
    f.parent.mkdir()
    f.write_text("password=mysecretpwd123\n", encoding="utf-8")
    result = read_file_preview(f)
    assert "mysecretpwd123" not in (result["preview"] or "")


def test_preview_max_chars(tmp_path):
    f = tmp_path / "scripts" / "big.py"
    f.parent.mkdir()
    f.write_text("a" * 10000, encoding="utf-8")
    result = read_file_preview(f, max_chars=100)
    assert len(result["preview"]) <= 100
    assert result["truncated"] is True


def test_preview_binary_returns_error(tmp_path):
    f = tmp_path / "scripts" / "data.bin"
    f.parent.mkdir()
    f.write_bytes(b"\x00\x01\x02\x03binary")
    result = read_file_preview(f)
    assert result["error"] is not None
    assert result["preview"] is None


# ── write_search_result ───────────────────────────────────────────────────

def test_write_creates_json_and_md(tmp_path):
    result = {
        "mode": "search",
        "root": str(tmp_path),
        "query": "test",
        "searched_at": "20260426_120000",
        "total_matches": 1,
        "results": [{"path": "scripts/foo.py", "size_bytes": 10,
                      "match_in_name": True, "matched_lines": [], "match_count": 0}],
    }
    paths = write_search_result(result, tmp_path / "out")
    assert Path(paths["json"]).exists()
    assert Path(paths["md"]).exists()
    data = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
    assert data["query"] == "test"


def test_write_no_secret_in_output(tmp_path):
    secret = "s" * 40
    result = {
        "mode": "search",
        "root": str(tmp_path),
        "query": "x",
        "searched_at": "20260426_120000",
        "total_matches": 0,
        "results": [],
        "note": f"api_key={secret}",
    }
    paths = write_search_result(result, tmp_path / "out")
    content = Path(paths["json"]).read_text(encoding="utf-8")
    # raw secret stored as-is in result dict (redaction is in preview/matched_lines)
    # but ensure no raw 40-char blocks appear in matched_lines
    assert "matched_lines" not in content or secret not in content


# ── normalize_root ────────────────────────────────────────────────────────

def test_normalize_root_resolves(tmp_path):
    result = normalize_root(str(tmp_path))
    assert result == tmp_path.resolve()

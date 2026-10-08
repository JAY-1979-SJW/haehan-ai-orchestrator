"""temp_oauth_revoke: import/환경변수 검사만으로 비가역 권한 철회가 실행되지 않는지 검증.

대상 스크립트는 import·실행하지 않고 ast 로 구조만 검사한다(구조 시험).
동작 시험은 가드가 생긴 뒤 importlib 로 로드하여 가짜 함수를 주입한다.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

TARGET = Path(__file__).resolve().parents[2] / "scripts" / "archive" / "one_off" / "temp_oauth_revoke.py"
ENV_KEYS = ("YOUTUBE_CLIENT_SECRETS_FILE", "YOUTUBE_OAUTH_TOKEN_FILE")


def _tree() -> ast.Module:
    return ast.parse(TARGET.read_text(encoding="utf-8"))


def _is_main_guard(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "__name__"
        and any(isinstance(c, ast.Constant) and c.value == "__main__" for c in node.test.comparators)
    )


def test_no_toplevel_side_effects_and_main_guard() -> None:
    tree = _tree()
    offenders = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef)) or _is_main_guard(node):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue  # docstring
        has_call = any(isinstance(n, ast.Call) for n in ast.walk(node))
        sets_subscript = isinstance(node, ast.Assign) and any(isinstance(t, ast.Subscript) for t in node.targets)
        if has_call or sets_subscript:
            offenders.append(node.lineno)
    assert not offenders, f"모듈 최상위 실행 문장: {offenders}"
    assert any(_is_main_guard(n) for n in tree.body), "__main__ 가드 없음"
    assert any(isinstance(n, ast.FunctionDef) and n.name == "main" for n in tree.body)


def _load():
    spec = importlib.util.spec_from_file_location("temp_oauth_revoke_under_test", TARGET)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mod(monkeypatch):
    m = _load()
    calls = {"agent": 0, "revoke": 0, "reauth": 0}
    monkeypatch.setattr(m, "_load_env", lambda: None)
    monkeypatch.setattr(
        m,
        "_make_agent",
        lambda: calls.__setitem__("agent", calls["agent"] + 1) or __import__("types").SimpleNamespace(page=None),
    )
    monkeypatch.setattr(m, "_revoke_permissions", lambda page: calls.__setitem__("revoke", calls["revoke"] + 1))
    monkeypatch.setattr(
        m, "_reauthorize", lambda page, secrets, token: calls.__setitem__("reauth", calls["reauth"] + 1)
    )
    m.calls = calls
    return m


def test_default_is_dry_run(mod, monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setenv(ENV_KEYS[0], str(tmp_path / "s.json"))
    monkeypatch.setenv(ENV_KEYS[1], str(tmp_path / "t.json"))
    assert mod.main([]) == 0
    assert mod.calls == {"agent": 0, "revoke": 0, "reauth": 0}
    out = capsys.readouterr().out
    assert str(tmp_path) not in out  # 경로/값 비출력


def test_execute_without_env_aborts_before_revoke(mod, monkeypatch) -> None:
    for k in ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    assert mod.main(["--execute"]) != 0
    assert mod.calls == {"agent": 0, "revoke": 0, "reauth": 0}
    monkeypatch.setenv(ENV_KEYS[0], "x")  # 토큰 경로만 없음
    assert mod.main(["--execute"]) != 0
    assert mod.calls["revoke"] == 0 and mod.calls["agent"] == 0


def test_execute_with_env_revokes_once(mod, monkeypatch, tmp_path) -> None:
    secrets = tmp_path / "s.json"
    secrets.write_text("{}", encoding="utf-8")
    monkeypatch.setenv(ENV_KEYS[0], str(secrets))
    monkeypatch.setenv(ENV_KEYS[1], str(tmp_path / "t.json"))
    assert mod.main(["--execute"]) == 0
    assert mod.calls == {"agent": 1, "revoke": 1, "reauth": 1}

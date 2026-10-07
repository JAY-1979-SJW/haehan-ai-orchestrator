"""audit_kit_gate — git mv(이름 변경) 파일은 옛 위치의 기존 mypy 오류를 신규로 잡지 않는다.

배경(2026-10-07): '편집 전 대비 새 오류만' 비교가 HEAD:<같은 경로> 를 기준으로 삼아서, 이동한 파일은 HEAD 에 없는 새 파일로 보여 옛 위치의
기존 오류가 전부 신규로 잡혔다(W2 S1 커밋에서 오탐 3건). staged 목록을 `-M --name-status` 로 읽어 R 이면 HEAD:<옛 경로> 를 기준으로 쓴다.
mypy 는 이 시험을 도는 파이썬(sys.executable)의 것을 쓴다.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.ops import audit_kit_gate as gate

BAD = "x: int = 'not an int'\n"  # mypy: Incompatible types in assignment
BAD2 = "y: str = 123\n"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(root), capture_output=True, text=True, encoding="utf-8", errors="replace", check=True
    ).stdout


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "old").mkdir()
    (tmp_path / "old" / "mod.py").write_text(
        "def f() -> int:\n    return 1\n\n" + BAD, encoding="utf-8"
    )  # 기존 오류 1개
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    return tmp_path


def _keys(res: tuple[list[str], str]) -> list[str]:
    findings, why = res
    assert why == "", why
    return findings


def test_moved_file_without_changes_has_no_new_errors(repo):
    """① 이동 + 무변경 = 신규 0."""
    (repo / "new").mkdir()
    _git(repo, "mv", "old/mod.py", "new/mod.py")
    path = repo / "new" / "mod.py"
    assert _keys(gate._mypy_against_head(sys.executable, path, repo, old_rel="old/mod.py")) == []


def test_without_old_path_the_same_move_is_misreported_as_new(repo):
    """회귀 방지: 옛 경로를 모르면(예전 동작) 기존 오류 1개가 신규로 잡힌다 — 이 수정이 필요한 이유."""
    (repo / "new").mkdir()
    _git(repo, "mv", "old/mod.py", "new/mod.py")
    path = repo / "new" / "mod.py"
    assert len(_keys(gate._mypy_against_head(sys.executable, path, repo))) == 1


def test_moved_file_with_one_new_error_reports_exactly_one(repo):
    """② 이동 + 새 오류 1개 = 신규 1(기존 오류는 제외)."""
    (repo / "new").mkdir()
    _git(repo, "mv", "old/mod.py", "new/mod.py")
    path = repo / "new" / "mod.py"
    path.write_text(path.read_text(encoding="utf-8") + BAD2, encoding="utf-8")
    found = _keys(gate._mypy_against_head(sys.executable, path, repo, old_rel="old/mod.py"))
    assert len(found) == 1 and "str" in found[0]


def test_pure_new_file_reports_all_errors_as_new(repo):
    """③ 순수 새 파일 = 전부 신규."""
    path = repo / "brand_new.py"
    path.write_text(BAD + BAD2, encoding="utf-8")
    assert len(_keys(gate._mypy_against_head(sys.executable, path, repo))) == 2


def test_modified_file_still_compares_with_its_own_head_version(repo):
    """수정(M)은 예전처럼 같은 경로의 HEAD 와 비교한다."""
    path = repo / "old" / "mod.py"
    path.write_text(path.read_text(encoding="utf-8") + BAD2, encoding="utf-8")
    assert len(_keys(gate._mypy_against_head(sys.executable, path, repo))) == 1


def test_staged_changes_reports_old_path_for_renames_only(repo):
    """staged 목록: R 은 (새 경로, 옛 경로), 새 파일(A)·수정(M)은 옛 경로 None, 삭제는 제외."""
    (repo / "new").mkdir()
    _git(repo, "mv", "old/mod.py", "new/mod.py")
    (repo / "fresh.py").write_text("z = 1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    got = {(p.relative_to(repo).as_posix(), old) for p, old in gate._staged_python_changes()}
    assert got == {("new/mod.py", "old/mod.py"), ("fresh.py", None)}
    assert [p.relative_to(repo).as_posix() for p in gate._staged_python_files()].count("new/mod.py") == 1


def test_check_file_passes_old_path_through(repo, monkeypatch, tmp_path):
    """check_file 이 old_rel 을 mypy 비교까지 전달한다(가짜 audit-kit: 아무 문제 없다고 답함)."""
    fake = tmp_path / "fake_kit.py"
    fake.write_text("import sys\nsys.stdin.read()\nraise SystemExit(0)\n", encoding="utf-8")
    monkeypatch.setattr(gate, "mypy_python", lambda _kit: sys.executable)
    (repo / "new").mkdir()
    _git(repo, "mv", "old/mod.py", "new/mod.py")
    path = repo / "new" / "mod.py"
    kit = [sys.executable, str(fake)]
    assert gate.check_file(kit, path, repo, old_rel="old/mod.py") == ([], "")
    findings, _ = gate.check_file(kit, path, repo)  # 옛 경로 모르면 기존 오류가 신규로 보인다
    assert len(findings) == 1

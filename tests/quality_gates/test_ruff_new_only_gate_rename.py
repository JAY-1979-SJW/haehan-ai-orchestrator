"""ruff_new_only_gate — git mv(이름 변경) 파일은 git 설정(diff.renames)과 무관하게 '새 줄'로 잡히지 않는다.

기본 git 은 이름 변경을 감지하지만 diff.renames=false 인 환경에서는 이동한 파일의 모든 줄이 새 줄이 되어 기존 위반이 전부 신규로 차단됐다.
`-M` 을 명시해 같은 결과가 나오게 했다(2026-10-07).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools.repo_gates import ruff_new_only_gate as gate

BODY = "import os\n\n\ndef f():\n    return 1\n"


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
    (tmp_path / "old" / "m.py").write_text(BODY * 3, encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    return tmp_path


@pytest.mark.parametrize("renames_setting", [None, "false"])
def test_unchanged_move_has_no_changed_lines(repo, renames_setting):
    """① 이동 + 무변경 = 바뀐 줄 0 — diff.renames 설정이 꺼져 있어도 같다."""
    if renames_setting:
        _git(repo, "config", "diff.renames", renames_setting)
    (repo / "new").mkdir()
    _git(repo, "mv", "old/m.py", "new/m.py")
    assert gate.changed_lines_staged() == {"new/m.py": set()} or gate.changed_lines_staged() == {}


@pytest.mark.parametrize("renames_setting", [None, "false"])
def test_moved_and_edited_file_reports_only_the_edited_line(repo, renames_setting):
    """② 이동 + 한 줄 추가 = 그 줄만 바뀐 줄."""
    if renames_setting:
        _git(repo, "config", "diff.renames", renames_setting)
    (repo / "new").mkdir()
    _git(repo, "mv", "old/m.py", "new/m.py")
    path = repo / "new" / "m.py"
    path.write_text(path.read_text(encoding="utf-8") + "extra = 1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    changed = gate.changed_lines_staged() or {}
    assert changed.get("new/m.py") == {16}  # 원본 15줄 뒤 한 줄


def test_pure_new_file_is_all_new_lines(repo):
    """③ 순수 새 파일 = 모든 줄이 새 줄."""
    (repo / "fresh.py").write_text(BODY, encoding="utf-8")
    _git(repo, "add", "-A")
    assert (gate.changed_lines_staged() or {}).get("fresh.py") == set(range(1, 6))


def test_changed_lines_between_commits_is_rename_aware_too(repo):
    """커밋 사이 비교(verify_change 가 쓰는 경로)도 같다."""
    _git(repo, "config", "diff.renames", "false")
    (repo / "new").mkdir()
    _git(repo, "mv", "old/m.py", "new/m.py")
    _git(repo, "commit", "-qm", "move")
    changed = gate.changed_lines_between("HEAD~1", "HEAD") or {}
    assert not changed.get("new/m.py")  # 무변경 이동은 바뀐 줄 없음

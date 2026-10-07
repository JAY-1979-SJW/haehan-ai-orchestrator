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


# ── 커밋 단계 일괄 검사(check_files): 파일별 check_file 과 같은 결과, mypy 는 기준 폴더별 1회 ─────────────


def _fake_kit(tmp_path: Path) -> list[str]:
    fake = tmp_path / "fake_kit_ok.py"
    fake.write_text("import sys\nsys.stdin.read()\nraise SystemExit(0)\n", encoding="utf-8")
    return [sys.executable, str(fake)]


def test_batched_check_files_equals_per_file_check(repo, monkeypatch, tmp_path):
    """기존 오류만 있는 수정·새 오류가 생긴 수정(패키지 안)·이름 변경+새 오류·새 파일 — 일괄 결과가 파일별 결과와 같다."""
    (repo / "keep.py").write_text(BAD, encoding="utf-8")
    (repo / "pkg").mkdir()
    (repo / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "pkg" / "a.py").write_text("v = 1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "more")
    (repo / "keep.py").write_text(BAD + "# 주석만 추가\n", encoding="utf-8")  # 기존 오류만
    (repo / "pkg" / "a.py").write_text("v = 1\n" + BAD2, encoding="utf-8")  # 새 오류
    (repo / "new").mkdir()
    _git(repo, "mv", "old/mod.py", "new/mod.py")
    moved = repo / "new" / "mod.py"
    moved.write_text(moved.read_text(encoding="utf-8") + BAD2, encoding="utf-8")  # 이름 변경 + 새 오류
    (repo / "fresh.py").write_text(BAD, encoding="utf-8")  # 새 파일
    _git(repo, "add", "-A")
    monkeypatch.setattr(gate, "mypy_python", lambda _kit: sys.executable)
    kit = _fake_kit(tmp_path)
    items = gate._staged_python_changes()
    assert len(items) == 4 and ("new/mod.py" in {p.relative_to(repo).as_posix() for p, _ in items})

    per_file = [(p, *gate.check_file(kit, p, repo, old)) for p, old in items]
    calls: list[list[str]] = []
    real_run = gate.subprocess.run

    def counting_run(cmd, *a, **k):
        if "mypy" in cmd:
            calls.append(cmd)
        return real_run(cmd, *a, **k)

    monkeypatch.setattr(gate.subprocess, "run", counting_run)
    batched = gate.check_files(kit, items, repo)
    assert batched == per_file
    got = {p.relative_to(repo).as_posix(): len(found) for p, found, why in batched if not why}
    assert got == {"keep.py": 0, "pkg/a.py": 1, "new/mod.py": 1, "fresh.py": 1}
    assert len(calls) == 2  # 기준 폴더 2곳(저장소 루트, new/) — 예전엔 파일당 현재·HEAD 로 7회
    assert not list(repo.rglob("_mypy_base_*"))  # 비교용 사본은 남기지 않는다


class _Proc:
    def __init__(self, rc: int, out: bytes = b"", err: bytes = b"") -> None:
        self.returncode, self.stdout, self.stderr = rc, out, err


def test_mypy_runs_once_for_many_files_and_splits_output(tmp_path, monkeypatch):
    """같은 폴더의 N개 파일(+HEAD 사본)은 mypy 1회. 출력 경로가 절대/상대 어느 쪽이든 파일별로 나눠 신규 오류만 낸다."""
    files = [tmp_path / f"m{i}.py" for i in range(6)]
    for f in files:
        f.write_text("x = 1\n", encoding="utf-8")
    with_base = {f"m{i}.py" for i in range(0, 6, 2)}
    monkeypatch.setattr(gate, "_head_blobs", lambda _root, rels: {r: (b"x = 0\n" if r in with_base else None) for r in rels})
    calls = []

    def fake_run(cmd, *_a, **_k):
        assert "mypy" in cmd
        calls.append(cmd)
        lines = []
        for i, arg in enumerate(a for a in cmd if a.endswith(".py")):
            shown = arg if i % 2 else str(Path(arg).relative_to(tmp_path))
            lines.append(f"{shown}:3: error: shared  [misc]")
            if "_mypy_base_" not in arg:
                lines.append(f"{shown}:4:2: error: only {Path(arg).name}  [misc]")
        return _Proc(1, "\n".join(lines).encode())

    monkeypatch.setattr(gate.subprocess, "run", fake_run)
    result = gate.mypy_against_head_many("py", [(f, None) for f in files], tmp_path)
    assert len(calls) == 1 and sum(a.endswith(".py") for a in calls[0]) == 9  # 6개 + HEAD 사본 3개
    for f in files:
        new, why = result[f]
        assert why == ""
        expected = [f"[mypy] {f.name}: only {f.name}  [misc]"]
        if f.name not in with_base:
            expected = [f"[mypy] {f.name}: only {f.name}  [misc]", f"[mypy] {f.name}: shared  [misc]"]
        assert new == expected
    assert not list(tmp_path.glob("_mypy_base_*"))


def test_batch_falls_back_to_per_file_on_mypy_internal_error(tmp_path, monkeypatch):
    """일괄 mypy 가 자체 오류(종료코드 2)면 파일별 실행으로 되돌아간다 — 한 파일 때문에 나머지가 '오류 없음'이 되지 않게."""
    files = [tmp_path / f"m{i}.py" for i in range(3)]
    calls = []

    def fake_run(cmd, *_a, **_k):
        calls.append(cmd)
        targets = [a for a in cmd if a.endswith(".py")]
        if len(targets) > 1:
            return _Proc(2, b"m1.py:1: error: invalid syntax  [syntax]")
        if targets[0].endswith("m1.py"):
            return _Proc(2, b"m1.py:1: error: invalid syntax  [syntax]")
        return _Proc(1, f"{targets[0]}:1: error: bad  [misc]".encode())

    monkeypatch.setattr(gate.subprocess, "run", fake_run)
    keys = gate.mypy_keys_batch("py", files, tmp_path)
    assert keys == {files[0]: {"bad  [misc]"}, files[1]: None, files[2]: {"bad  [misc]"}}
    assert len(calls) == 2 + 4  # 일괄 2회(재시도) + 파일별(m1 은 재시도 포함 2회)


def test_batch_reports_not_run_when_mypy_missing_or_times_out(tmp_path, monkeypatch):
    """mypy 미설치·시간 초과는 '오류 없음'(통과)이 아니라 '실행하지 못했습니다'."""
    files = [tmp_path / "a.py", tmp_path / "b.py"]
    monkeypatch.setattr(gate.subprocess, "run", lambda *_a, **_k: _Proc(1, b"", b"python.exe: No module named mypy"))
    assert gate.mypy_keys_batch("py", files, tmp_path) == {files[0]: None, files[1]: None}

    def timeout(*_a, **_k):
        raise subprocess.TimeoutExpired("mypy", 1)

    monkeypatch.setattr(gate.subprocess, "run", timeout)
    monkeypatch.setattr(gate, "_head_blobs", lambda _root, rels: dict.fromkeys(rels))
    out = gate.mypy_against_head_many("py", [(f, None) for f in files], tmp_path)
    assert out == {f: ([], "mypy 를 실행하지 못했습니다") for f in files}

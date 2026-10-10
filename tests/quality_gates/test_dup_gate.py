"""G12 중복 게이트(tools/repo_gates/dup_gate.py) 시험 — 임시 git 저장소에서 격리 검증."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DUP_GATE = ROOT / "tools" / "repo_gates" / "dup_gate.py"

_COPY_PASTE_FUNC = """
def {name}(limit):
    if not limit:
        return []
    total = 0
    for i in range(limit):
        total += i
    return total
"""

_UNIQUE_FUNC = """
def {name}(x, y):
    acc = x
    acc += y
    acc *= 2
    return acc - 1
"""


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """dup_gate.py를 격리된 임시 git 저장소에 복사해 실행 — 실제 저장소 상태에 의존하지 않는다."""
    (tmp_path / "tools" / "repo_gates").mkdir(parents=True)
    (tmp_path / "configs").mkdir()
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")  # 저장소 루트 표식 — 게이트가 pyproject.toml 이 있는 상위 폴더를 루트로 찾는다
    (tmp_path / "tools" / "repo_gates" / "dup_gate.py").write_bytes(DUP_GATE.read_bytes())
    (tmp_path / "tools" / "repo_gates" / "_dup_structure_hash.py").write_bytes(
        (ROOT / "tools" / "repo_gates" / "_dup_structure_hash.py").read_bytes()
    )
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.local"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    return tmp_path


def _write(repo_path: Path, rel: str, content: str) -> None:
    p = repo_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _run_gate(repo_path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "tools/repo_gates/dup_gate.py", *args],
        cwd=repo_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _git_add_all(repo_path: Path) -> None:
    subprocess.run(["git", "add", "-A"], cwd=repo_path, check=True)


def test_build_baseline_captures_existing_duplicate(repo):
    _write(repo, "pkg_a/one.py", _COPY_PASTE_FUNC.format(name="legacy_a"))
    _write(repo, "pkg_b/two.py", _COPY_PASTE_FUNC.format(name="legacy_b"))
    _git_add_all(repo)

    result = _run_gate(repo, "build-baseline")
    assert result.returncode == 0, result.stdout + result.stderr

    baseline = json.loads((repo / "configs" / "dup_baseline.json").read_text(encoding="utf-8"))
    assert baseline["hash_count"] >= 1


def test_existing_duplicate_passes_check(repo):
    _write(repo, "pkg_a/one.py", _COPY_PASTE_FUNC.format(name="legacy_a"))
    _write(repo, "pkg_b/two.py", _COPY_PASTE_FUNC.format(name="legacy_b"))
    _git_add_all(repo)
    _run_gate(repo, "build-baseline")

    result = _run_gate(repo, "check", "pkg_a/one.py", "pkg_b/two.py")
    assert result.returncode == 0, result.stdout + result.stderr


def test_new_copy_is_blocked(repo):
    _write(repo, "pkg_a/one.py", _UNIQUE_FUNC.format(name="only_copy"))
    _git_add_all(repo)
    _run_gate(repo, "build-baseline")  # 기준선엔 중복이 하나도 없음(1곳뿐)

    _write(repo, "pkg_b/two.py", _UNIQUE_FUNC.format(name="only_copy_dup"))
    result = _run_gate(repo, "check", "pkg_b/two.py")
    assert result.returncode == 1, result.stdout
    assert "구조 동일 중복" in result.stdout


def test_files_from_reads_target_list_from_file(repo, tmp_path):
    """PR #165(변경 2567개, 'Argument list too long') 대응 — 명령줄 인자 대신 파일로 대상 목록을 받는다."""
    _write(repo, "pkg_a/one.py", _UNIQUE_FUNC.format(name="only_copy"))
    _git_add_all(repo)
    _run_gate(repo, "build-baseline")  # 기준선엔 중복이 하나도 없음(1곳뿐)

    _write(repo, "pkg_b/two.py", _UNIQUE_FUNC.format(name="only_copy_dup"))
    list_file = tmp_path / "changed.txt"
    list_file.write_text("pkg_b/two.py\n", encoding="utf-8")

    result = _run_gate(repo, "check", "--files-from", str(list_file))
    assert result.returncode == 1, result.stdout
    assert "구조 동일 중복" in result.stdout


def test_files_from_dash_reads_target_list_from_stdin(repo):
    """`--files-from -` 는 표준입력에서 목록을 읽는다(ci.yml 과 달리 파일 없이도 쓸 수 있는지 확인)."""
    _write(repo, "pkg_a/one.py", _UNIQUE_FUNC.format(name="only_copy"))
    _git_add_all(repo)
    _run_gate(repo, "build-baseline")
    _write(repo, "pkg_b/two.py", _UNIQUE_FUNC.format(name="only_copy_dup"))

    result = subprocess.run(
        [sys.executable, "tools/repo_gates/dup_gate.py", "check", "--files-from", "-"],
        cwd=repo, input="pkg_b/two.py\n", capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 1, result.stdout
    assert "구조 동일 중복" in result.stdout


def test_exempt_test_dir_passes_even_when_duplicated(repo):
    _write(repo, "pkg_a/one.py", _UNIQUE_FUNC.format(name="risky"))
    _git_add_all(repo)
    _run_gate(repo, "build-baseline")

    _write(repo, "tests/test_something.py", _UNIQUE_FUNC.format(name="risky_copy"))
    result = _run_gate(repo, "check", "tests/test_something.py")
    assert result.returncode == 0, result.stdout


def test_exempt_scripts_archive_passes_even_when_duplicated(repo):
    _write(repo, "pkg_a/one.py", _UNIQUE_FUNC.format(name="risky2"))
    _git_add_all(repo)
    _run_gate(repo, "build-baseline")

    _write(repo, "scripts/archive/old_copy.py", _UNIQUE_FUNC.format(name="risky2_copy"))
    result = _run_gate(repo, "check", "scripts/archive/old_copy.py")
    assert result.returncode == 0, result.stdout


def test_exempt_apps_dir_passes_even_when_duplicated(repo):
    _write(repo, "pkg_a/one.py", _UNIQUE_FUNC.format(name="risky3"))
    _git_add_all(repo)
    _run_gate(repo, "build-baseline")

    _write(repo, "apps/standalone/copy.py", _UNIQUE_FUNC.format(name="risky3_copy"))
    result = _run_gate(repo, "check", "apps/standalone/copy.py")
    assert result.returncode == 0, result.stdout


def test_short_function_below_min_statements_not_flagged(repo):
    _write(repo, "pkg_a/one.py", "def tiny():\n    return 1\n")
    _git_add_all(repo)
    _run_gate(repo, "build-baseline")

    _write(repo, "pkg_b/two.py", "def tiny_copy():\n    return 1\n")
    result = _run_gate(repo, "check", "pkg_b/two.py")
    assert result.returncode == 0, result.stdout


def test_staged_mode_only_checks_staged_files(repo):
    _write(repo, "pkg_a/one.py", _UNIQUE_FUNC.format(name="staged_target"))
    _git_add_all(repo)
    _run_gate(repo, "build-baseline")

    _write(repo, "pkg_b/two.py", _UNIQUE_FUNC.format(name="staged_target_dup"))
    # 아직 git add 하지 않음 — --staged 는 아무 것도 못 찾아야 함
    result = _run_gate(repo, "check", "--staged")
    assert result.returncode == 0, result.stdout

    _git_add_all(repo)
    result2 = _run_gate(repo, "check", "--staged")
    assert result2.returncode == 1, result2.stdout


# ── check --all: 저장소 전체 비교(2026-10-07 기준선 감사 — staged·변경 파일 검사는 새 중복이 샘) ─────────────


def test_check_all_passes_when_every_duplicate_group_is_in_the_baseline(repo):
    _write(repo, "pkg_a/one.py", _COPY_PASTE_FUNC.format(name="legacy_a"))
    _write(repo, "pkg_b/two.py", _COPY_PASTE_FUNC.format(name="legacy_b"))
    _git_add_all(repo)
    _run_gate(repo, "build-baseline")
    result = _run_gate(repo, "check", "--all")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout


def test_check_all_fails_on_a_new_group_even_when_the_files_are_not_staged_or_listed(repo):
    """변경 파일 목록에 없는 두 파일 사이의 새 중복도 전체 비교는 잡는다."""
    _write(repo, "pkg_a/one.py", _UNIQUE_FUNC.format(name="only_copy"))
    _git_add_all(repo)
    _run_gate(repo, "build-baseline")  # 기준선에는 중복이 없다
    _write(repo, "pkg_b/two.py", _UNIQUE_FUNC.format(name="second_copy"))
    _git_add_all(repo)
    result = _run_gate(repo, "check", "--all")
    assert result.returncode == 1
    assert "새 중복 묶음" in result.stdout and "pkg_b/two.py" in result.stdout


def test_check_all_reports_vanished_baseline_hashes_but_still_passes(repo):
    _write(repo, "pkg_a/one.py", _COPY_PASTE_FUNC.format(name="legacy_a"))
    _write(repo, "pkg_b/two.py", _COPY_PASTE_FUNC.format(name="legacy_b"))
    _git_add_all(repo)
    _run_gate(repo, "build-baseline")
    (repo / "pkg_b" / "two.py").unlink()
    _git_add_all(repo)
    result = _run_gate(repo, "check", "--all")
    assert result.returncode == 0
    assert "기준선에만 남은" in result.stderr


def test_check_all_ignores_exempt_folders(repo):
    _write(repo, "pkg_a/one.py", _UNIQUE_FUNC.format(name="only_copy"))
    _write(repo, "scripts/archive/old.py", _UNIQUE_FUNC.format(name="archived_copy"))
    _git_add_all(repo)
    _run_gate(repo, "build-baseline")
    assert _run_gate(repo, "check", "--all").returncode == 0


def test_no_warning_on_matching_python_version(capsys, monkeypatch):
    sys.path.insert(0, str(ROOT))
    from tools.repo_gates import dup_gate as gate

    monkeypatch.setattr(gate.sys, "version_info", (3, 14, 7, "final", 0))
    gate._warn_if_wrong_python_version()
    assert "경고" not in capsys.readouterr().err


def test_warning_fires_for_other_python_version(capsys, monkeypatch):
    sys.path.insert(0, str(ROOT))
    from tools.repo_gates import dup_gate as gate

    monkeypatch.setattr(gate.sys, "version_info", (3, 12, 10, "final", 0))
    gate._warn_if_wrong_python_version()
    assert "경고" in capsys.readouterr().err

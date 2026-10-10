"""audit_kit_gate — git mv(이름 변경) 파일은 옛 위치의 기존 mypy 오류를 신규로 잡지 않는다.

배경(2026-10-07): '편집 전 대비 새 오류만' 비교가 HEAD:<같은 경로> 를 기준으로 삼아서, 이동한 파일은 HEAD 에 없는 새 파일로 보여 옛 위치의
기존 오류가 전부 신규로 잡혔다(W2 S1 커밋에서 오탐 3건). staged 목록을 `-M --name-status` 로 읽어 R 이면 HEAD:<옛 경로> 를 기준으로 쓴다.
mypy 는 이 시험을 도는 파이썬(sys.executable)의 것을 쓴다.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from tools.hooks import audit_kit_gate as gate

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
    monkeypatch.setattr(
        gate, "_head_blobs", lambda _root, rels: {r: (b"x = 0\n" if r in with_base else None) for r in rels}
    )
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


def _write_marker_kit(path: Path) -> None:
    """가짜 audit-kit: stdin 의 file_path 내용에 들어 있는 마커 줄마다 `[STD-99] <줄>` 를 찍고 exit 2(없으면 exit 0)."""
    path.write_text(
        "import json, sys\n"
        "data = json.loads(sys.stdin.read())\n"
        "text = open(data['tool_input']['file_path'], encoding='utf-8').read()\n"
        "markers = [ln for ln in text.splitlines() if ln.startswith('MARKER_')]\n"
        "for m in markers:\n"
        "    print(f'[STD-99] {m}', file=sys.stderr)\n"
        "sys.exit(2 if markers else 0)\n",
        encoding="utf-8",
    )


def _write_path_echoing_kit(path: Path) -> None:
    """가짜 audit-kit: 실제 audit-kit 처럼 지적 문구에 검사 대상의 상대경로를 그대로 박아 넣는다(`_hook_base_<이름>` 사본과
    원본의 파일명이 달라 글자 비교가 틀어지는 실제 버그를 재현)."""
    path.write_text(
        "import json, sys\n"
        "from pathlib import Path\n"
        "data = json.loads(sys.stdin.read())\n"
        "fp = Path(data['tool_input']['file_path'])\n"
        "text = fp.read_text(encoding='utf-8')\n"
        "markers = [ln for ln in text.splitlines() if ln.startswith('MARKER_')]\n"
        "rel = fp.relative_to(Path(data['cwd']))\n"
        "for m in markers:\n"
        "    print(f'[표준 STD-02] {rel.as_posix()}:25 {m}', file=sys.stderr)\n"
        "sys.exit(2 if markers else 0)\n",
        encoding="utf-8",
    )


def test_hook_rename_ignores_temp_copy_filename_in_finding_text(repo, tmp_path):
    """회귀 방지(2026-10-08 실사례): HEAD 사본 파일명(`_hook_base_X.py`)이 지적 문구 안의 경로에 그대로 찍혀도
    태그+메시지만 비교해 같은 지적로 인식한다(실제 audit-kit STD-02 형식 재현)."""
    (repo / "old" / "mod.py").write_text(
        (repo / "old" / "mod.py").read_text(encoding="utf-8") + "MARKER_A = 1\n", encoding="utf-8"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add marker")
    (repo / "new").mkdir()
    _git(repo, "mv", "old/mod.py", "new/mod.py")
    path = repo / "new" / "mod.py"
    kit_py = tmp_path / "path_echo_kit.py"
    _write_path_echoing_kit(kit_py)
    kit = [sys.executable, str(kit_py)]
    assert gate._kit_hook_against_head(kit, path, repo, "old/mod.py") == ([], "")


def test_hook_rename_without_change_has_no_new_findings(repo, tmp_path):
    """STD 류(hook) 체크도 git mv 로만 옮긴 파일은 옛 위치의 기존 지적을 신규로 안 잡는다(2026-10-08, tests 이동 커밋 오탐 발견)."""
    (repo / "old" / "mod.py").write_text(
        (repo / "old" / "mod.py").read_text(encoding="utf-8") + "MARKER_A = 1\n", encoding="utf-8"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add marker")
    (repo / "new").mkdir()
    _git(repo, "mv", "old/mod.py", "new/mod.py")
    path = repo / "new" / "mod.py"
    kit_py = tmp_path / "marker_kit.py"
    _write_marker_kit(kit_py)
    kit = [sys.executable, str(kit_py)]
    assert gate._kit_hook_against_head(kit, path, repo, "old/mod.py") == ([], "")


def test_hook_rename_without_old_rel_is_misreported_as_new(repo, tmp_path):
    """회귀 방지: old_rel 을 안 주면(예전 동작) 옮기기만 한 파일도 기존 지적이 전부 신규로 잡힌다."""
    (repo / "old" / "mod.py").write_text(
        (repo / "old" / "mod.py").read_text(encoding="utf-8") + "MARKER_A = 1\n", encoding="utf-8"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add marker")
    (repo / "new").mkdir()
    _git(repo, "mv", "old/mod.py", "new/mod.py")
    path = repo / "new" / "mod.py"
    kit_py = tmp_path / "marker_kit.py"
    _write_marker_kit(kit_py)
    kit = [sys.executable, str(kit_py)]
    findings, why = gate._kit_hook_against_head(kit, path, repo, None)
    assert why == "" and len(findings) == 1 and "MARKER_A" in findings[0]


def test_hook_rename_with_new_marker_reports_only_the_new_one(repo, tmp_path):
    """이동 + 새 지적 1개 = 신규 1(기존 마커는 제외)."""
    (repo / "old" / "mod.py").write_text(
        (repo / "old" / "mod.py").read_text(encoding="utf-8") + "MARKER_A = 1\n", encoding="utf-8"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add marker")
    (repo / "new").mkdir()
    _git(repo, "mv", "old/mod.py", "new/mod.py")
    path = repo / "new" / "mod.py"
    path.write_text(path.read_text(encoding="utf-8") + "MARKER_B = 2\n", encoding="utf-8")
    kit_py = tmp_path / "marker_kit.py"
    _write_marker_kit(kit_py)
    kit = [sys.executable, str(kit_py)]
    findings, why = gate._kit_hook_against_head(kit, path, repo, "old/mod.py")
    assert why == "" and len(findings) == 1 and "MARKER_B" in findings[0]


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


# ── audit-kit hook 자체의 "(기존)" 판정이 놓치는 이동 파일의 옛 결함(F8, 2026-10-08) ──────────


_CONTENT_AWARE_KIT = textwrap.dedent(
    """
    import json, pathlib, sys
    payload = json.loads(sys.stdin.read())
    fp = pathlib.Path(payload["tool_input"]["file_path"])
    cwd = pathlib.Path(payload["cwd"])
    text = fp.read_text(encoding="utf-8")
    rel = fp.relative_to(cwd).as_posix()
    findings = []
    if "BAD_PATH_MARKER" in text:
        # 실측 형식 재현: 메시지 안에 상대경로(파일명 포함)가 다시 나온다(F8-2 재발 원인).
        findings.append(f"[표준 STD-02] {rel}:14 절대경로 하드코딩: 'C:/Windows/'")
    if "BAD_NEW_MARKER" in text:
        findings.append(f"[표준 STD-03] {rel}:20 새 문제")
    if findings:
        sys.stderr.write("\\n".join(findings) + "\\n")
        sys.exit(2)
    sys.exit(0)
    """
)


def _content_aware_kit(tmp_path: Path) -> list[str]:
    fake = tmp_path / "fake_kit_content.py"
    fake.write_text(_CONTENT_AWARE_KIT, encoding="utf-8")
    return [sys.executable, str(fake)]


def test_renamed_file_with_old_defect_reports_zero_new_findings(repo, monkeypatch):
    """F8: 이동 전부터 있던 결함(BAD_PATH_MARKER)은 audit-kit 자신의 '(기존)' 판정 없이도 신규로 잡히지 않는다."""
    monkeypatch.setattr(gate, "mypy_python", lambda _kit: None)  # mypy 비교는 이 시험 범위 밖
    (repo / "old" / "mod.py").write_text("BAD_PATH_MARKER = 1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add marker")
    (repo / "new").mkdir()
    _git(repo, "mv", "old/mod.py", "new/mod.py")
    path = repo / "new" / "mod.py"
    kit = _content_aware_kit(repo)

    findings, why = gate.check_file(kit, path, repo, old_rel="old/mod.py")
    assert why == ""
    assert findings == []


def test_renamed_file_without_old_rel_misreports_old_defect_as_new(repo, monkeypatch):
    """회귀 방지: old_rel 을 안 넘기면(예전 동작) 이동 전부터 있던 결함이 신규로 잡힌다."""
    monkeypatch.setattr(gate, "mypy_python", lambda _kit: None)
    (repo / "old" / "mod.py").write_text("BAD_PATH_MARKER = 1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add marker")
    (repo / "new").mkdir()
    _git(repo, "mv", "old/mod.py", "new/mod.py")
    path = repo / "new" / "mod.py"
    kit = _content_aware_kit(repo)

    findings, why = gate.check_file(kit, path, repo)
    assert why == ""
    assert len(findings) == 1 and "STD-02" in findings[0]


def test_renamed_file_with_old_and_new_defect_reports_only_new(repo, monkeypatch):
    """이동 + 새 결함 추가 = 옛 결함은 빠지고 새 결함만 신규로 잡힌다."""
    monkeypatch.setattr(gate, "mypy_python", lambda _kit: None)
    (repo / "old" / "mod.py").write_text("BAD_PATH_MARKER = 1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add marker")
    (repo / "new").mkdir()
    _git(repo, "mv", "old/mod.py", "new/mod.py")
    path = repo / "new" / "mod.py"
    path.write_text(path.read_text(encoding="utf-8") + "BAD_NEW_MARKER = 1\n", encoding="utf-8")
    kit = _content_aware_kit(repo)

    findings, why = gate.check_file(kit, path, repo, old_rel="old/mod.py")
    assert why == ""
    assert len(findings) == 1 and "STD-03" in findings[0]


def test_renamed_file_check_files_batched_drops_old_defect_too(repo, monkeypatch):
    """check_files(커밋 단계 일괄 실행) 에서도 같은 결과 — _kit_hook_against_head 가 old_rel 을 내부에서 처리한다."""
    monkeypatch.setattr(gate, "mypy_python", lambda _kit: None)
    (repo / "old" / "mod.py").write_text("BAD_PATH_MARKER = 1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add marker")
    (repo / "new").mkdir()
    _git(repo, "mv", "old/mod.py", "new/mod.py")
    path = repo / "new" / "mod.py"
    _git(repo, "add", "-A")
    kit = _content_aware_kit(repo)

    items = [(path, "old/mod.py")]
    batched = gate.check_files(kit, items, repo)
    assert batched == [(path, [], "")]
    assert not list(repo.rglob("_hook_base_*"))  # 비교용 사본은 남기지 않는다

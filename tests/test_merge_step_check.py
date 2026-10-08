"""merge_step_check — 합본 단계 점검 표·판정·종료코드(측정·게이트 실행은 대체 객체로, 이동 감지는 임시 git 저장소로)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.ops.devflow import merge_step_check as msc


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(root), capture_output=True, text=True, encoding="utf-8", errors="replace", check=True
    ).stdout


def test_as_count_handles_dict_list_int_and_none():
    assert msc._as_count({"total": 3, "by_pair": {}}) == 3
    assert msc._as_count({"a": 1, "b": 2}) == 2  # total 없는 dict 는 항목 수
    assert msc._as_count([1, 2, 3, 4]) == 4
    assert msc._as_count(7) == 7
    assert msc._as_count(None) == 0


def test_verdict_and_table_show_signed_delta():
    assert (msc._verdict(5, 6), msc._verdict(5, 5), msc._verdict(5, 4)) == ("증가", "동일", "개선")
    assert msc._verdict(None, 84) == "신규"  # 기준 브랜치에 없던 기준선 파일은 증가로 보지 않는다
    assert "-" in msc._table([("G15", None, 176, "신규")])
    table = msc._table([("순환", 38, 37, "개선"), ("층 역전", 0, 2, "증가")])
    assert "-1" in table and "+2" in table and "증가" in table and "개선" in table


def test_baseline_sizes_reads_count_keys_and_missing_file_is_none(tmp_path):
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "tool_home_baseline.json").write_text(json.dumps({"count": 84}), encoding="utf-8")
    (tmp_path / "configs" / "dup_baseline.json").write_text(json.dumps({"hash_count": 81}), encoding="utf-8")
    got = msc.baseline_sizes(tmp_path)
    assert got["G11 tool_home 기준선"] == 84 and got["G12 dup 기준선"] == 81
    assert got["G15 flat_root 기준선"] is None and got["G16 folder 등록 수"] is None  # 파일 없음 = 새 게이트


@pytest.fixture()
def repo(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "a").mkdir()
    body = "".join(f"def f{i}():\n    return {i}\n\n" for i in range(30))
    (tmp_path / "a" / "mod.py").write_text(body, encoding="utf-8")
    (tmp_path / "a" / "keep.py").write_text("x = 1\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "base")
    _git(tmp_path, "branch", "base")
    _git(tmp_path, "checkout", "-q", "-b", "work")
    (tmp_path / "b").mkdir()
    _git(tmp_path, "mv", "a/mod.py", "b/mod.py")
    (tmp_path / "docs.md").write_text("a/keep.py\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "move")
    return tmp_path


def test_moved_py_lists_only_renamed_python_files(repo):
    assert msc.moved_py("base", "work", repo) == {"a/mod.py": "b/mod.py"}


def _fake_measure(cycles_before, cycles_after, gates_ok=True, blocking=()):
    calls = {"n": 0}

    def measure(tree, runcheck):
        calls["n"] += 1
        c = cycles_before if calls["n"] == 2 else cycles_after  # head 를 먼저 재고 base 를 나중에 잰다
        return {"순환(실제 import)": c, "층 역전": 0, "금지 import": 0, "LIVE import 실패": 0}

    return measure, gates_ok, list(blocking)


def _run_main(monkeypatch, capsys, *, before, after, gates_ok=True, blocking=(), extra=()):
    measure, ok, block = _fake_measure(before, after, gates_ok, blocking)
    monkeypatch.setattr(msc, "measure_tree", measure)
    monkeypatch.setattr(msc, "baseline_sizes", lambda tree: {"G11 tool_home 기준선": 84, "G15 flat_root 기준선": 176})
    monkeypatch.setattr(msc, "gate_results", lambda tree: {"registry_sync": ok, "G11 tool_home": ok})
    monkeypatch.setattr(msc, "_run", lambda cmd, cwd, timeout=0: subprocess.CompletedProcess(cmd, 0, "", ""))
    monkeypatch.setattr(msc, "preflight_blocking", lambda base, head, root: block)
    monkeypatch.setattr(msc, "moved_py", lambda base, head, root: {})
    monkeypatch.setattr("scripts.ops.verify_change._checkout", lambda ref, dest: True)
    monkeypatch.setattr(msc, "_git", lambda cwd, *args: subprocess.CompletedProcess(args, 0, "", ""))
    rc = msc.main(["--base", "origin/master", "--no-runcheck", *extra])
    return rc, capsys.readouterr().out


def test_main_passes_when_nothing_increases(monkeypatch, capsys):
    rc, out = _run_main(monkeypatch, capsys, before=38, after=37)
    assert rc == 0 and "결과: 통과" in out and "-1" in out


def test_main_fails_when_cycles_increase(monkeypatch, capsys):
    rc, out = _run_main(monkeypatch, capsys, before=37, after=38)
    assert rc == 1 and "결과: 실패" in out and "순환(실제 import)" in out


def test_main_fails_when_a_gate_fails_or_preflight_blocks(monkeypatch, capsys):
    rc, out = _run_main(monkeypatch, capsys, before=37, after=37, gates_ok=False)
    assert rc == 1 and "실패" in out
    rc, out = _run_main(monkeypatch, capsys, before=37, after=37, blocking=["a/mod.py: 1건 (path_string x.py:3)"])
    assert rc == 1 and "move_preflight 막음 1건" in out

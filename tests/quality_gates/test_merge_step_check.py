"""merge_step_check — 합본 단계 점검 표·판정·종료코드(측정·게이트 실행은 대체 객체로, 이동 감지는 임시 git 저장소로)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tools.devflow import merge_step_check as msc


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
    monkeypatch.setattr("tools.verify_change._checkout", lambda ref, dest: True)
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


# ── 영향 시험 실행 옵션(--impacted-tests) ─────────────────────────────────────


def test_plan_impacted_never_turns_an_empty_list_into_a_full_run():
    assert msc.plan_impacted([]) == "empty"
    assert msc.plan_impacted(["tests/test_a.py"]) == "run"
    assert msc.plan_impacted([f"tests/test_{i}.py" for i in range(msc.IMPACTED_MAX_FILES)]) == "run"
    assert msc.plan_impacted([f"tests/test_{i}.py" for i in range(msc.IMPACTED_MAX_FILES + 1)]) == "list_only"
    assert msc.plan_impacted(["a", "b", "c"], max_files=2) == "list_only"


def test_split_failures_marks_only_base_failures_as_existing():
    new, existing = msc.split_failures(["t/a.py::x", "t/b.py::y", "t/new.py::z"], {"t/a.py::x"})
    assert new == ["t/b.py::y", "t/new.py::z"] and existing == ["t/a.py::x"]


def test_impacted_section_skips_run_when_empty_or_too_many(monkeypatch, tmp_path):
    ran: list = []
    monkeypatch.setattr(msc, "run_impacted", lambda tree, files, workers: ran.append(files) or [])
    monkeypatch.setattr(msc, "impacted_test_files", lambda base, head, root: [])
    assert msc.impacted_section("b", tmp_path, 1, 400)["status"] == "empty"
    monkeypatch.setattr(msc, "impacted_test_files", lambda base, head, root: [f"tests/test_{i}.py" for i in range(5)])
    result = msc.impacted_section("b", tmp_path, 1, 3)
    assert result["status"] == "list_only" and len(result["files"]) == 5
    assert ran == []  # 비었거나 상한 초과면 pytest 를 부르지 않는다


def test_impacted_section_separates_new_and_existing_failures(monkeypatch, tmp_path):
    base_tree = tmp_path / "base"
    (base_tree / "tests").mkdir(parents=True)
    (base_tree / "tests" / "test_old.py").write_text("", encoding="utf-8")  # 기준에도 있는 시험 파일 (test_new.py 는 없음)
    calls: list[tuple[Path, list[str]]] = []

    def fake_run(tree, files, workers):
        calls.append((tree, list(files)))
        return ["tests/test_old.py::t1", "tests/test_new.py::t2"] if tree == msc.ROOT else ["tests/test_old.py::t1"]

    monkeypatch.setattr(msc, "run_impacted", fake_run)
    monkeypatch.setattr(msc, "impacted_test_files", lambda base, head, root: ["tests/test_old.py", "tests/test_new.py"])
    result = msc.impacted_section("b", base_tree, 2, 400)
    assert result["status"] == "run"
    assert result["existing_failures"] == ["tests/test_old.py::t1"]  # 기준에서도 실패 → 판정 제외
    assert result["new_failures"] == ["tests/test_new.py::t2"]  # 기준에 없는 시험 파일의 실패는 새 실패
    assert calls[1] == (base_tree, ["tests/test_old.py"])  # 기준에서는 head 에서 실패한 파일 중 기준에 있는 것만 다시 돈다


def test_impacted_section_adds_slot_notice_at_100_files(monkeypatch, tmp_path):
    monkeypatch.setattr(msc, "run_impacted", lambda tree, files, workers: [])
    monkeypatch.setattr(msc, "impacted_test_files", lambda base, head, root: [f"tests/test_{i}.py" for i in range(msc.IMPACTED_SLOT_NOTICE)])
    assert "HEAVY_SLOT" in msc.impacted_section("b", tmp_path, 1, 400)["notice"]


def test_run_impacted_caps_workers_at_four(monkeypatch, tmp_path):
    seen: list[list[str]] = []

    def fake_run(cmd, tree, timeout=0):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("tools.verify_change.run", fake_run)
    monkeypatch.setattr(msc, "_xdist_available", lambda: True)
    assert msc.run_impacted(tmp_path, ["tests/test_a.py"], 99) == []
    assert seen[0][seen[0].index("-n") + 1] == "4"
    seen.clear()
    msc.run_impacted(tmp_path, ["tests/test_a.py"], 1)
    assert "-n" not in seen[0]


def test_main_fails_on_new_impacted_failure_but_not_on_existing_ones(monkeypatch, capsys):
    measure, _ok, _block = _fake_measure(37, 37)
    monkeypatch.setattr(msc, "measure_tree", measure)
    monkeypatch.setattr(msc, "baseline_sizes", lambda tree: {"G11 tool_home 기준선": 84})
    monkeypatch.setattr(msc, "gate_results", lambda tree: {"registry_sync": True})
    monkeypatch.setattr(msc, "_run", lambda cmd, cwd, timeout=0: subprocess.CompletedProcess(cmd, 0, "", ""))
    monkeypatch.setattr(msc, "preflight_blocking", lambda base, head, root: [])
    monkeypatch.setattr(msc, "moved_py", lambda base, head, root: {})
    monkeypatch.setattr("tools.verify_change._checkout", lambda ref, dest: True)
    monkeypatch.setattr(msc, "_git", lambda cwd, *args: subprocess.CompletedProcess(args, 0, "", ""))
    section = {"status": "run", "files": ["tests/test_a.py"], "new_failures": [], "existing_failures": ["tests/test_a.py::old"], "notice": ""}
    monkeypatch.setattr(msc, "impacted_section", lambda base, base_tree, workers, max_files: section)
    assert msc.main(["--no-runcheck", "--impacted-tests"]) == 0
    assert "기존 실패" in capsys.readouterr().out
    section["new_failures"] = ["tests/test_a.py::broken"]
    assert msc.main(["--no-runcheck", "--impacted-tests"]) == 1
    assert "영향 시험 새 실패 1건" in capsys.readouterr().out


# ── 영향 시험 선별은 verify_change.affected_tests(= ref_seeds 출발점 포함) 와 같은 함수를 쓴다 ──────


def test_impacted_test_files_uses_the_shared_selection(monkeypatch, tmp_path):
    from tools import verify_change as vc

    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("x = 1", encoding="utf-8")
    seen: list[list[str]] = []
    monkeypatch.setattr(vc, "changed_files", lambda base, head: ["configs/folder_registry.json"])
    monkeypatch.setattr(vc, "affected_tests", lambda changed: seen.append(list(changed)) or ["tests/test_a.py", "tests/test_gone.py"])
    assert msc.impacted_test_files("b", "HEAD", tmp_path) == ["tests/test_a.py"]  # 현재 트리에 없는 시험은 뺀다
    assert seen == [["configs/folder_registry.json"]]  # .py 가 하나도 없어도 비-.py 변경이 선별 함수에 그대로 전달된다


def test_no_changes_means_no_tests(monkeypatch, tmp_path):
    from tools import verify_change as vc

    monkeypatch.setattr(vc, "changed_files", lambda base, head: [])
    monkeypatch.setattr(vc, "affected_tests", lambda changed: (_ for _ in ()).throw(AssertionError("변경이 없으면 부르지 않는다")))
    assert msc.impacted_test_files("b", "HEAD", tmp_path) == []

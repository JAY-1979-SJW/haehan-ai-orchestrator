"""verify_change --phase — CI 가 verify 를 job 여러 개로 나눠 병렬로 돌릴 때(static · tests 묶음 N개 · report) 합쳐서 같은 판정이 나오는지 고정한다."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from scripts.ops import verify_change as vc


def test_shard_slices_partition_the_list_without_loss_or_overlap():
    tests = [f"tests/test_{i:02d}.py" for i in range(10)]
    parts = [vc.shard_slice(tests, i, 3) for i in (1, 2, 3)]
    assert sorted(x for part in parts for x in part) == tests
    assert len({x for part in parts for x in part}) == len(tests)
    assert [len(p) for p in parts] == [4, 3, 3]  # 라운드 로빈 — 한쪽에 몰리지 않는다


def test_parse_shard_and_bad_values():
    assert vc._parse_shard(None) == (1, 1) and vc._parse_shard("2/3") == (2, 3)
    for bad in ("0/3", "4/3"):
        with pytest.raises(SystemExit):
            vc._parse_shard(bad)


def _static(tmp_path: Path, tests: list[str]) -> Path:
    base = {
        "collect_errors": [],
        "import_fail": [],
        "routes": "5",
        "violations": [],
        "skeleton": [],
        "cycles": [],
        "test_failures": [],
        "test_timeouts": [],
    }
    data = {
        "before": dict(base),
        "after": dict(base),
        "ruff_errors": [],
        "kit_errors": [],
        "loc_deps": [],
        "moved": {},
        "receiving": [],
        "changed": ["pkg/mod.py"],
        "tests": tests,
    }
    path = tmp_path / "static.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _shard(tmp_path: Path, index: int, count: int, before: list[str], after: list[str]) -> Path:
    data = {
        "shard": index,
        "count": count,
        "tests": [],
        "before": {"test_failures": before, "test_timeouts": []},
        "after": {"test_failures": after, "test_timeouts": []},
    }
    path = tmp_path / f"tests_{index}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _args(static: Path, shards: list[Path], out: Path | None = None) -> argparse.Namespace:
    return argparse.Namespace(
        static_json=str(static),
        test_json=[str(s) for s in shards],
        json=str(out) if out else None,
        expect_routes=None,
        base="b",
        head="h",
        phase="report",
        shard=None,
    )


def test_report_merges_shards_and_passes_when_failures_do_not_increase(tmp_path, capsys):
    tests = ["tests/test_a.py", "tests/test_b.py", "tests/test_c.py"]
    shards = [_shard(tmp_path, 1, 2, ["tests/test_a.py::x"], ["tests/test_a.py::x"]), _shard(tmp_path, 2, 2, [], [])]
    out = tmp_path / "result.json"
    assert vc._phase_report(_args(_static(tmp_path, tests), shards, out)) == 0
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["ok"] is True and saved["before"]["test_failures"] == ["tests/test_a.py::x"]


def test_report_fails_on_a_new_test_failure_in_any_shard(tmp_path, capsys):
    tests = ["tests/test_a.py", "tests/test_b.py"]
    shards = [_shard(tmp_path, 1, 2, [], []), _shard(tmp_path, 2, 2, [], ["tests/test_b.py::broken"])]
    assert vc._phase_report(_args(_static(tmp_path, tests), shards)) == 1
    assert "tests/test_b.py::broken" in capsys.readouterr().out


def test_report_fails_when_a_shard_result_is_missing(tmp_path, capsys):
    """묶음 결과가 하나 빠지면(job 실패·아티팩트 누락) 그 시험이 조용히 건너뛰어진 것이다 → 실패."""
    tests = ["tests/test_a.py", "tests/test_b.py"]
    assert vc._phase_report(_args(_static(tmp_path, tests), [_shard(tmp_path, 1, 2, [], [])])) == 1
    assert "모자란다" in capsys.readouterr().out


def test_report_with_no_affected_tests_needs_no_shards(tmp_path):
    assert vc._phase_report(_args(_static(tmp_path, []), [])) == 0


def test_phase_tests_runs_only_its_shard_on_both_trees(monkeypatch, tmp_path):
    """_measure_affected_test_results 는 3값(실패·시간초과·사유)을 돌려준다 — 2값으로 풀면
    ValueError(PR #165 서버 CI 결함, verify_change.py 701행)."""
    all_tests = [f"tests/test_{i}.py" for i in range(6)]
    ran: list[tuple[str, list[str]]] = []

    def fake_measure(tree, files):
        ran.append((tree.name, list(files)))
        if tree.name == "head" and files:
            return [f"{files[0]}::fail"], [], {f"{files[0]}::fail": "AssertionError: 기대값 불일치"}
        return [], [], {}

    monkeypatch.setattr(vc, "changed_files", lambda base, head: ["pkg/mod.py"])
    monkeypatch.setattr(vc, "run", lambda cmd, cwd, timeout=0: None)
    monkeypatch.setattr(vc, "affected_tests", lambda changed: all_tests)
    monkeypatch.setattr(vc, "_checkout", lambda ref, dest: dest.mkdir(parents=True, exist_ok=True) or True)
    monkeypatch.setattr(vc, "_cleanup_trees", lambda tmp, trees: None)
    monkeypatch.setattr(vc, "_measure_affected_test_results", fake_measure)
    out = tmp_path / "t2.json"
    args = argparse.Namespace(base="b", head="h", shard="2/3", json=str(out))
    assert vc._phase_tests(args) == 0
    mine = all_tests[1::3]
    assert sorted(ran) == [("base", mine), ("head", mine)]  # 이 묶음만, 두 트리에서
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["shard"] == 2 and saved["count"] == 3 and saved["tests"] == mine
    assert saved["after"]["test_failures"] == [f"{mine[0]}::fail"] and saved["before"]["test_failures"] == []
    assert saved["after"]["test_failure_reasons"] == {f"{mine[0]}::fail": "AssertionError: 기대값 불일치"}
    assert saved["before"]["test_failure_reasons"] == {}


def test_phase_report_merges_test_failure_reasons_across_shards(tmp_path):
    """새 시험: _phase_tests 가 shard JSON 에 넣은 test_failure_reasons 를 _phase_report 가 합쳐
    after_reasons(469행, 사유 표시)로 쓸 수 있게 되는지 — PR #165 수정 확인용."""
    tests = ["tests/test_a.py", "tests/test_b.py"]
    shard1 = {
        "shard": 1, "count": 2, "tests": [],
        "before": {"test_failures": [], "test_timeouts": [], "test_failure_reasons": {}},
        "after": {"test_failures": ["tests/test_a.py::x"], "test_timeouts": [],
                   "test_failure_reasons": {"tests/test_a.py::x": "TypeError: boom"}},
    }
    shard2 = {
        "shard": 2, "count": 2, "tests": [],
        "before": {"test_failures": [], "test_timeouts": [], "test_failure_reasons": {}},
        "after": {"test_failures": [], "test_timeouts": [], "test_failure_reasons": {}},
    }
    p1, p2 = tmp_path / "s1.json", tmp_path / "s2.json"
    p1.write_text(json.dumps(shard1), encoding="utf-8")
    p2.write_text(json.dumps(shard2), encoding="utf-8")
    out = tmp_path / "result.json"
    assert vc._phase_report(_args(_static(tmp_path, tests), [p1, p2], out)) == 1  # 새 실패 1건 — FAIL 이 맞다
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["after"]["test_failure_reasons"] == {"tests/test_a.py::x": "TypeError: boom"}

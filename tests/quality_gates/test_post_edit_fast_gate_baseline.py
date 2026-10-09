"""post_edit_fast_gate 기준선 비교 — HEAD 에서도 같은 문구로 실패하던 테스트는 차단하지 않는다."""

from __future__ import annotations

import pytest

from tools.hooks import post_edit_fast_gate as gate

OUTPUT = """
FAILED ai_orchestrator/tests/test_a.py::test_one - assert 404 == 200
FAILED ai_orchestrator/tests/test_a.py::test_two
ERROR ai_orchestrator/tests/test_b.py - ModuleNotFoundError: No module named 'keyring'
3 failed, 5 passed in 1.2s
"""


def test_parse_failures_reads_failed_and_error_lines():
    assert gate.parse_failures(OUTPUT) == {
        "ai_orchestrator/tests/test_a.py::test_one": "assert 404 == 200",
        "ai_orchestrator/tests/test_a.py::test_two": "",
        "ai_orchestrator/tests/test_b.py": "ModuleNotFoundError: No module named 'keyring'",
    }


def test_parse_failures_ignores_summary_and_noise():
    assert gate.parse_failures("3 passed in 0.1s\nsome FAILED text in a sentence\n") == {}


@pytest.mark.parametrize(
    ("current", "baseline", "expected"),
    [
        ({"t::a": "boom"}, {"t::a": "boom"}, []),  # 기존 실패 — 통과
        ({"t::a": "boom"}, {}, ["t::a"]),  # 기준선에서는 통과했는데 새로 실패
        ({"t::a": "new reason"}, {"t::a": "old reason"}, ["t::a"]),  # 같은 테스트라도 실패 문구가 바뀌면 새 문제
        ({"t::a": "x", "t::b": "y"}, {"t::a": "x"}, ["t::b"]),
        ({}, {"t::a": "x"}, []),
    ],
)
def test_new_failures(current, baseline, expected):
    assert gate.new_failures(current, baseline) == expected


def test_baseline_unavailable_keeps_blocking(monkeypatch):
    """기준선을 못 구하면 종전처럼 차단(fail-closed) — 실패를 조용히 삼키지 않는다."""
    fake = type("P", (), {"returncode": 1, "stdout": "FAILED t.py::a - boom\n", "stderr": ""})()
    monkeypatch.setattr(gate, "_run", lambda *a, **k: fake)
    monkeypatch.setattr(gate, "_baseline_failures", lambda _t: None)
    assert gate._impact_tests_gate(["t.py"], 0.0) == 2


def test_only_preexisting_failures_pass(monkeypatch):
    fake = type("P", (), {"returncode": 1, "stdout": "FAILED t.py::a - boom\n", "stderr": ""})()
    monkeypatch.setattr(gate, "_run", lambda *a, **k: fake)
    monkeypatch.setattr(gate, "_baseline_failures", lambda _t: {"t.py::a": "boom"})
    assert gate._impact_tests_gate(["t.py"], 0.0) == 0


def test_new_failure_blocks(monkeypatch):
    fake = type("P", (), {"returncode": 1, "stdout": "FAILED t.py::a - boom\nFAILED t.py::b - bang\n", "stderr": ""})()
    monkeypatch.setattr(gate, "_run", lambda *a, **k: fake)
    monkeypatch.setattr(gate, "_baseline_failures", lambda _t: {"t.py::a": "boom"})
    assert gate._impact_tests_gate(["t.py"], 0.0) == 2


def test_passing_tests_skip_baseline(monkeypatch):
    fake = type("P", (), {"returncode": 0, "stdout": "5 passed\n", "stderr": ""})()
    monkeypatch.setattr(gate, "_run", lambda *a, **k: fake)
    monkeypatch.setattr(gate, "_baseline_failures", lambda _t: pytest.fail("통과했는데 기준선을 돌렸다"))
    assert gate._impact_tests_gate(["t.py"], 0.0) == 0


def test_snapshot_skips_heavy_and_non_ascii_top_levels(monkeypatch):
    class Proc:
        stdout = b"ai_orchestrator\nadmin-web\ndocs\ndata\n" + "README_한글.txt\n".encode() + b"scripts\nCLAUDE.md\n"

    monkeypatch.setattr(gate.subprocess, "run", lambda *a, **k: Proc())
    assert gate._git_top_levels() == ["ai_orchestrator", "scripts", "CLAUDE.md"]

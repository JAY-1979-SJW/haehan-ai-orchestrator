"""verify_change — ruff 가 돌지 못하면 '0건'으로 조용히 통과하지 않고 실패로 드러낸다.

배경(2026-10-07): CI 러너에는 ruff 가 설치돼 있지 않았다(requirements·constraints 에 개발 도구가 없음). `python -m ruff` 가 실패하면
stdout 이 비는데 예전 코드는 이를 findings=[] 로 처리해 '바뀐 파일 ruff 0' 이 검사 없이 통과했다.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tools import verify_change as vc


def _proc(stdout: str, returncode: int, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["ruff"], returncode=returncode, stdout=stdout, stderr=stderr)


@pytest.fixture(autouse=True)
def _changed_lines(monkeypatch):
    # 바뀐 줄: a.py 의 3번 줄만
    monkeypatch.setattr(vc, "changed_lines_between", lambda _b, _h: {"a.py": {3}})


def _find(tmp_path: Path, row: int) -> dict:
    return {
        "filename": str(tmp_path / "a.py"),
        "location": {"row": row, "column": 1},
        "code": "F401",
        "message": "unused",
    }


def test_no_changed_python_files_means_no_ruff_run(tmp_path):
    assert vc._new_ruff_findings(None, tmp_path, "base", "head") == []


def test_clean_run_prints_empty_json_and_reports_nothing(tmp_path):
    assert vc._new_ruff_findings(_proc("[]", 0), tmp_path, "base", "head") == []


def test_missing_ruff_is_a_loud_failure_not_zero(tmp_path):
    """ruff 미설치: stdout 비고 종료코드 1(No module named ruff) → 실패 항목 1건."""
    out = vc._new_ruff_findings(_proc("", 1, "python: No module named ruff"), tmp_path, "base", "head")
    assert len(out) == 1 and "ruff 실행 실패" in out[0] and "No module named ruff" in out[0]


def test_ruff_internal_error_is_a_loud_failure(tmp_path):
    out = vc._new_ruff_findings(_proc("", 2, "error: invalid config"), tmp_path, "base", "head")
    assert len(out) == 1 and "ruff 실행 실패" in out[0]


def test_non_json_output_is_a_loud_failure(tmp_path):
    out = vc._new_ruff_findings(_proc("garbage", 1), tmp_path, "base", "head")
    assert len(out) == 1 and "JSON 이 아니다" in out[0]


def test_only_findings_on_changed_lines_are_new(tmp_path):
    payload = json.dumps([_find(tmp_path, 3), _find(tmp_path, 99)])
    out = vc._new_ruff_findings(_proc(payload, 1), tmp_path, "base", "head")
    assert len(out) == 1 and out[0].startswith("a.py:3:")


# ── 변경 파일이 많아도 ruff 명령줄이 한도를 넘지 않게 묶음으로 돌린다 (PR #160 WinError 206) ─────────


def test_run_ruff_splits_files_into_chunks_and_merges_json(monkeypatch, tmp_path):
    calls: list[list[str]] = []

    def fake_run(cmd, cwd, timeout=0):
        calls.append(cmd)
        files = [c for c in cmd if c.endswith(".py")]
        rows = [{"filename": f, "code": "E1", "message": "m", "location": {"row": 1, "column": 1}} for f in files[:1]]
        return _proc(json.dumps(rows), 1)

    monkeypatch.setattr(vc, "run", fake_run)
    monkeypatch.setattr(vc, "RUFF_CHUNK", 3)
    result = vc._run_ruff([], [f"f{i}.py" for i in range(7)], tmp_path)
    assert len(calls) == 3  # 7개 / 3 = 묶음 3번
    assert result.returncode == 1 and [r["filename"] for r in json.loads(result.stdout)] == ["f0.py", "f3.py", "f6.py"]


def test_run_ruff_returns_the_failing_chunk_so_the_failure_stays_loud(monkeypatch, tmp_path):
    answers = iter([_proc("[]", 0), _proc("", 2, "ruff: boom")])
    monkeypatch.setattr(vc, "run", lambda cmd, cwd, timeout=0: next(answers))
    monkeypatch.setattr(vc, "RUFF_CHUNK", 2)
    result = vc._run_ruff([], ["a.py", "b.py", "c.py"], tmp_path)
    assert result.returncode == 2
    findings = vc._new_ruff_findings(result, tmp_path, "base", "head")
    assert findings and "ruff 실행 실패" in findings[0]


def test_run_ruff_all_clean_gives_empty_json(monkeypatch, tmp_path):
    monkeypatch.setattr(vc, "run", lambda cmd, cwd, timeout=0: _proc("[]", 0))
    result = vc._run_ruff([], ["a.py"], tmp_path)
    assert (result.returncode, json.loads(result.stdout)) == (0, [])

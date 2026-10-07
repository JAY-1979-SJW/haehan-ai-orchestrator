"""verify_change — ruff 가 돌지 못하면 '0건'으로 조용히 통과하지 않고 실패로 드러낸다.

배경(2026-10-07): CI 러너에는 ruff 가 설치돼 있지 않았다(requirements·constraints 에 개발 도구가 없음). `python -m ruff` 가 실패하면
stdout 이 비는데 예전 코드는 이를 findings=[] 로 처리해 '바뀐 파일 ruff 0' 이 검사 없이 통과했다.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.ops import verify_change as vc


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

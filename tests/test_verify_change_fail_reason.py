"""verify_change — 영향 테스트 실패의 pytest 요약 줄 사유를 보고서에 남긴다.

재현 안 되는 CI 전용 실패(예: 2026-10-08 gabia_router_clean)가 나왔을 때, verify_change
보고서가 시험 id만 남기면 원인 추적이 막힌다 — 요약 줄의 사유(짧게 잘릴 수 있음)를 같이
남겨 바로 단서를 준다. 사유가 없는 줄(rc 로만 잡힌 합성 id 등)도 안전해야 한다.
"""

import argparse
import subprocess

from tools import verify_change as vc


def _completed(stdout: str, returncode: int = 1) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(["pytest"], returncode, stdout, "")


# ── _failure_reason ───────────────────────────────────────────────────────────


def test_failure_reason_extracts_text_after_dash():
    line = "FAILED tests/x.py::test_y - assert 401 == 200"
    assert vc._failure_reason(line, "tests/x.py::test_y") == "assert 401 == 200"


def test_failure_reason_empty_when_no_dash_separator():
    line = "FAILED tests/x.py::test_y"
    assert vc._failure_reason(line, "tests/x.py::test_y") == ""


def test_failure_reason_empty_when_id_not_in_line():
    assert vc._failure_reason("FAILED other::test", "tests/x.py::test_y") == ""


# ── _pytest(reasons=...) ───────────────────────────────────────────────────────


def test_pytest_fills_reasons_dict_for_failed_ids(tmp_path, monkeypatch):
    stdout = (
        "....\n"
        "=========================== short test summary info ===========================\n"
        "FAILED tests/x.py::test_y - AssertionError: assert 401 == 200\n"
    )
    monkeypatch.setattr(vc, "run", lambda cmd, cwd, timeout=900: _completed(stdout))
    reasons: dict[str, str] = {}
    out = vc._pytest(tmp_path, ["tests/x.py"], 60, reasons)
    assert out == ["tests/x.py::test_y"]
    assert reasons == {"tests/x.py::test_y": "AssertionError: assert 401 == 200"}


def test_pytest_reasons_none_by_default_does_not_crash(tmp_path, monkeypatch):
    """reasons 인자를 안 주면(기존 호출부 호환) 사유 없이 id 만 돌아온다."""
    stdout = "FAILED tests/x.py::test_y - assert 1 == 2\n"
    monkeypatch.setattr(vc, "run", lambda cmd, cwd, timeout=900: _completed(stdout))
    out = vc._pytest(tmp_path, ["tests/x.py"], 60)
    assert out == ["tests/x.py::test_y"]


def test_pytest_synthetic_rc_id_has_no_reason_when_output_empty(tmp_path, monkeypatch):
    """수집 자체가 안 된 rc 실패는 합성 id 라 요약 줄이 없다 — 출력도 비어있으면 사유도 빈 문자열."""
    monkeypatch.setattr(vc, "run", lambda cmd, cwd, timeout=900: _completed("", returncode=2))
    reasons: dict[str, str] = {}
    out = vc._pytest(tmp_path, ["tests/x.py", "tests/y.py"], 60, reasons)
    assert out == ["tests/x.py..(+1)::<rc=2>"]
    assert reasons == {"tests/x.py..(+1)::<rc=2>": ""}


def test_pytest_synthetic_rc_id_captures_output_tail(tmp_path, monkeypatch):
    """pytest 요약 줄이 안 남는 비정상 종료(INTERNALERROR 등)는 id 만으론 원인을 못 찾는다
    (2026-10-10, run38009465088 tests/google rc=3 재현 조사 중 CI 로그에 트레이스백이 안 남아
    원인 추적이 막혔음) — 출력 꼬리(최대 30줄)를 reasons 에 남겨 재발 시 바로 원인이 보이게 한다."""
    stdout = "\n".join(f"line{i}" for i in range(40))
    monkeypatch.setattr(vc, "run", lambda cmd, cwd, timeout=900: _completed(stdout, returncode=3))
    reasons: dict[str, str] = {}
    out = vc._pytest(tmp_path, ["tests/x.py"], 60, reasons)
    sid = out[0]
    assert "<rc=3>" in sid
    assert "line39" in reasons[sid]
    assert "line9" not in reasons[sid]  # 마지막 30줄만(line10..line39)


# ── _build_verify_report — 보고서에 사유가 붙는지 ──────────────────────────────


def _base_measurement(test_failures, reasons=None):
    return {
        "collect_errors": [],
        "import_fail": [],
        "routes": 0,
        "violations": [],
        "cycles": [],
        "skeleton": [],
        "test_failures": test_failures,
        "test_timeouts": [],
        "test_failure_reasons": reasons or {},
    }


def _args():
    return argparse.Namespace(base="base-ref", head="head-ref", expect_routes=None)


def test_report_appends_reason_to_new_failure_id():
    before = _base_measurement([])
    after = _base_measurement(["tests/x.py::test_y"], {"tests/x.py::test_y": "AssertionError: assert 401 == 200"})
    measurements = {
        "before": before,
        "after": after,
        "ruff_errors": [],
        "loc_deps": [],
        "moved": {},
        "receiving": set(),
        "kit_errors": [],
    }
    ok, report = vc._build_verify_report(_args(), ["tests/x.py"], ["tests/x.py"], measurements)
    assert ok is False
    assert "tests/x.py::test_y — AssertionError: assert 401 == 200" in report


def test_report_leaves_bare_id_when_reason_missing():
    """사유가 없는 새 실패 id(합성 rc id 등)는 그대로 id 만 — KeyError 없이 안전하게."""
    before = _base_measurement([])
    after = _base_measurement(["tests/x.py..(+1)::<rc=2>"], {})
    measurements = {
        "before": before,
        "after": after,
        "ruff_errors": [],
        "loc_deps": [],
        "moved": {},
        "receiving": set(),
        "kit_errors": [],
    }
    ok, report = vc._build_verify_report(_args(), ["tests/x.py"], ["tests/x.py"], measurements)
    assert ok is False
    assert "tests/x.py..(+1)::<rc=2>" in report


def test_report_missing_reasons_key_entirely_is_safe():
    """옛 버전 measurements 호환 — test_failure_reasons 키 자체가 없어도 안전(.get 기본값)."""
    before = _base_measurement([])
    after = _base_measurement(["tests/x.py::test_y"])
    del after["test_failure_reasons"]
    measurements = {
        "before": before,
        "after": after,
        "ruff_errors": [],
        "loc_deps": [],
        "moved": {},
        "receiving": set(),
        "kit_errors": [],
    }
    ok, report = vc._build_verify_report(_args(), ["tests/x.py"], ["tests/x.py"], measurements)
    assert ok is False
    assert "tests/x.py::test_y" in report

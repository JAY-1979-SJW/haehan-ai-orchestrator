"""test_excel_diff_reporter — 변경 보고 모듈 단위 테스트."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


def test_validation_report_add_error():
    """보고서에 오류를 추가한다."""
    from agent.excel import diff_reporter

    report = diff_reporter.ValidationReport()
    report.add_error({"type": "test", "message": "Test error"})

    assert len(report.errors) == 1
    assert report.is_valid() is False


def test_validation_report_add_warning():
    """보고서에 경고를 추가한다."""
    from agent.excel import diff_reporter

    report = diff_reporter.ValidationReport()
    report.add_warning({"type": "test", "message": "Test warning"})

    assert len(report.warnings) == 1
    assert report.is_valid() is True


def test_validation_report_to_dict():
    """보고서를 dict로 변환한다."""
    from agent.excel import diff_reporter

    report = diff_reporter.ValidationReport()
    report.add_error({"type": "error1"})
    report.add_warning({"type": "warning1"})
    report.add_info({"type": "info1"})

    result = report.to_dict()

    assert result["success"] is False
    assert result["summary"]["errors"] == 1
    assert result["summary"]["warnings"] == 1
    assert result["summary"]["info"] == 1


def test_build_change_diff():
    """변경 diff를 생성한다."""
    from agent.excel import diff_reporter

    before = {"cells": {"A1": "100"}}
    after = {"cells": {"A1": "200"}}

    diff, err = diff_reporter.build_change_diff(before, after)

    assert err is None
    assert diff is not None
    assert isinstance(diff, dict)


def test_compare_formulas():
    """수식 비교를 수행한다."""
    from agent.excel import diff_reporter

    before = {"A1": "=SUM(A1:A10)"}
    after = {"A1": "=SUM(A1:A11)"}

    issues, err = diff_reporter.compare_formulas(before, after)

    assert err is None
    assert isinstance(issues, list)

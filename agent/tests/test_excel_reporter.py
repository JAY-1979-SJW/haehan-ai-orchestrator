"""test_excel_reporter — 보고서 생성 모듈 단위 테스트."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


def test_build_analysis_report_empty():
    from agent.excel import reporter

    report = reporter.build_analysis_report(sheet_name="Sheet1")

    assert report["sheet_name"] == "Sheet1"
    assert "summary" in report
    assert "issues" in report
    assert "recommendations" in report
    assert isinstance(report["issues"], list)


def test_build_analysis_report_with_issues():
    from agent.excel import reporter

    data_validation = {
        "error_cells": 5,
        "empty_cells": 10,
        "empty_percentage": 20.0,
        "quality_score": 80.0,
    }

    report = reporter.build_analysis_report(
        sheet_name="Sheet1",
        data_validation=data_validation,
    )

    assert report["summary"]["quality_score"] == 80.0
    assert len(report["issues"]) > 0


def test_format_report_as_text():
    from agent.excel import reporter

    report = reporter.build_analysis_report(
        sheet_name="Sheet1",
        data_validation={"quality_score": 85.0},
    )

    text = reporter.format_report_as_text(report)

    assert isinstance(text, str)
    assert "Sheet1" in text
    assert "품질 점수" in text or "quality" in text.lower()


def test_summarize_changes_no_change():
    from agent.excel import reporter

    report = reporter.build_analysis_report(sheet_name="Sheet1")

    changes = reporter.summarize_changes(report, report)

    assert changes["quality_delta"] == 0.0
    assert changes["issue_delta"] == 0
    assert len(changes["improvements"]) == 0
    assert len(changes["regressions"]) == 0


def test_summarize_changes_with_improvement():
    from agent.excel import reporter

    before = reporter.build_analysis_report(
        sheet_name="Sheet1",
        data_validation={"quality_score": 50.0},
    )
    before["summary"]["issue_count"] = 5

    after = reporter.build_analysis_report(
        sheet_name="Sheet1",
        data_validation={"quality_score": 80.0},
    )
    after["summary"]["issue_count"] = 1

    changes = reporter.summarize_changes(before, after)

    assert changes["quality_delta"] == 30.0
    assert changes["issue_delta"] == -4

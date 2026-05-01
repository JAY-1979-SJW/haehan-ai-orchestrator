"""test_excel_change_tracker — 변경 추적 모듈 단위 테스트."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


def test_compare_analyses_no_change():
    from agent.excel import change_tracker

    analysis = {
        "success": True,
        "sheet": "Sheet1",
        "analysis": {
            "table_structure": {
                "summary": {"row_count": 10, "col_count": 5},
            },
            "data_quality": {
                "quality_score": 85.0,
                "error_cells": 0,
            },
            "formula_errors": {
                "error_count": 0,
            },
        },
    }

    result, err = change_tracker.compare_analyses(analysis, analysis)

    assert err is None
    assert result is not None
    assert not result["table_structure_changed"]
    assert not result["data_quality_changed"]
    assert not result["formula_errors_changed"]


def test_compare_analyses_with_change():
    from agent.excel import change_tracker

    before = {
        "success": True,
        "analysis": {
            "table_structure": {
                "summary": {"row_count": 10, "col_count": 5},
            },
            "data_quality": {
                "quality_score": 85.0,
                "error_cells": 0,
            },
            "formula_errors": {
                "error_count": 0,
            },
        },
    }

    after = {
        "success": True,
        "analysis": {
            "table_structure": {
                "summary": {"row_count": 15, "col_count": 5},
            },
            "data_quality": {
                "quality_score": 80.0,
                "error_cells": 2,
            },
            "formula_errors": {
                "error_count": 1,
            },
        },
    }

    result, err = change_tracker.compare_analyses(before, after)

    assert err is None
    assert result is not None
    assert result["table_structure_changed"]
    assert result["data_quality_changed"]
    assert result["formula_errors_changed"]


def test_track_cell_changes_no_changes():
    from agent.excel import change_tracker

    fake_sheet = MagicMock()
    fake_cell = MagicMock()
    fake_cell.Value = 100
    fake_sheet.Cells.return_value = fake_cell

    result, err = change_tracker.track_cell_changes(
        fake_sheet, fake_sheet, start_row=1, end_row=5, start_col=1, end_col=3
    )

    assert err is None
    assert result is not None
    assert result["change_count"] == 0


def test_track_cell_changes_with_changes():
    from agent.excel import change_tracker

    before_sheet = MagicMock()
    after_sheet = MagicMock()

    before_cell = MagicMock()
    before_cell.Value = 100

    after_cell = MagicMock()
    after_cell.Value = 200

    before_sheet.Cells.return_value = before_cell
    after_sheet.Cells.return_value = after_cell

    result, err = change_tracker.track_cell_changes(
        before_sheet, after_sheet, start_row=1, end_row=5, start_col=1, end_col=3
    )

    assert err is None
    assert result is not None
    # 15개 셀 모두 변경 (1x5x3 = 15)
    assert result["change_count"] > 0


def test_generate_change_summary_no_change():
    from agent.excel import change_tracker

    analysis = {
        "success": True,
        "analysis": {
            "table_structure": {
                "summary": {"row_count": 10, "col_count": 5},
            },
            "data_quality": {
                "quality_score": 85.0,
            },
        },
    }

    result, err = change_tracker.generate_change_summary(analysis, analysis)

    assert err is None
    assert result is not None
    assert "summary" in result
    assert "변경 사항 없음" in result["summary"]


def test_generate_change_summary_with_change():
    from agent.excel import change_tracker

    before = {
        "success": True,
        "analysis": {
            "table_structure": {
                "summary": {"row_count": 10, "col_count": 5},
            },
            "data_quality": {
                "quality_score": 85.0,
                "error_cells": 0,
            },
        },
    }

    after = {
        "success": True,
        "analysis": {
            "table_structure": {
                "summary": {"row_count": 12, "col_count": 5},
            },
            "data_quality": {
                "quality_score": 80.0,
                "error_cells": 1,
            },
        },
    }

    result, err = change_tracker.generate_change_summary(before, after)

    assert err is None
    assert result is not None
    assert len(result["changes"]) > 0
    assert "impact" in result

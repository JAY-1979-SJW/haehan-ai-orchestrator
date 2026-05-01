"""test_excel_data_validator — 데이터 검증 모듈 단위 테스트."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


def test_check_empty_cells_in_range_success():
    from agent.excel import data_validator

    fake_sheet = MagicMock()
    fake_cell = MagicMock()
    fake_cell.Value = None
    fake_sheet.Cells.return_value = fake_cell

    result, err = data_validator.check_empty_cells_in_range(
        fake_sheet, start_row=1, end_row=10, start_col=1, end_col=5
    )

    assert err is None
    assert result is not None
    assert "total_cells" in result
    assert "empty_cells" in result
    assert "empty_percentage" in result


def test_detect_duplicates_in_column_no_duplicates():
    from agent.excel import data_validator

    fake_sheet = MagicMock()
    fake_cell = MagicMock()
    fake_cell.Value = "unique"
    fake_sheet.Cells.return_value = fake_cell

    result, err = data_validator.detect_duplicates_in_column(
        fake_sheet, col_num=1, start_row=1, end_row=10
    )

    assert err is None
    assert result is not None
    assert "has_duplicates" in result


def test_check_numeric_consistency_all_numeric():
    from agent.excel import data_validator

    fake_sheet = MagicMock()
    fake_cell = MagicMock()
    fake_cell.Value = 100
    fake_sheet.Cells.return_value = fake_cell

    result, err = data_validator.check_numeric_consistency(
        fake_sheet, col_num=1, start_row=1, end_row=10
    )

    assert err is None
    assert result is not None
    assert result["numeric_count"] == 10


def test_validate_data_range_success():
    from agent.excel import data_validator

    fake_sheet = MagicMock()
    fake_cell = MagicMock()
    fake_cell.Value = "data"
    fake_cell.Formula = None
    fake_sheet.Cells.return_value = fake_cell

    result, err = data_validator.validate_data_range(
        fake_sheet, start_row=1, end_row=10, start_col=1, end_col=5
    )

    assert err is None
    assert result is not None
    assert "quality_score" in result
    assert 0 <= result["quality_score"] <= 100

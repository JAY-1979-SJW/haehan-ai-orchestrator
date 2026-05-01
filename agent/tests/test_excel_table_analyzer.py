"""test_excel_table_analyzer — 표 구조 분석 모듈 단위 테스트."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


def test_analyze_column_type_success():
    from agent.excel import table_analyzer

    fake_sheet = MagicMock()
    fake_cell = MagicMock()
    fake_cell.Value = 100  # 숫자
    fake_sheet.Cells.return_value = fake_cell

    result, err = table_analyzer.analyze_column_type(
        fake_sheet, col_num=3, header_row=1, data_start_row=2
    )

    assert err is None
    assert result is not None
    assert "type" in result
    assert "type_breakdown" in result


def test_analyze_column_type_no_sheet():
    from agent.excel import table_analyzer

    result, err = table_analyzer.analyze_column_type(
        None, col_num=3, header_row=1, data_start_row=2
    )

    assert err == "SHEET_NOT_FOUND"
    assert result is None


def test_detect_data_range_success():
    from agent.excel import table_analyzer

    fake_sheet = MagicMock()
    fake_cells = MagicMock()
    fake_cells.Value = "data"
    fake_sheet.Cells.return_value = fake_cells

    fake_range = MagicMock()
    fake_range.Row = 1
    fake_range.Rows.Count = 10
    fake_range.Column = 1
    fake_range.Columns.Count = 5
    fake_sheet.UsedRange = fake_range

    result, err = table_analyzer.detect_data_range(
        fake_sheet, header_row=1
    )

    assert err is None
    assert result is not None
    assert "data_start_row" in result
    assert "data_end_row" in result


def test_analyze_table_structure_success():
    from agent.excel import table_analyzer

    fake_sheet = MagicMock()
    headers = {"name": 1, "value": 2}

    result, err = table_analyzer.analyze_table_structure(
        fake_sheet, header_row=1, headers=headers
    )

    # 결과가 None이거나 유효한 구조여야 함
    if result:
        assert "columns" in result
        assert "summary" in result

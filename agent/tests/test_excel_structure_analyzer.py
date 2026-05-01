"""test_excel_structure_analyzer — 시트 구조 분석 모듈 단위 테스트."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


def test_analyze_active_sheet_structure_success():
    from agent.excel import structure_analyzer

    fake_sheet = MagicMock()
    fake_sheet.Name = "Sheet1"

    # UsedRange mock
    fake_used_range = MagicMock()
    fake_used_range.Row = 1
    fake_used_range.Column = 1
    fake_used_range.Rows.Count = 20
    fake_used_range.Columns.Count = 5
    fake_sheet.UsedRange = fake_used_range

    # Cells mock
    fake_cell = MagicMock()
    fake_cell.Value = "test"
    fake_cell.Formula = None
    fake_sheet.Cells.return_value = fake_cell

    result, err = structure_analyzer.analyze_active_sheet_structure(fake_sheet)

    assert err is None
    assert result is not None
    assert result["sheet_name"] == "Sheet1"
    assert "analysis_summary" in result
    assert isinstance(result["merged_cells"], list)
    assert isinstance(result["formula_cells"], list)


def test_analyze_active_sheet_structure_no_sheet():
    from agent.excel import structure_analyzer

    result, err = structure_analyzer.analyze_active_sheet_structure(None)

    assert err == "SHEET_NOT_FOUND"
    assert result is None


def test_detect_merged_cells():
    from agent.excel import merged_cell_detector

    fake_sheet = MagicMock()
    fake_merged = MagicMock()
    fake_merged.Row = 1
    fake_merged.Column = 1
    fake_merged.Rows.Count = 2
    fake_merged.Columns.Count = 2
    fake_sheet.MergedAreas = [fake_merged]

    result, err = merged_cell_detector.detect_merged_cells(fake_sheet)

    assert err is None
    assert isinstance(result, list)
    assert len(result) > 0
    assert result[0]["first_row"] == 1
    assert result[0]["first_col"] == 1


def test_detect_merged_cells_no_sheet():
    from agent.excel import merged_cell_detector

    result, err = merged_cell_detector.detect_merged_cells(None)

    assert err == "SHEET_NOT_FOUND"
    assert result is None


def test_detect_hidden_rows():
    from agent.excel import hidden_filter_detector

    fake_sheet = MagicMock()
    fake_row = MagicMock()
    fake_row.Hidden = True
    fake_sheet.Rows.return_value = fake_row

    result, err = hidden_filter_detector.detect_hidden_rows(fake_sheet, 1, 10)

    assert err is None
    assert isinstance(result, list)


def test_detect_autofilter():
    from agent.excel import hidden_filter_detector

    fake_sheet = MagicMock()
    fake_filter = MagicMock()
    fake_filter_range = MagicMock()
    fake_filter_range.Row = 1
    fake_filter_range.Column = 1
    fake_filter_range.Rows.Count = 1
    fake_filter_range.Columns.Count = 5
    fake_filter.Range = fake_filter_range
    fake_sheet.AutoFilter = fake_filter

    result, err = hidden_filter_detector.detect_autofilter(fake_sheet)

    assert err is None
    assert result is not None
    assert "has_filter" in result
    assert result["has_filter"] is True


def test_detect_table_regions():
    from agent.excel import table_region_detector

    fake_sheet = MagicMock()
    fake_list_obj = MagicMock()
    fake_range = MagicMock()
    fake_range.Row = 1
    fake_range.Column = 1
    fake_range.Rows.Count = 10
    fake_range.Columns.Count = 5
    fake_list_obj.Range = fake_range
    fake_list_obj.Name = "Table1"
    fake_sheet.ListObjects = [fake_list_obj]

    result, err = table_region_detector.detect_table_regions(fake_sheet)

    assert err is None
    assert isinstance(result, list)
    assert len(result) > 0
    assert result[0]["type"] == "table_object"


def test_detect_header_row_candidates():
    from agent.excel import table_region_detector

    fake_sheet = MagicMock()
    fake_cell = MagicMock()
    fake_cell.Value = "Header"
    fake_sheet.Cells.return_value = fake_cell
    fake_sheet.MergedAreas = None

    result, err = table_region_detector.detect_header_row_candidates(fake_sheet, 1, 10)

    assert err is None
    assert isinstance(result, list)


def test_detect_total_row_candidates():
    from agent.excel import table_region_detector

    fake_sheet = MagicMock()
    fake_cell = MagicMock()
    fake_cell.Value = "Total"
    fake_cell.Formula = "=SUM(A1:A10)"
    fake_sheet.Cells.return_value = fake_cell

    result, err = table_region_detector.detect_total_row_candidates(
        fake_sheet, data_start_row=2, data_end_row=10
    )

    assert err is None
    assert isinstance(result, list)

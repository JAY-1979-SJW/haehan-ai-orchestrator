"""test_excel_row_finder — 행 검색 모듈 단위 테스트."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


def test_find_row_by_header_value_success():
    from agent.excel import row_finder

    fake_sheet = MagicMock()
    fake_used_range = MagicMock()
    fake_used_range.Rows.Count = 10
    fake_sheet.UsedRange = fake_used_range

    def mock_cells(row, col):
        cell = MagicMock()
        if row == 5 and col == 1:
            cell.Value = "소화전함"
        else:
            cell.Value = None
        return cell

    fake_sheet.Cells = mock_cells

    row, err = row_finder.find_row_by_header_value(
        fake_sheet, header_row=2, match_col=1, match_value="소화전함"
    )

    assert err is None
    assert row == 5


def test_find_row_by_header_value_not_found():
    from agent.excel import row_finder

    fake_sheet = MagicMock()
    fake_used_range = MagicMock()
    fake_used_range.Rows.Count = 10
    fake_sheet.UsedRange = fake_used_range

    def mock_cells(row, col):
        cell = MagicMock()
        cell.Value = None
        return cell

    fake_sheet.Cells = mock_cells

    row, err = row_finder.find_row_by_header_value(
        fake_sheet, header_row=2, match_col=1, match_value="없는값"
    )

    assert err is not None
    assert "NOT_FOUND" in err
    assert row is None

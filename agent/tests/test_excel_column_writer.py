"""test_excel_column_writer — 열 삽입 및 채우기 모듈 단위 테스트."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


def test_insert_column_at_success():
    from agent.excel import column_writer

    fake_sheet = MagicMock()
    fake_cols = MagicMock()
    fake_sheet.Columns.return_value = fake_cols

    result, err = column_writer.insert_column_at(fake_sheet, col_num=3)

    assert err is None
    assert result is not None
    assert result["inserted_col"] == 3
    fake_sheet.Columns.assert_called()


def test_insert_column_at_invalid_col():
    from agent.excel import column_writer

    fake_sheet = MagicMock()
    result, err = column_writer.insert_column_at(fake_sheet, col_num=0)

    assert err == "INVALID_COL_NUM"
    assert result is None


def test_insert_column_at_no_sheet():
    from agent.excel import column_writer

    result, err = column_writer.insert_column_at(None, col_num=3)

    assert err == "SHEET_NOT_FOUND"
    assert result is None


def test_insert_column_next_to_header_success():
    from agent.excel import column_writer

    fake_sheet = MagicMock()
    fake_cell = MagicMock()
    fake_sheet.Cells.return_value = fake_cell
    fake_cols = MagicMock()
    fake_sheet.Columns.return_value = fake_cols

    result, err = column_writer.insert_column_next_to_header(
        fake_sheet, header_row=1, anchor_header="금액",
        anchor_col=4, new_header="부가세", position="right"
    )

    assert err is None
    assert result == 5  # col_num + 1


def test_insert_column_next_to_header_invalid_position():
    from agent.excel import column_writer

    fake_sheet = MagicMock()
    result, err = column_writer.insert_column_next_to_header(
        fake_sheet, header_row=1, anchor_header="금액",
        anchor_col=4, new_header="부가세", position="invalid"
    )

    assert err == "INVALID_POSITION"


def test_fill_column_values_success():
    from agent.excel import column_writer

    fake_sheet = MagicMock()
    fake_cell = MagicMock()
    fake_sheet.Cells.return_value = fake_cell

    values = [10, 20, 30, 40]
    result, err = column_writer.fill_column_values(
        fake_sheet, col_num=3, header_row=1, values=values
    )

    assert err is None
    assert result is not None
    assert result["filled_rows"] == 4


def test_fill_column_values_invalid_params():
    from agent.excel import column_writer

    result, err = column_writer.fill_column_values(None, 3, 1, [1, 2, 3])
    assert err == "SHEET_NOT_FOUND"

"""test_excel_row_writer — 행 삽입 및 채우기 모듈 단위 테스트."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


def test_insert_row_at_success():
    from agent.excel import row_writer

    fake_sheet = MagicMock()
    fake_rows = MagicMock()
    fake_sheet.Rows.return_value = fake_rows

    result, err = row_writer.insert_row_at(fake_sheet, row_num=5)

    assert err is None
    assert result is not None
    assert result["inserted_row"] == 5
    fake_sheet.Rows.assert_called()


def test_insert_row_at_invalid_row():
    from agent.excel import row_writer

    fake_sheet = MagicMock()
    result, err = row_writer.insert_row_at(fake_sheet, row_num=0)

    assert err == "INVALID_ROW_NUM"
    assert result is None


def test_insert_row_at_no_sheet():
    from agent.excel import row_writer

    result, err = row_writer.insert_row_at(None, row_num=5)

    assert err == "SHEET_NOT_FOUND"
    assert result is None


def test_fill_row_by_headers_success():
    from agent.excel import row_writer

    fake_sheet = MagicMock()
    fake_cell = MagicMock()
    fake_sheet.Cells.return_value = fake_cell

    headers = {"품명": 1, "규격": 2, "수량": 3}
    values = {"품명": "테스트", "규격": "A형", "수량": 10}

    result, err = row_writer.fill_row_by_headers(
        fake_sheet, row_num=5, values=values, headers=headers
    )

    assert err is None
    assert result is not None
    assert len(result["filled_cells"]) == 3
    assert result["filled_cells"][0]["header"] == "품명"


def test_fill_row_by_headers_invalid_params():
    from agent.excel import row_writer

    result, err = row_writer.fill_row_by_headers(None, 5, {}, {})
    assert err == "SHEET_NOT_FOUND"


def test_insert_row_by_match_invalid_position():
    from agent.excel import row_writer

    fake_sheet = MagicMock()
    result, err = row_writer.insert_row_by_match(
        fake_sheet, header_row=1, match_header="품명",
        match_value="테스트", match_col=1, position="invalid"
    )

    assert err == "INVALID_POSITION"
    assert result is None

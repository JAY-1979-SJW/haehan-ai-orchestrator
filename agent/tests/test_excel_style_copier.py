"""test_excel_style_copier — 서식 복사 모듈 단위 테스트."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


def test_copy_row_format_success():
    from agent.excel import style_copier

    fake_sheet = MagicMock()
    fake_src_row = MagicMock()
    fake_dst_row = MagicMock()
    fake_sheet.Rows.side_effect = [fake_src_row, fake_dst_row]

    result, err = style_copier.copy_row_format(fake_sheet, src_row=5, dst_row=6)

    assert err is None
    assert result is not None
    assert result["src_row"] == 5
    assert result["dst_row"] == 6


def test_copy_row_format_invalid_row():
    from agent.excel import style_copier

    fake_sheet = MagicMock()
    result, err = style_copier.copy_row_format(fake_sheet, src_row=0, dst_row=5)

    assert err == "INVALID_ROW_NUM"
    assert result is None


def test_copy_column_format_success():
    from agent.excel import style_copier

    fake_sheet = MagicMock()
    fake_src_col = MagicMock()
    fake_dst_col = MagicMock()
    fake_sheet.Columns.side_effect = [fake_src_col, fake_dst_col]

    result, err = style_copier.copy_column_format(
        fake_sheet, src_col=3, dst_col=4
    )

    assert err is None
    assert result is not None
    assert result["src_col"] == 3
    assert result["dst_col"] == 4


def test_copy_column_format_no_sheet():
    from agent.excel import style_copier

    result, err = style_copier.copy_column_format(None, src_col=3, dst_col=4)

    assert err == "SHEET_NOT_FOUND"
    assert result is None


def test_copy_cell_format_success():
    from agent.excel import style_copier

    fake_sheet = MagicMock()
    fake_src_cell = MagicMock()
    fake_dst_cell = MagicMock()
    fake_sheet.Cells.side_effect = [fake_src_cell, fake_dst_cell]

    result, err = style_copier.copy_cell_format(
        fake_sheet, src_row=5, src_col=3, dst_row=6, dst_col=3
    )

    assert err is None
    assert result is not None
    assert result["src"] == "C5"
    assert result["dst"] == "C6"


def test_copy_range_format_success():
    from agent.excel import style_copier

    fake_sheet = MagicMock()
    fake_src_range = MagicMock()
    fake_dst_range = MagicMock()
    fake_sheet.Range.side_effect = [fake_src_range, fake_dst_range]

    result, err = style_copier.copy_range_format(
        fake_sheet, src_range_addr="A1:D10", dst_range_addr="F1"
    )

    assert err is None
    assert result is not None
    assert result["src"] == "A1:D10"
    assert result["dst"] == "F1"

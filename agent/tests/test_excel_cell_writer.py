"""test_excel_cell_writer — 셀 수정 모듈 단위 테스트."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


def test_update_cell_success():
    from agent.excel import cell_writer

    fake_sheet = MagicMock()
    fake_cell = MagicMock()
    fake_cell.Value = 1  # old value
    fake_sheet.Cells.return_value = fake_cell

    result, err = cell_writer.update_cell(fake_sheet, row=5, col=3, new_value=99)

    assert err is None
    assert result is not None
    assert result["old_value"] == 1
    assert result["new_value"] == 99
    assert result["cell_address"] == "C5"


def test_col_letter():
    from agent.excel import cell_writer

    assert cell_writer.col_letter(1) == "A"
    assert cell_writer.col_letter(26) == "Z"
    assert cell_writer.col_letter(27) == "AA"
    assert cell_writer.col_letter(52) == "AZ"

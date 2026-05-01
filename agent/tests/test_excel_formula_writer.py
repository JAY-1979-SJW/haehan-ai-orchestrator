"""test_excel_formula_writer — 수식 입력 모듈 단위 테스트."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


def test_write_formula_to_cell_success():
    from agent.excel import formula_writer

    fake_sheet = MagicMock()
    fake_cell = MagicMock()
    fake_cell.Value = 30
    fake_sheet.Cells.return_value = fake_cell

    result, err = formula_writer.write_formula_to_cell(
        fake_sheet, row=5, col=3, formula="=A5+B5"
    )

    assert err is None
    assert result is not None
    assert result["formula"] == "=A5+B5"
    assert result["cell_address"] == "C5"


def test_write_formula_to_cell_auto_equals():
    from agent.excel import formula_writer

    fake_sheet = MagicMock()
    fake_cell = MagicMock()
    fake_cell.Value = 100
    fake_sheet.Cells.return_value = fake_cell

    result, err = formula_writer.write_formula_to_cell(
        fake_sheet, row=10, col=5, formula="SUM(A1:A10)"
    )

    assert err is None
    assert result["formula"] == "=SUM(A1:A10)"


def test_write_formula_to_cell_invalid_params():
    from agent.excel import formula_writer

    result, err = formula_writer.write_formula_to_cell(None, 5, 3, "=A1+B1")
    assert err == "SHEET_NOT_FOUND"

    result, err = formula_writer.write_formula_to_cell(
        MagicMock(), 5, 3, ""
    )
    assert err == "INVALID_FORMULA"


def test_fill_formula_down_success():
    from agent.excel import formula_writer

    fake_sheet = MagicMock()
    fake_cell = MagicMock()
    fake_cell.Value = None
    fake_sheet.Cells.return_value = fake_cell

    result, err = formula_writer.fill_formula_down(
        fake_sheet, start_row=2, end_row=5, col=3, formula_template="=A2*B2"
    )

    assert err is None
    assert result is not None
    assert result["filled_rows"] == 4


def test_build_formula_from_headers_success():
    from agent.excel import formula_writer

    headers = {"수량": 2, "단가": 3, "금액": 4}
    result, err = formula_writer.build_formula_from_headers(
        formula_expr="{수량}*{단가}",
        headers=headers,
        row=5
    )

    assert err is None
    assert result is not None
    assert "B5" in result  # 수량
    assert "C5" in result  # 단가
    assert result.startswith("=")


def test_build_formula_from_headers_complex():
    from agent.excel import formula_writer

    headers = {"금액": 3, "세율": 4}
    result, err = formula_writer.build_formula_from_headers(
        formula_expr="{금액}*{세율}",
        headers=headers,
        row=10
    )

    assert err is None
    assert "C10*D10" in result

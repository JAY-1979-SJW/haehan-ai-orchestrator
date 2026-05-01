"""test_excel_formula_validator — 수식 검증 모듈 단위 테스트."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


def test_extract_cell_references():
    from agent.excel import formula_validator

    refs = formula_validator.extract_cell_references("=A1+B2*C3")
    assert "A1" in refs
    assert "B2" in refs
    assert "C3" in refs

    refs = formula_validator.extract_cell_references("=SUM(A1:A10)")
    assert "A1" in refs
    assert "A10" in refs


def test_extract_cell_references_no_formula():
    from agent.excel import formula_validator

    refs = formula_validator.extract_cell_references("just text")
    assert refs == []


def test_validate_formula_in_cell_with_formula():
    from agent.excel import formula_validator

    fake_sheet = MagicMock()
    fake_cell = MagicMock()
    fake_cell.Formula = "=A1+B1"
    fake_cell.Value = 100
    fake_sheet.Cells.return_value = fake_cell

    result, err = formula_validator.validate_formula_in_cell(
        fake_sheet, row=5, col=3
    )

    assert err is None
    assert result is not None
    assert result["has_formula"] is True
    assert result["formula"] == "=A1+B1"


def test_validate_formula_in_cell_with_error():
    from agent.excel import formula_validator

    fake_sheet = MagicMock()
    fake_cell = MagicMock()
    fake_cell.Formula = "=A1/0"
    fake_cell.Value = "#DIV/0!"
    fake_sheet.Cells.return_value = fake_cell

    result, err = formula_validator.validate_formula_in_cell(
        fake_sheet, row=5, col=3
    )

    assert err is None
    assert result["has_error"] is True


def test_check_formula_consistency_in_range_success():
    from agent.excel import formula_validator

    fake_sheet = MagicMock()
    fake_cell = MagicMock()
    fake_cell.Formula = "=A5+B5"
    fake_sheet.Cells.return_value = fake_cell

    result, err = formula_validator.check_formula_consistency_in_range(
        fake_sheet, start_row=5, end_row=10, col=3
    )

    assert err is None
    assert result is not None
    assert "all_consistent" in result


def test_scan_formula_errors_success():
    from agent.excel import formula_validator

    fake_sheet = MagicMock()
    fake_cell = MagicMock()
    fake_cell.Value = "#REF!"
    fake_sheet.Cells.return_value = fake_cell

    result, err = formula_validator.scan_formula_errors(
        fake_sheet, start_row=1, end_row=10, start_col=1, end_col=5
    )

    assert err is None
    assert result is not None
    assert "error_count" in result

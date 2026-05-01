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
    """수식에서 셀 참조를 추출한다."""
    from agent.excel import formula_validator

    formula = "=SUM(A1:A10) + B5"
    refs = formula_validator.extract_cell_references(formula)

    assert len(refs) > 0


def test_scan_formula_errors():
    """수식 에러를 스캔한다."""
    from agent.excel import formula_validator

    fake_sheet = MagicMock()
    fake_cell = MagicMock()
    fake_cell.Formula = "=SUM(A1:A10)"
    fake_cell.Value = 100
    fake_sheet.Cells.return_value = fake_cell

    result, err = formula_validator.scan_formula_errors(
        fake_sheet, 1, 10, 1, 5
    )

    assert result is not None

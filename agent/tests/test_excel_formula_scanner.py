"""test_excel_formula_scanner — 수식 스캔 모듈 단위 테스트."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


def test_scan_formula_cells_success():
    from agent.excel import formula_scanner

    fake_sheet = MagicMock()
    fake_cell = MagicMock()
    fake_cell.Formula = "=SUM(A1:A10)"
    fake_cell.Value = 100
    fake_sheet.Cells.return_value = fake_cell

    result, err = formula_scanner.scan_formula_cells(
        fake_sheet, start_row=1, end_row=10, start_col=1, end_col=5
    )

    assert err is None
    assert isinstance(result, list)
    assert len(result) > 0
    assert result[0]["formula"] == "=SUM(A1:A10)"


def test_scan_formula_cells_no_sheet():
    from agent.excel import formula_scanner

    result, err = formula_scanner.scan_formula_cells(
        None, start_row=1, end_row=10, start_col=1, end_col=5
    )

    assert err == "SHEET_NOT_FOUND"
    assert result is None


def test_scan_formula_cells_no_formulas():
    from agent.excel import formula_scanner

    fake_sheet = MagicMock()
    fake_cell = MagicMock()
    fake_cell.Formula = None
    fake_cell.Value = 100
    fake_sheet.Cells.return_value = fake_cell

    result, err = formula_scanner.scan_formula_cells(
        fake_sheet, start_row=1, end_row=10, start_col=1, end_col=5
    )

    assert err is None
    assert isinstance(result, list)
    assert len(result) == 0


def test_detect_numeric_as_text_candidates_success():
    from agent.excel import formula_scanner

    fake_sheet = MagicMock()
    fake_cell = MagicMock()
    fake_cell.Value = "123"  # 문자로 저장된 숫자
    fake_cell.Formula = None
    fake_sheet.Cells.return_value = fake_cell

    result, err = formula_scanner.detect_numeric_as_text_candidates(
        fake_sheet, start_row=1, end_row=10, start_col=1, end_col=5
    )

    assert err is None
    assert isinstance(result, list)
    assert len(result) > 0
    assert result[0]["value"] == "123"


def test_detect_numeric_as_text_candidates_no_sheet():
    from agent.excel import formula_scanner

    result, err = formula_scanner.detect_numeric_as_text_candidates(
        None, start_row=1, end_row=10, start_col=1, end_col=5
    )

    assert err == "SHEET_NOT_FOUND"
    assert result is None


def test_detect_numeric_as_text_candidates_mixed():
    from agent.excel import formula_scanner

    fake_sheet = MagicMock()

    # 설정: 첫 호출 = 숫자 텍스트, 두 번째 = 일반 텍스트
    fake_cell_1 = MagicMock()
    fake_cell_1.Value = "456"
    fake_cell_1.Formula = None

    fake_cell_2 = MagicMock()
    fake_cell_2.Value = "Not a number"
    fake_cell_2.Formula = None

    # 셀을 번갈아 반환하도록 설정
    fake_sheet.Cells.side_effect = [fake_cell_1, fake_cell_2]

    result, err = formula_scanner.detect_numeric_as_text_candidates(
        fake_sheet, start_row=1, end_row=2, start_col=1, end_col=1
    )

    assert err is None
    assert isinstance(result, list)
    # 첫 번째 셀만 숫자 텍스트로 감지되어야 함
    assert len(result) >= 1
    assert result[0]["value"] == "456"

"""test_excel_total_validator — 합계 행 검증 모듈 단위 테스트."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


def test_validate_total_rows_success():
    """합계 행이 정상이면 이슈 없음."""
    from agent.excel import total_validator

    fake_sheet = MagicMock()
    fake_cell = MagicMock()
    fake_cell.Formula = "=SUM(A2:A100)"
    fake_sheet.Cells.return_value = fake_cell

    issues, err = total_validator.validate_total_rows(
        fake_sheet, 2, 100, [101]
    )

    assert err is None
    assert isinstance(issues, list)


def test_validate_total_rows_no_sheet():
    """시트가 없으면 오류."""
    from agent.excel import total_validator

    issues, err = total_validator.validate_total_rows(
        None, 2, 100, [101]
    )

    assert err == "SHEET_NOT_FOUND"
    assert issues is None

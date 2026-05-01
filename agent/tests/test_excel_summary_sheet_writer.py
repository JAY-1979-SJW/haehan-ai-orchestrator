"""test_excel_summary_sheet_writer — 요약 시트 작성 모듈 단위 테스트."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


def test_create_summary_sheet_success():
    """요약 시트를 성공적으로 생성한다."""
    from agent.excel import summary_sheet_writer

    fake_wb = MagicMock()
    fake_sheets = MagicMock()
    fake_new_sheet = MagicMock()

    fake_wb.Sheets = fake_sheets
    fake_wb.Sheets.Count = 1
    fake_sheets.Add.return_value = fake_new_sheet
    fake_sheets.__iter__.return_value = []

    change_log = {
        "executed_operations": 3,
        "total_operations": 3,
        "success": True,
    }

    validation_report = {
        "success": True,
        "summary": {
            "errors": 0,
            "warnings": 2,
            "info": 1,
        },
        "issues": [],
    }

    success, error, result = summary_sheet_writer.create_summary_sheet(
        fake_wb,
        change_log=change_log,
        validation_report=validation_report,
    )

    assert success is True
    assert error is None
    assert "sheet_name" in result


def test_create_summary_sheet_no_workbook():
    """Workbook이 없으면 실패한다."""
    from agent.excel import summary_sheet_writer

    success, error, result = summary_sheet_writer.create_summary_sheet(None)

    assert success is False
    assert error == "WORKBOOK_NOT_FOUND"


def test_build_change_table():
    """변경 내역 표를 작성한다."""
    from agent.excel import report_table_builder

    fake_sheet = MagicMock()
    fake_cell = MagicMock()
    fake_sheet.Cells.return_value = fake_cell

    change_log = {
        "logs": [
            {
                "operation_type": "update_cell",
                "status": "success",
                "sheet": "Sheet1",
                "message": "Cell updated",
            }
        ]
    }

    success, error, end_row = report_table_builder.build_change_table(
        fake_sheet, 1, change_log
    )

    assert success is True
    assert error is None
    assert end_row > 1


def test_build_validation_table():
    """검증 결과 표를 작성한다."""
    from agent.excel import report_table_builder

    fake_sheet = MagicMock()
    fake_cell = MagicMock()
    fake_sheet.Cells.return_value = fake_cell

    validation_report = {
        "issues": [
            {
                "severity": "warning",
                "type": "formula_gap",
                "cell": "A1",
                "message": "Formula missing",
            }
        ]
    }

    success, error, end_row = report_table_builder.build_validation_table(
        fake_sheet, 1, validation_report
    )

    assert success is True
    assert error is None
    assert end_row > 1


def test_build_summary_table():
    """요약 표를 작성한다."""
    from agent.excel import report_table_builder

    fake_sheet = MagicMock()
    fake_cell = MagicMock()
    fake_sheet.Cells.return_value = fake_cell

    change_log = {
        "total_operations": 3,
        "executed_operations": 3,
    }

    validation_report = {
        "summary": {
            "errors": 0,
            "warnings": 2,
            "info": 1,
        }
    }

    success, error, end_row = report_table_builder.build_summary_table(
        fake_sheet, 1, change_log, validation_report
    )

    assert success is True
    assert error is None
    assert end_row > 1

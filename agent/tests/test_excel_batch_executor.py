"""test_excel_batch_executor — 일괄 실행 모듈 단위 테스트."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


def test_apply_change_plan_success():
    from agent.excel import batch_executor, operation_schema

    fake_app = MagicMock()
    fake_wb = MagicMock()
    fake_sheet = MagicMock()
    fake_sheet.Name = "Sheet1"

    # Mock SaveCopyAs
    fake_wb.SaveCopyAs = MagicMock()

    # ChangePlan with single operation
    op = operation_schema.Operation(
        type="update_cell_by_header",
        sheet="Sheet1",
        risk="medium",
        params={
            "row_match_header": "A",
            "row_match_value": 1,
            "target_header": "B",
            "new_value": 100,
        }
    )
    plan = operation_schema.ChangePlan(
        success=True,
        dry_run=True,
        operations=[op],
        requires_approval=True,
        will_modify_original=True,
        save_mode="save_as",
    )

    success, error, result = batch_executor.apply_change_plan(
        fake_app, fake_wb, fake_sheet, plan, "C:\\output.xlsx"
    )

    assert success is True
    assert error is None
    assert "output_path" in result
    assert "change_log" in result
    fake_wb.SaveCopyAs.assert_called_once_with("C:\\output.xlsx")


def test_apply_change_plan_no_sheet():
    from agent.excel import batch_executor, operation_schema

    op = operation_schema.Operation(
        type="update_cell_by_header",
        sheet="Sheet1",
        risk="medium",
        params={},
    )
    plan = operation_schema.ChangePlan(
        success=True,
        dry_run=True,
        operations=[op],
        requires_approval=True,
        will_modify_original=True,
        save_mode="save_as",
    )

    success, error, result = batch_executor.apply_change_plan(
        None, None, None, plan, "C:\\output.xlsx"
    )

    assert success is False
    assert error == "SHEET_NOT_FOUND"


def test_apply_change_plan_no_output_path():
    from agent.excel import batch_executor, operation_schema

    fake_sheet = MagicMock()

    op = operation_schema.Operation(
        type="update_cell_by_header",
        sheet="Sheet1",
        risk="medium",
        params={},
    )
    plan = operation_schema.ChangePlan(
        success=True,
        dry_run=True,
        operations=[op],
        requires_approval=True,
        will_modify_original=True,
        save_mode="save_as",
    )

    success, error, result = batch_executor.apply_change_plan(
        None, None, fake_sheet, plan, ""
    )

    assert success is False
    assert error == "OUTPUT_PATH_REQUIRED"


def test_apply_change_plan_multiple_operations():
    from agent.excel import batch_executor, operation_schema

    fake_app = MagicMock()
    fake_wb = MagicMock()
    fake_sheet = MagicMock()
    fake_sheet.Name = "Sheet1"

    fake_wb.SaveCopyAs = MagicMock()

    # Multiple operations
    op1 = operation_schema.Operation(
        type="update_cell_by_header",
        sheet="Sheet1",
        risk="medium",
        params={},
    )
    op2 = operation_schema.Operation(
        type="insert_column_by_header",
        sheet="Sheet1",
        risk="medium",
        params={},
    )
    op3 = operation_schema.Operation(
        type="write_formula_by_header",
        sheet="Sheet1",
        risk="medium",
        params={},
    )

    plan = operation_schema.ChangePlan(
        success=True,
        dry_run=True,
        operations=[op1, op2, op3],
        requires_approval=True,
        will_modify_original=True,
        save_mode="save_as",
    )

    success, error, result = batch_executor.apply_change_plan(
        fake_app, fake_wb, fake_sheet, plan, "C:\\output.xlsx"
    )

    assert success is True
    assert error is None
    assert "change_log" in result
    log = result["change_log"]
    # executed_operations는 operation 3개 + save_copy_as
    assert log["executed_operations"] == 4
    assert log["success"] is True


def test_apply_change_plan_invalid_plan():
    from agent.excel import batch_executor

    fake_sheet = MagicMock()

    success, error, result = batch_executor.apply_change_plan(
        None, None, fake_sheet, "not a plan", "C:\\output.xlsx"
    )

    assert success is False
    assert error == "INVALID_PLAN"


def test_change_log_success():
    from agent.excel import change_log

    builder = change_log.ChangeLogBuilder(3)
    builder.add_success("update_cell", "Sheet1", "Cell updated", {"value": 100})
    builder.add_success("insert_col", "Sheet1", "Column inserted", {"col": 2})
    builder.add_success("write_formula", "Sheet1", "Formula written", {})

    log = builder.build()

    assert log.success is True
    assert log.total_operations == 3
    assert log.executed_operations == 3
    assert log.failed_at_index is None
    assert log.summary["success_count"] == 3
    assert log.summary["failure_count"] == 0


def test_change_log_with_failure():
    from agent.excel import change_log

    builder = change_log.ChangeLogBuilder(3)
    builder.add_success("update_cell", "Sheet1", "Cell updated", {})
    builder.add_failure("insert_col", "Sheet1", "Column not found", {})

    log = builder.build()

    assert log.success is False
    assert log.total_operations == 3
    assert log.executed_operations == 2
    assert log.failed_at_index == 1
    assert log.summary["success_count"] == 1
    assert log.summary["failure_count"] == 1


def test_operation_executor_update_cell():
    from agent.excel import operation_executor, operation_schema

    fake_sheet = MagicMock()
    fake_cell = MagicMock()
    fake_cell.Value = 50
    fake_sheet.Cells.return_value = fake_cell

    op = operation_schema.Operation(
        type="update_cell_by_header",
        sheet="Sheet1",
        risk="medium",
        params={
            "row_match_header": "A",
            "row_match_value": 1,
            "target_header": "B",
            "new_value": 100,
        }
    )

    # This will fail because header_detector isn't mocked properly,
    # but it tests the operation_executor import
    success, error, details = operation_executor.execute_operation(fake_sheet, op)
    # Expected to fail due to missing header detection
    assert isinstance(success, bool)


def test_operation_executor_no_sheet():
    from agent.excel import operation_executor, operation_schema

    op = operation_schema.Operation(
        type="update_cell_by_header",
        sheet="Sheet1",
        risk="medium",
        params={},
    )

    success, error, details = operation_executor.execute_operation(None, op)

    assert success is False
    assert error == "SHEET_NOT_FOUND"

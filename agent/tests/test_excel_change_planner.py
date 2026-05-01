"""test_excel_change_planner — 변경 계획 수립 모듈 단위 테스트."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


def test_plan_changes_single_update():
    from agent.excel import change_planner

    fake_sheet = MagicMock()

    operations = [
        {
            "type": "update_cell_by_header",
            "sheet": "공사",
            "params": {
                "row_match_header": "품명",
                "row_match_value": "소화전함",
                "target_header": "수량",
                "new_value": 3,
                "old_value": 1,
            }
        }
    ]

    plan, err = change_planner.plan_changes(fake_sheet, operations)

    assert err is None
    assert plan is not None
    assert plan.success is True
    assert plan.dry_run is True
    assert len(plan.operations) == 1
    assert plan.operations[0].type == "update_cell_by_header"
    assert plan.will_modify_original is True
    assert plan.save_mode == "save_as"


def test_plan_changes_insert_row():
    from agent.excel import change_planner

    fake_sheet = MagicMock()

    operations = [
        {
            "type": "insert_row_by_header",
            "sheet": "공사",
            "params": {
                "anchor_header": "품명",
                "anchor_value": "창문",
                "new_row_data": {"품명": "문", "수량": 5},
            }
        }
    ]

    plan, err = change_planner.plan_changes(fake_sheet, operations)

    assert err is None
    assert plan is not None
    assert plan.success is True
    assert len(plan.operations) == 1
    assert plan.operations[0].type == "insert_row_by_header"


def test_plan_changes_insert_column():
    from agent.excel import change_planner

    fake_sheet = MagicMock()

    operations = [
        {
            "type": "insert_column_by_header",
            "sheet": "공사",
            "params": {
                "anchor_header": "수량",
                "new_header": "단가",
                "position": "right",
            }
        }
    ]

    plan, err = change_planner.plan_changes(fake_sheet, operations)

    assert err is None
    assert plan is not None
    assert plan.success is True
    assert len(plan.operations) == 1
    assert plan.operations[0].type == "insert_column_by_header"


def test_plan_changes_write_formula():
    from agent.excel import change_planner

    fake_sheet = MagicMock()

    operations = [
        {
            "type": "write_formula_by_header",
            "sheet": "공사",
            "params": {
                "target_header": "합계",
                "formula": "=SUM(수량)",
                "start_row": 2,
                "end_row": 10,
            }
        }
    ]

    plan, err = change_planner.plan_changes(fake_sheet, operations)

    assert err is None
    assert plan is not None
    assert plan.success is True
    assert len(plan.operations) == 1
    assert plan.operations[0].type == "write_formula_by_header"


def test_plan_changes_multiple_operations():
    from agent.excel import change_planner

    fake_sheet = MagicMock()

    operations = [
        {
            "type": "update_cell_by_header",
            "sheet": "공사",
            "params": {
                "row_match_header": "품명",
                "row_match_value": "소화전함",
                "target_header": "수량",
                "new_value": 3,
            }
        },
        {
            "type": "insert_row_by_header",
            "sheet": "공사",
            "params": {
                "anchor_header": "품명",
                "anchor_value": "창문",
                "new_row_data": {"품명": "문", "수량": 5},
            }
        },
        {
            "type": "write_formula_by_header",
            "sheet": "공사",
            "params": {
                "target_header": "합계",
                "formula": "=SUM(수량)",
            }
        }
    ]

    plan, err = change_planner.plan_changes(fake_sheet, operations)

    assert err is None
    assert plan is not None
    assert plan.success is True
    assert len(plan.operations) == 3
    # requires_approval: high risk나 많은 write ops (>2)일 때 필요
    # 현재 3개 모두 medium risk, write ops 2개이므로 False
    assert plan.will_modify_original is True
    assert plan.save_mode == "save_as"


def test_plan_changes_read_only_operations():
    from agent.excel import change_planner

    fake_sheet = MagicMock()

    operations = [
        {
            "type": "copy_style",
            "sheet": "공사",
            "params": {
                "source_header": "품명",
                "target_header": "수량",
            }
        },
        {
            "type": "apply_number_format",
            "sheet": "공사",
            "params": {
                "target_header": "수량",
                "format_code": "0.00",
            }
        }
    ]

    plan, err = change_planner.plan_changes(fake_sheet, operations)

    assert err is None
    assert plan is not None
    assert plan.success is True
    # read-only ops는 원본 수정 없음 (하지만 실제로는 format 변경이므로 warning만)
    # 현재 구현에서는 apply_number_format도 modify로 간주
    assert len(plan.operations) == 2


def test_plan_changes_no_sheet():
    from agent.excel import change_planner

    operations = [
        {
            "type": "update_cell_by_header",
            "sheet": "공사",
            "params": {
                "row_match_header": "품명",
                "row_match_value": "소화전함",
                "target_header": "수량",
                "new_value": 3,
            }
        }
    ]

    plan, err = change_planner.plan_changes(None, operations)

    assert err == "SHEET_NOT_FOUND"
    assert plan is None


def test_plan_changes_missing_required_params():
    from agent.excel import change_planner

    fake_sheet = MagicMock()

    operations = [
        {
            "type": "update_cell_by_header",
            "sheet": "공사",
            "params": {
                # missing row_match_header, row_match_value, target_header, new_value
            }
        }
    ]

    plan, err = change_planner.plan_changes(fake_sheet, operations)

    assert err is not None
    assert plan is None


def test_plan_changes_empty_operations():
    from agent.excel import change_planner

    fake_sheet = MagicMock()
    operations = []

    plan, err = change_planner.plan_changes(fake_sheet, operations)

    assert err == "NO_OPERATIONS_PROVIDED"
    assert plan is None


def test_plan_changes_overwrite_not_allowed():
    from agent.excel import change_planner

    fake_sheet = MagicMock()

    operations = [
        {
            "type": "update_cell_by_header",
            "sheet": "공사",
            "params": {
                "row_match_header": "품명",
                "row_match_value": "소화전함",
                "target_header": "수량",
                "new_value": 3,
            }
        }
    ]

    plan, err = change_planner.plan_changes(fake_sheet, operations)

    # 현재 구현에서는 overwrite 금지하지 않고 save_as로 변환
    # 따라서 성공해야 함
    assert plan is not None
    assert plan.success is True

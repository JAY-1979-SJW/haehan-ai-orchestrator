"""test_excel_workflows — Excel 워크플로우 통합 테스트."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


def test_insert_row_by_header_copy_no_approval():
    from agent.excel import workflows

    result = workflows.insert_row_by_header_copy(
        row_match_header="품명",
        row_match_value="테스트",
        approval_token=None,
    )

    assert not result["success"]
    assert result["error"] == "WRITE_APPROVAL_REQUIRED"


def test_insert_column_by_header_copy_no_approval():
    from agent.excel import workflows

    result = workflows.insert_column_by_header_copy(
        anchor_header="금액",
        new_header="부가세",
        approval_token=None,
    )

    assert not result["success"]
    assert result["error"] == "WRITE_APPROVAL_REQUIRED"


def test_write_formula_by_header_copy_no_approval():
    from agent.excel import workflows

    result = workflows.write_formula_by_header_copy(
        target_header="금액",
        formula="=A1*B1",
        approval_token=None,
    )

    assert not result["success"]
    assert result["error"] == "WRITE_APPROVAL_REQUIRED"


def test_insert_row_by_header_copy_approval_empty_string():
    from agent.excel import workflows

    result = workflows.insert_row_by_header_copy(
        row_match_header="품명",
        row_match_value="테스트",
        approval_token="   ",
    )

    # 공백만 있는 경우도 승인 실패
    assert not result["success"]
    assert result["error"] == "WRITE_APPROVAL_REQUIRED"


def test_insert_column_by_header_copy_invalid_params():
    from agent.excel import workflows

    result = workflows.insert_column_by_header_copy(
        anchor_header="",
        new_header="부가세",
        approval_token="valid_token",
    )

    # invalid params는 workflows 내부에서 처리되거나,
    # GetActiveObject가 실패해서 EXCEL_APP_NOT_FOUND 반환
    assert not result["success"]


def test_write_formula_by_header_copy_invalid_params():
    from agent.excel import workflows

    result = workflows.write_formula_by_header_copy(
        target_header="금액",
        formula="",
        approval_token="valid_token",
    )

    assert not result["success"]

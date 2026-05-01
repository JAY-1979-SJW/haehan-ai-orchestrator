"""test_excel_header_detector — 헤더 인식 모듈 단위 테스트."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


def test_detect_header_row_success():
    from agent.excel import header_detector

    fake_sheet = MagicMock()

    def mock_cells(row, col):
        cell = MagicMock()
        if row == 2:
            if col == 1:
                cell.Value = "품명"
            elif col == 2:
                cell.Value = "규격"
            elif col == 3:
                cell.Value = "수량"
            else:
                cell.Value = None
        else:
            cell.Value = None
        return cell

    fake_sheet.Cells = mock_cells
    header_row, err = header_detector.detect_header_row(fake_sheet)

    assert err is None
    assert header_row == 2


def test_map_headers_success():
    from agent.excel import header_detector

    fake_sheet = MagicMock()

    def mock_cells(row, col):
        cell = MagicMock()
        if col == 1:
            cell.Value = "품명"
        elif col == 2:
            cell.Value = "규격"
        elif col == 3:
            cell.Value = "수량"
        else:
            cell.Value = None
        return cell

    fake_sheet.Cells = mock_cells
    headers, err = header_detector.map_headers(fake_sheet, header_row=2)

    assert err is None
    assert headers is not None
    assert headers["품명"] == 1
    assert headers["규격"] == 2
    assert headers["수량"] == 3

"""test_excel_copy_saver — 복사본 저장 모듈 단위 테스트."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


def test_build_safe_copy_path_with_output_path(tmp_path):
    from agent.excel import copy_saver

    fake_wb = MagicMock()
    fake_wb.Name = "test.xlsx"
    fake_wb.FullName = str(tmp_path / "original.xlsx")

    copy_file = str(tmp_path / "copy.xlsx")
    path, err = copy_saver.build_safe_copy_path(fake_wb, output_path=copy_file)

    assert err is None
    assert path == copy_file


def test_build_safe_copy_path_without_output_path():
    from agent.excel import copy_saver

    fake_wb = MagicMock()
    fake_wb.Name = "test.xlsx"
    fake_wb.FullName = "C:\\Users\\test\\original.xlsx"

    path, err = copy_saver.build_safe_copy_path(fake_wb, output_path=None)

    assert err is None
    assert path is not None
    assert "test_copy_" in path
    assert path.endswith(".xlsx")


def test_build_safe_copy_path_same_as_original(tmp_path):
    from agent.excel import copy_saver

    same_file = str(tmp_path / "test.xlsx")

    fake_wb = MagicMock()
    fake_wb.Name = "test.xlsx"
    fake_wb.FullName = same_file

    path, err = copy_saver.build_safe_copy_path(fake_wb, output_path=same_file)

    assert err is not None
    assert "SAME_AS_ORIGINAL" in err
    assert path is None


def test_save_copy_savecopyAs_success(tmp_path, monkeypatch):
    from agent.excel import copy_saver

    fake_wb = MagicMock()
    fake_wb.SaveCopyAs.return_value = None

    copy_file = str(tmp_path / "test_copy.xlsx")

    err = copy_saver.save_copy(fake_wb, copy_file)

    assert err is None
    fake_wb.SaveCopyAs.assert_called_once()
    # wb.Save() 호출 안 됨
    fake_wb.Save.assert_not_called()

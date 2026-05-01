"""excel_com_connector — 단위 테스트 (mock 기반).

실제 Excel/Windows COM 없이도 돌아야 하므로 모든 pywin32 / Dispatch /
workbook 객체는 MagicMock 으로 대체한다.

검증:
1) 플랫폼이 Windows 가 아닐 때 명확한 not-supported 반환
2) pywin32 미설치 (Dispatch import 실패) 시 dispatch_failed 반환
3) Dispatch 자체 실패 시 app_not_found 반환
4) open_workbook 경로 가드 (empty/relative/missing)
5) open_workbook COM 실패 → workbook_open_failed
6) 없는 sheet → sheet_not_found
7) read_cell / write_cell 성공 흐름
8) run_basic_poc mocked 성공 — Save/Close/Quit 호출 확인
9) run_basic_poc save_as 흐름 — SaveAs 호출 확인
10) 에러 코드가 errors.ALL_CODES 에 등록되어 있음
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


# ──────────────────────────────────────────────────────────────────
# 1) 비 Windows 환경 — not supported
# ──────────────────────────────────────────────────────────────────
def test_is_excel_available_non_windows(monkeypatch):
    from agent.connectors import excel_com_connector as com
    monkeypatch.setattr(com, "_is_windows", lambda: False)
    out = com.is_excel_available()
    assert out["ok"] is False
    assert out["excel_available"] is False
    assert out["error"] == com._err.EXCEL_COM_NOT_SUPPORTED


def test_open_excel_app_non_windows(monkeypatch):
    from agent.connectors import excel_com_connector as com
    monkeypatch.setattr(com, "_is_windows", lambda: False)
    app, err = com.open_excel_app()
    assert app is None
    assert err == com._err.EXCEL_COM_NOT_SUPPORTED


# ──────────────────────────────────────────────────────────────────
# 2) pywin32 import 실패
# ──────────────────────────────────────────────────────────────────
def test_is_excel_available_dispatch_import_failed(monkeypatch):
    from agent.connectors import excel_com_connector as com
    monkeypatch.setattr(com, "_is_windows", lambda: True)
    monkeypatch.setattr(
        com, "_try_import_win32com",
        lambda: (None, com._err.EXCEL_COM_DISPATCH_FAILED),
    )
    out = com.is_excel_available()
    assert out["ok"] is False
    assert out["error"] == com._err.EXCEL_COM_DISPATCH_FAILED


# ──────────────────────────────────────────────────────────────────
# 3) Dispatch 자체가 실패 (Excel 미설치 등)
# ──────────────────────────────────────────────────────────────────
def test_is_excel_available_dispatch_raises(monkeypatch):
    from agent.connectors import excel_com_connector as com

    fake_mod = MagicMock()
    fake_mod.Dispatch.side_effect = RuntimeError("CoCreateInstance failed")

    monkeypatch.setattr(com, "_is_windows", lambda: True)
    monkeypatch.setattr(com, "_try_import_win32com", lambda: (fake_mod, None))
    out = com.is_excel_available()
    assert out["ok"] is False
    assert out["error"] == com._err.EXCEL_APP_NOT_FOUND
    assert out["detail"] == "RuntimeError"


def test_open_excel_app_dispatch_raises(monkeypatch):
    from agent.connectors import excel_com_connector as com

    fake_mod = MagicMock()
    fake_mod.Dispatch.side_effect = OSError("COM unavailable")
    monkeypatch.setattr(com, "_is_windows", lambda: True)
    monkeypatch.setattr(com, "_try_import_win32com", lambda: (fake_mod, None))
    app, err = com.open_excel_app()
    assert app is None
    assert err == com._err.EXCEL_APP_NOT_FOUND


def test_open_excel_app_success(monkeypatch):
    from agent.connectors import excel_com_connector as com

    fake_app = MagicMock()
    fake_mod = MagicMock()
    fake_mod.Dispatch.return_value = fake_app
    monkeypatch.setattr(com, "_is_windows", lambda: True)
    monkeypatch.setattr(com, "_try_import_win32com", lambda: (fake_mod, None))

    app, err = com.open_excel_app(visible=False)
    assert err is None
    assert app is fake_app
    assert fake_app.DisplayAlerts is False
    assert fake_app.Visible is False


# ──────────────────────────────────────────────────────────────────
# 4) open_workbook 경로 가드
# ──────────────────────────────────────────────────────────────────
def test_open_workbook_empty_path():
    from agent.connectors import excel_com_connector as com
    wb, err = com.open_workbook(MagicMock(), "")
    assert wb is None
    assert err == com._err.FILE_PATH_REQUIRED


def test_open_workbook_relative_path():
    from agent.connectors import excel_com_connector as com
    wb, err = com.open_workbook(MagicMock(), "relative/path.xlsx")
    assert wb is None
    assert err == com._err.FILE_NOT_ALLOWED


def test_open_workbook_missing_file(tmp_path):
    from agent.connectors import excel_com_connector as com
    target = tmp_path / "nope.xlsx"
    wb, err = com.open_workbook(MagicMock(), str(target))
    assert wb is None
    assert err == com._err.FILE_NOT_FOUND


def test_open_workbook_com_failure(tmp_path):
    from agent.connectors import excel_com_connector as com
    f = tmp_path / "x.xlsx"
    f.write_bytes(b"dummy")
    app = MagicMock()
    app.Workbooks.Open.side_effect = RuntimeError("COM: file locked")
    wb, err = com.open_workbook(app, str(f))
    assert wb is None
    assert err == com._err.WORKBOOK_OPEN_FAILED


def test_open_workbook_success(tmp_path):
    from agent.connectors import excel_com_connector as com
    f = tmp_path / "x.xlsx"
    f.write_bytes(b"dummy")
    fake_wb = MagicMock()
    app = MagicMock()
    app.Workbooks.Open.return_value = fake_wb
    wb, err = com.open_workbook(app, str(f), read_only=True)
    assert err is None
    assert wb is fake_wb
    app.Workbooks.Open.assert_called_once()
    _, kwargs = app.Workbooks.Open.call_args
    assert kwargs.get("ReadOnly") is True


# ──────────────────────────────────────────────────────────────────
# 5) 시트/셀 I/O
# ──────────────────────────────────────────────────────────────────
def test_read_cell_missing_sheet():
    from agent.connectors import excel_com_connector as com
    wb = MagicMock()
    wb.Worksheets.side_effect = Exception("no such sheet")
    val, err = com.read_cell(wb, "Nope", "A1")
    assert val is None
    assert err == com._err.SHEET_NOT_FOUND


def test_read_cell_success():
    from agent.connectors import excel_com_connector as com
    wb = MagicMock()
    sheet = MagicMock()
    wb.Worksheets.return_value = sheet
    cell = MagicMock()
    cell.Value = "HELLO"
    sheet.Range.return_value = cell
    val, err = com.read_cell(wb, "Sheet1", "A1")
    assert err is None
    assert val == "HELLO"
    sheet.Range.assert_called_once_with("A1")


def test_read_cell_range_raises():
    from agent.connectors import excel_com_connector as com
    wb = MagicMock()
    sheet = MagicMock()
    wb.Worksheets.return_value = sheet
    sheet.Range.side_effect = RuntimeError("bad ref")
    val, err = com.read_cell(wb, "Sheet1", "ZZZZ9999")
    assert val is None
    assert err == com._err.CELL_READ_FAILED


def test_write_cell_success():
    from agent.connectors import excel_com_connector as com
    wb = MagicMock()
    sheet = MagicMock()
    wb.Worksheets.return_value = sheet
    target = MagicMock()
    sheet.Range.return_value = target
    err = com.write_cell(
        wb, "Sheet1", "B2", "POC_OK",
        dry_run=False, allow_write=True, approval_token="DUMMY"
    )
    assert err is None
    assert target.Value == "POC_OK"


def test_write_cell_missing_sheet():
    from agent.connectors import excel_com_connector as com
    wb = MagicMock()
    wb.Worksheets.side_effect = Exception("no sheet")
    err = com.write_cell(
        wb, "ghost", "A1", "v",
        dry_run=False, allow_write=True, approval_token="DUMMY"
    )
    assert err == com._err.SHEET_NOT_FOUND


# ──────────────────────────────────────────────────────────────────
# 6) 저장 / 종료
# ──────────────────────────────────────────────────────────────────
def test_save_workbook_success():
    from agent.connectors import excel_com_connector as com
    wb = MagicMock()
    assert com.save_workbook(wb, dry_run=False, allow_write=True, approval_token="DUMMY") is None
    wb.Save.assert_called_once()


def test_save_workbook_failure():
    from agent.connectors import excel_com_connector as com
    wb = MagicMock()
    wb.Save.side_effect = OSError("disk full")
    assert com.save_workbook(wb, dry_run=False, allow_write=True, approval_token="DUMMY") == com._err.WORKBOOK_SAVE_FAILED


def test_save_workbook_as_requires_absolute(tmp_path):
    from agent.connectors import excel_com_connector as com
    wb = MagicMock()
    assert com.save_workbook_as(wb, "") == com._err.OUTPUT_PATH_REQUIRED
    assert com.save_workbook_as(wb, "rel/out.xlsx") == com._err.OUTPUT_PATH_NOT_ALLOWED


def test_save_workbook_as_success(tmp_path):
    from agent.connectors import excel_com_connector as com
    wb = MagicMock()
    out = tmp_path / "out.xlsx"
    assert com.save_workbook_as(wb, str(out), dry_run=False, allow_write=True, approval_token="DUMMY") is None
    wb.SaveAs.assert_called_once()
    args, kwargs = wb.SaveAs.call_args
    assert kwargs.get("FileFormat") == 51


def test_close_and_quit_never_raise():
    from agent.connectors import excel_com_connector as com
    wb = MagicMock()
    wb.Close.side_effect = RuntimeError("boom")
    com.close_workbook(wb)  # 예외 삼키기
    app = MagicMock()
    app.Quit.side_effect = RuntimeError("boom")
    com.quit_excel(app)  # 예외 삼키기


# ──────────────────────────────────────────────────────────────────
# 7) run_basic_poc
# ──────────────────────────────────────────────────────────────────
def _install_successful_mocks(monkeypatch, com, *, read_value="HELLO"):
    fake_app = MagicMock()
    fake_wb = MagicMock()
    fake_sheet = MagicMock()
    fake_app.Workbooks.Open.return_value = fake_wb
    fake_wb.Worksheets.return_value = fake_sheet

    ranges: dict = {}

    def _range(ref):
        if ref not in ranges:
            m = MagicMock()
            if ref == "A1":
                m.Value = read_value
            ranges[ref] = m
        return ranges[ref]

    fake_sheet.Range.side_effect = _range

    monkeypatch.setattr(
        com, "is_excel_available",
        lambda: {"ok": True, "platform": "win32",
                 "excel_available": True, "version": "16.0"},
    )
    monkeypatch.setattr(
        com, "open_excel_app", lambda visible=True: (fake_app, None)
    )
    return fake_app, fake_wb, fake_sheet, ranges


def test_run_basic_poc_non_windows(monkeypatch, tmp_path):
    from agent.connectors import excel_com_connector as com
    monkeypatch.setattr(
        com, "is_excel_available",
        lambda: {"ok": False, "platform": "linux",
                 "excel_available": False,
                 "error": com._err.EXCEL_COM_NOT_SUPPORTED},
    )
    out = com.run_basic_poc(str(tmp_path / "x.xlsx"), dry_run=False, approval_token="DUMMY", allow_write=True)
    assert out["ok"] is False
    assert out["error"] == com._err.EXCEL_COM_NOT_SUPPORTED
    assert out["dispatched"] is False
    assert out["quit"] is False


def test_run_basic_poc_success_flow(monkeypatch, tmp_path):
    from agent.connectors import excel_com_connector as com

    f = tmp_path / "sample.xlsx"
    f.write_bytes(b"dummy")
    fake_app, fake_wb, fake_sheet, ranges = _install_successful_mocks(
        monkeypatch, com,
    )

    out = com.run_basic_poc(str(f), sheet_name="Sheet1", dry_run=False, approval_token="DUMMY", allow_write=True)
    assert out["ok"] is True
    assert out["dispatched"] is True
    assert out["workbook_opened"] is True
    assert out["read_value"] == "HELLO"
    assert out["written_cell"] == "B2"
    assert out["written_value"] == "POC_OK"
    assert out["saved"] is True
    assert out["closed"] is True
    assert out["quit"] is True
    assert out["error"] is None

    fake_wb.Save.assert_called_once()
    fake_wb.Close.assert_called_once()
    fake_app.Quit.assert_called_once()
    # B2 에 실제로 쓰였는지 확인
    assert ranges["B2"].Value == "POC_OK"


def test_run_basic_poc_save_as_flow(monkeypatch, tmp_path):
    from agent.connectors import excel_com_connector as com

    f = tmp_path / "sample.xlsx"
    f.write_bytes(b"dummy")
    fake_app, fake_wb, *_ = _install_successful_mocks(monkeypatch, com)

    out_path = tmp_path / "out.xlsx"
    out = com.run_basic_poc(str(f), save_as=str(out_path), dry_run=False, approval_token="DUMMY", allow_write=True)
    assert out["ok"] is True
    fake_wb.SaveAs.assert_called_once()
    fake_wb.Save.assert_not_called()


def test_run_basic_poc_cleanup_on_failure(monkeypatch, tmp_path):
    """중간 단계가 실패해도 Close / Quit 가 호출되어야 한다."""
    from agent.connectors import excel_com_connector as com

    f = tmp_path / "sample.xlsx"
    f.write_bytes(b"dummy")
    fake_app, fake_wb, fake_sheet, _ = _install_successful_mocks(
        monkeypatch, com,
    )
    # read_cell 을 실패시키기 위해 Range 전체를 예외로 교체
    fake_sheet.Range.side_effect = RuntimeError("boom")

    out = com.run_basic_poc(str(f), dry_run=False, approval_token="DUMMY", allow_write=True)
    assert out["ok"] is False
    assert out["error"] == com._err.CELL_READ_FAILED
    # 정리 동작은 여전히 실행됨
    assert out["closed"] is True
    assert out["quit"] is True
    fake_wb.Close.assert_called_once()
    fake_app.Quit.assert_called_once()


# ──────────────────────────────────────────────────────────────────
# 8) 에러 코드 등록 확인
# ──────────────────────────────────────────────────────────────────
def test_com_error_codes_registered():
    from agent import errors
    for name in (
        "EXCEL_COM_NOT_SUPPORTED",
        "EXCEL_COM_DISPATCH_FAILED",
        "EXCEL_APP_NOT_FOUND",
        "WORKBOOK_OPEN_FAILED",
        "WORKBOOK_SAVE_FAILED",
        "CELL_READ_FAILED",
        "CELL_WRITE_FAILED",
    ):
        assert hasattr(errors, name), f"errors.{name} missing"
        assert getattr(errors, name) in errors.ALL_CODES, name
        assert errors.is_standard_code(getattr(errors, name))


# ──────────────────────────────────────────────────────────────────
# 9) P0 보안: dry_run 기본값 테스트
# ──────────────────────────────────────────────────────────────────
def test_run_basic_poc_dry_run_default_true(monkeypatch, tmp_path):
    """dry_run을 명시하지 않으면 기본값이 True 여야 한다."""
    from agent.connectors import excel_com_connector as com

    f = tmp_path / "sample.xlsx"
    f.write_bytes(b"dummy")
    fake_app, _, _, _ = _install_successful_mocks(monkeypatch, com)

    # dry_run 파라미터 미지정 - 기본값 True 적용되어야 함
    out = com.run_basic_poc(str(f))

    # dry_run=True 이므로 COM 앱이 실행되지 않아야 함
    assert out["ok"] is True
    assert out["dry_run"] is True
    assert out["planned_actions"]
    assert "dispatched" in out
    # dry_run=True 이므로 dispatched는 False (COM 객체를 생성하지 않음)
    assert out["dispatched"] is False


def test_write_cell_dry_run_default_true(monkeypatch, tmp_path):
    """write_cell dry_run 기본값이 True 여야 한다."""
    from agent.connectors import excel_com_connector as com

    f = tmp_path / "sample.xlsx"
    f.write_bytes(b"dummy")
    fake_app, fake_wb, fake_sheet, _ = _install_successful_mocks(monkeypatch, com)

    # dry_run 파라미터 미지정
    err = com.write_cell(fake_wb, "Sheet1", "A1", "test")

    # dry_run=True (기본)이므로 실제 쓰기가 수행되지 않음
    assert err is None
    fake_sheet.Range.assert_not_called()


# ──────────────────────────────────────────────────────────────────
# 10) P0 보안: approval_token 없는 write 차단
# ──────────────────────────────────────────────────────────────────
def test_write_cell_blocked_without_approval_token(monkeypatch, tmp_path):
    """approval_token 없이 dry_run=False + allow_write=True 시 차단."""
    from agent.connectors import excel_com_connector as com

    f = tmp_path / "sample.xlsx"
    f.write_bytes(b"dummy")
    fake_app, fake_wb, fake_sheet, _ = _install_successful_mocks(monkeypatch, com)

    # dry_run=False, allow_write=True이지만 approval_token=None
    err = com.write_cell(
        fake_wb, "Sheet1", "A1", "test",
        dry_run=False, allow_write=True, approval_token=None
    )

    assert err == com._err.WRITE_APPROVAL_REQUIRED
    fake_sheet.Range.assert_not_called()


def test_save_workbook_as_blocked_without_approval_token(monkeypatch, tmp_path):
    """save_workbook_as: approval_token 없이 차단."""
    from agent.connectors import excel_com_connector as com

    f = tmp_path / "sample.xlsx"
    f.write_bytes(b"dummy")
    fake_app, fake_wb, _, _ = _install_successful_mocks(monkeypatch, com)

    out_path = str(tmp_path / "out.xlsx")
    err = com.save_workbook_as(
        fake_wb, out_path,
        dry_run=False, allow_write=True, approval_token=None
    )

    assert err == com._err.WRITE_APPROVAL_REQUIRED
    fake_wb.SaveAs.assert_not_called()


# ──────────────────────────────────────────────────────────────────
# 11) P0 보안: allow_write=False 차단
# ──────────────────────────────────────────────────────────────────
def test_write_cell_blocked_allow_write_false(monkeypatch, tmp_path):
    """allow_write=False 시 차단."""
    from agent.connectors import excel_com_connector as com

    f = tmp_path / "sample.xlsx"
    f.write_bytes(b"dummy")
    fake_app, fake_wb, fake_sheet, _ = _install_successful_mocks(monkeypatch, com)

    err = com.write_cell(
        fake_wb, "Sheet1", "A1", "test",
        dry_run=False, allow_write=False, approval_token="dummy_token"
    )

    assert err == com._err.WRITE_NOT_ALLOWED
    fake_sheet.Range.assert_not_called()


# ──────────────────────────────────────────────────────────────────
# 12) P0 보안: approval_token 미노출
# ──────────────────────────────────────────────────────────────────
def test_write_cell_approval_token_not_exposed(monkeypatch, tmp_path, caplog):
    """approval_token 값이 로그나 결과에 노출되지 않음."""
    from agent.connectors import excel_com_connector as com
    import logging

    caplog.set_level(logging.DEBUG)
    f = tmp_path / "sample.xlsx"
    f.write_bytes(b"dummy")
    fake_app, fake_wb, fake_sheet, _ = _install_successful_mocks(monkeypatch, com)

    secret_token = "SECRET_APPROVAL_TOKEN_12345"

    err = com.write_cell(
        fake_wb, "Sheet1", "A1", "test",
        dry_run=False, allow_write=True, approval_token=secret_token
    )

    # approval_token이 전달되면 실제 쓰기 수행 (mock에서)
    # 로그나 에러 메시지에 token이 노출되지 않아야 함
    assert secret_token not in caplog.text
    assert secret_token not in str(err) if err else True


# ──────────────────────────────────────────────────────────────────
# 13) P0 보안: planned_actions 검증
# ──────────────────────────────────────────────────────────────────
def test_run_basic_poc_planned_actions(monkeypatch, tmp_path):
    """dry_run=True 시 planned_actions 구조 검증."""
    from agent.connectors import excel_com_connector as com

    f = tmp_path / "sample.xlsx"
    f.write_bytes(b"dummy")
    _install_successful_mocks(monkeypatch, com)

    out = com.run_basic_poc(str(f), dry_run=True)

    assert out["ok"] is True
    assert "planned_actions" in out
    assert isinstance(out["planned_actions"], list)
    assert len(out["planned_actions"]) >= 3

    # planned_actions 각 항목이 필요한 필드를 가져야 함
    assert out["planned_actions"][0]["action"] == "excel.open"
    assert out["planned_actions"][1]["action"] == "excel.read_cell"
    assert out["planned_actions"][2]["action"] == "excel.write_cell"
    # 민감값이 포함되지 않아야 함
    for action in out["planned_actions"]:
        assert "action" in action
        for key, val in action.items():
            if isinstance(val, str):
                assert "token" not in val.lower()
                assert "secret" not in val.lower()
                assert "password" not in val.lower()


# ──────────────────────────────────────────────────────────────────
# 14) read-only probe: get_active_excel_app (GetActiveObject)
# ──────────────────────────────────────────────────────────────────
def test_get_active_excel_app_non_windows(monkeypatch):
    """비 Windows에서는 not-supported 반환."""
    from agent.connectors import excel_com_connector as com
    monkeypatch.setattr(com, "_is_windows", lambda: False)
    app, err = com.get_active_excel_app()
    assert app is None
    assert err == com._err.EXCEL_COM_NOT_SUPPORTED


def test_get_active_excel_app_no_active_excel(monkeypatch):
    """Excel이 실행 중이지 않으면 app_not_found."""
    from agent.connectors import excel_com_connector as com

    fake_mod = MagicMock()
    fake_mod.GetObject.side_effect = RuntimeError("No active Excel")

    monkeypatch.setattr(com, "_is_windows", lambda: True)
    monkeypatch.setattr(com, "_try_import_win32com", lambda: (fake_mod, None))

    app, err = com.get_active_excel_app()
    assert app is None
    assert err == com._err.EXCEL_APP_NOT_FOUND


def test_get_active_excel_app_success(monkeypatch):
    """실행 중인 Excel을 성공적으로 연결."""
    from agent.connectors import excel_com_connector as com

    fake_app = MagicMock()
    fake_mod = MagicMock()
    fake_mod.GetObject.return_value = fake_app

    monkeypatch.setattr(com, "_is_windows", lambda: True)
    monkeypatch.setattr(com, "_try_import_win32com", lambda: (fake_mod, None))

    app, err = com.get_active_excel_app()
    assert app is fake_app
    assert err is None
    fake_mod.GetObject.assert_called_once()


# ──────────────────────────────────────────────────────────────────
# 15) read-only probe: probe_active_workbook_readonly
# ──────────────────────────────────────────────────────────────────
def test_probe_active_workbook_readonly_no_excel(monkeypatch):
    """Excel이 실행 중이지 않으면 NO_ACTIVE_EXCEL."""
    from agent.connectors import excel_com_connector as com

    fake_mod = MagicMock()
    fake_mod.GetObject.side_effect = RuntimeError("No Excel")
    monkeypatch.setattr(com, "_is_windows", lambda: True)
    monkeypatch.setattr(com, "_try_import_win32com", lambda: (fake_mod, None))

    result = com.probe_active_workbook_readonly()

    assert result["success"] is False
    assert result["excel_running"] is False
    assert result["error_code"] == com._err.EXCEL_APP_NOT_FOUND
    assert result["read_only"] is True


def test_probe_active_workbook_readonly_success(monkeypatch):
    """실행 중인 Workbook 정보를 성공적으로 조회."""
    from agent.connectors import excel_com_connector as com

    # Mock 구성
    fake_app = MagicMock()
    fake_wb = MagicMock()
    fake_sheet = MagicMock()
    fake_used_range = MagicMock()
    fake_rows = MagicMock()
    fake_columns = MagicMock()

    fake_app.Workbooks.Count = 1
    fake_app.ActiveWorkbook = fake_wb
    fake_wb.Name = "TestWorkbook.xlsx"
    fake_wb.Sheets.Count = 3
    fake_wb.ActiveSheet = fake_sheet
    fake_sheet.Name = "Sheet1"
    fake_wb.UsedRange = fake_used_range
    fake_used_range.Address.return_value = "A1:K52"
    fake_rows.Count = 52
    fake_columns.Count = 11
    fake_used_range.Rows = fake_rows
    fake_used_range.Columns = fake_columns

    # 샘플 셀 mock
    fake_cell_a1 = MagicMock()
    fake_cell_a1.Value = "Header"
    fake_sheet.Cells.return_value = fake_cell_a1

    fake_mod = MagicMock()
    fake_mod.GetObject.return_value = fake_app

    monkeypatch.setattr(com, "_is_windows", lambda: True)
    monkeypatch.setattr(com, "_try_import_win32com", lambda: (fake_mod, None))

    result = com.probe_active_workbook_readonly(max_sample_rows=10, max_sample_columns=10)

    assert result["success"] is True
    assert result["excel_running"] is True
    assert result["read_only"] is True
    assert result["workbook_count"] == 1
    assert result["active_workbook"]["name"] == "TestWorkbook.xlsx"
    assert result["active_workbook"]["sheet_count"] == 3
    assert result["active_workbook"]["active_sheet"] == "Sheet1"
    assert result["active_workbook"]["used_range"] == "A1:K52"
    assert result["active_workbook"]["rows"] == 52
    assert result["active_workbook"]["columns"] == 11


def test_probe_active_workbook_readonly_no_save_quit_close(monkeypatch):
    """probe는 Save/SaveAs/Close/Quit를 호출하지 않음."""
    from agent.connectors import excel_com_connector as com

    fake_app = MagicMock()
    fake_wb = MagicMock()
    fake_sheet = MagicMock()

    fake_app.Workbooks.Count = 1
    fake_app.ActiveWorkbook = fake_wb
    fake_wb.Name = "Test.xlsx"
    fake_wb.Sheets.Count = 1
    fake_wb.ActiveSheet = fake_sheet
    fake_sheet.Name = "Sheet1"
    fake_wb.UsedRange = MagicMock()
    fake_wb.UsedRange.Address.return_value = "A1:A1"
    fake_wb.UsedRange.Rows.Count = 1
    fake_wb.UsedRange.Columns.Count = 1

    fake_mod = MagicMock()
    fake_mod.GetObject.return_value = fake_app

    monkeypatch.setattr(com, "_is_windows", lambda: True)
    monkeypatch.setattr(com, "_try_import_win32com", lambda: (fake_mod, None))

    result = com.probe_active_workbook_readonly()

    assert result["success"] is True
    # Save/SaveAs/Close/Quit를 호출하지 않음
    fake_wb.Save.assert_not_called()
    fake_wb.SaveAs.assert_not_called()
    fake_wb.Close.assert_not_called()
    fake_app.Quit.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

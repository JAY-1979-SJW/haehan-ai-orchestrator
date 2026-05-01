"""Windows COM 기반 실제 Microsoft Excel 제어 (B안 1단계 POC).

목적
-----
로컬 Windows PC 에 설치된 Excel 데스크톱 앱을 ``win32com.client`` 로 실행시켜
- 파일 열기 / 셀 읽기 / 셀 쓰기 / 저장
가 실제로 동작하는지 증명한다. 서버 연동이나 action_registry 편입은 아직
없으며, openpyxl 기반 기존 파이프라인과는 완전히 분리되어 있다.

설계 원칙
---------
- ``win32com.client`` / ``pythoncom`` 은 **지연 import**. 비 Windows 환경에서
  모듈 import 자체가 실패하지 않도록 한다.
- 플랫폼/Dispatch 실패는 ``agent.errors`` 의 표준 코드로 반환.
- 모든 실패 경로에서 Excel 프로세스/Workbook 핸들을 ``finally`` 로 정리.
- 허용 경로 정책은 1·2단계 file_policy 와 독립적으로, 최소한 **절대경로만**
  받도록 가드.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Optional, Tuple

from .. import errors as _err

logger = logging.getLogger(__name__)

# .xlsx 저장용 FileFormat 코드 (Excel 내장 상수 xlOpenXMLWorkbook).
_XL_OPEN_XML_WORKBOOK = 51


# ── 보안: 승인/dry-run 게이트 ───────────────────────────────────────────
def _require_approval_for_write(
    action: str,
    approval_token: Optional[str],
    allow_write: bool,
) -> Optional[str]:
    """write 액션 승인 검증. 차단 시 에러 코드 반환, 통과 시 None."""
    if not allow_write:
        logger.warning("[EXCEL-WRITE-BLOCKED] action=%s allow_write=False", action)
        return _err.WRITE_NOT_ALLOWED
    if not approval_token or not isinstance(approval_token, str) or not approval_token.strip():
        logger.warning("[EXCEL-WRITE-BLOCKED] action=%s approval_token missing", action)
        return _err.WRITE_APPROVAL_REQUIRED
    return None


# ── 플랫폼 / 지연 import ────────────────────────────────────────────
def _is_windows() -> bool:
    return sys.platform.startswith("win")


def _try_import_win32com() -> Tuple[Optional[Any], Optional[str]]:
    """``win32com.client`` 지연 import.

    반환: (module_or_None, error_or_None).
    테스트에서 monkeypatch 로 상태를 시뮬레이션하기 위해 분리.
    """
    if not _is_windows():
        return None, _err.EXCEL_COM_NOT_SUPPORTED
    try:
        import win32com.client as _win32com  # type: ignore
        return _win32com, None
    except ImportError:
        return None, _err.EXCEL_COM_DISPATCH_FAILED


# ── 가용성 점검 ─────────────────────────────────────────────────────
def is_excel_available() -> dict:
    """플랫폼 / pywin32 / Excel 설치 세 층위를 순차적으로 진단.

    반환 예 (성공):
      {"ok": True, "platform": "win32", "excel_available": True, "version": "16.0"}

    반환 예 (실패):
      {"ok": False, "platform": "...", "excel_available": False,
       "error": "excel_com_not_supported" | ...}
    """
    platform_name = sys.platform
    if not _is_windows():
        return {
            "ok": False,
            "platform": platform_name,
            "excel_available": False,
            "error": _err.EXCEL_COM_NOT_SUPPORTED,
        }

    win32com_mod, err = _try_import_win32com()
    if err or win32com_mod is None:
        return {
            "ok": False,
            "platform": platform_name,
            "excel_available": False,
            "error": err or _err.EXCEL_COM_DISPATCH_FAILED,
        }

    try:
        app = win32com_mod.Dispatch("Excel.Application")
    except Exception as e:  # noqa: BLE001 - COM 예외 유형 다양
        logger.info("Excel.Application Dispatch 실패: %s", type(e).__name__)
        return {
            "ok": False,
            "platform": platform_name,
            "excel_available": False,
            "error": _err.EXCEL_APP_NOT_FOUND,
            "detail": type(e).__name__,
        }

    version = ""
    try:
        version = str(getattr(app, "Version", ""))
    except Exception:  # noqa: BLE001
        version = ""
    try:
        app.Quit()
    except Exception:  # noqa: BLE001
        pass

    return {
        "ok": True,
        "platform": platform_name,
        "excel_available": True,
        "version": version,
    }


# ── 핸들 관리 ──────────────────────────────────────────────────────
def open_excel_app(visible: bool = True) -> Tuple[Optional[Any], Optional[str]]:
    """Excel Application COM 객체를 반환.

    - DisplayAlerts=False (대화상자 억제).
    - Visible 은 POC 기본 True.
    """
    win32com_mod, err = _try_import_win32com()
    if err or win32com_mod is None:
        return None, err or _err.EXCEL_COM_DISPATCH_FAILED
    try:
        app = win32com_mod.Dispatch("Excel.Application")
    except Exception as e:  # noqa: BLE001
        logger.info("open_excel_app Dispatch 실패: %s", type(e).__name__)
        return None, _err.EXCEL_APP_NOT_FOUND

    try:
        app.DisplayAlerts = False
    except Exception:  # noqa: BLE001
        pass
    try:
        app.Visible = bool(visible)
    except Exception:  # noqa: BLE001
        pass
    return app, None


def open_workbook(
    app: Any, file_path: str, read_only: bool = False,
) -> Tuple[Optional[Any], Optional[str]]:
    """workbook 핸들 반환. 절대경로만 허용한다."""
    if not isinstance(file_path, str) or not file_path.strip():
        return None, _err.FILE_PATH_REQUIRED
    try:
        p = Path(file_path).expanduser()
    except (OSError, ValueError):
        return None, _err.FILE_NOT_ALLOWED
    if not p.is_absolute():
        return None, _err.FILE_NOT_ALLOWED
    if not p.exists() or not p.is_file():
        return None, _err.FILE_NOT_FOUND
    try:
        wb = app.Workbooks.Open(str(p), ReadOnly=bool(read_only))
    except Exception as e:  # noqa: BLE001
        logger.info("Workbooks.Open 실패: %s", type(e).__name__)
        return None, _err.WORKBOOK_OPEN_FAILED
    return wb, None


# ── 시트/셀 I/O ────────────────────────────────────────────────────
def _get_sheet(workbook: Any, sheet_name: str) -> Tuple[Optional[Any], Optional[str]]:
    if not isinstance(sheet_name, str) or not sheet_name:
        return None, _err.SHEET_NOT_FOUND
    try:
        sheet = workbook.Worksheets(sheet_name)
    except Exception:  # noqa: BLE001
        return None, _err.SHEET_NOT_FOUND
    if sheet is None:
        return None, _err.SHEET_NOT_FOUND
    return sheet, None


def read_cell(
    workbook: Any, sheet_name: str, cell_ref: str,
) -> Tuple[Any, Optional[str]]:
    sheet, err = _get_sheet(workbook, sheet_name)
    if err:
        return None, err
    try:
        value = sheet.Range(cell_ref).Value
    except Exception as e:  # noqa: BLE001
        logger.info("read_cell 실패 (%s!%s): %s", sheet_name, cell_ref, type(e).__name__)
        return None, _err.CELL_READ_FAILED
    return value, None


def write_cell(
    workbook: Any,
    sheet_name: str,
    cell_ref: str,
    value: Any,
    *,
    approval_token: Optional[str] = None,
    dry_run: bool = True,
    allow_write: bool = False,
) -> Optional[str]:
    """셀에 값을 씀. 승인/dry-run 게이트 포함."""
    if dry_run:
        logger.info("[EXCEL-DRY-RUN] write_cell %s!%s would_write=True", sheet_name, cell_ref)
        return None
    approval_err = _require_approval_for_write("excel.write_cell", approval_token, allow_write)
    if approval_err:
        return approval_err
    sheet, err = _get_sheet(workbook, sheet_name)
    if err:
        return err
    try:
        sheet.Range(cell_ref).Value = value
    except Exception as e:  # noqa: BLE001
        logger.info("write_cell 실패 (%s!%s): %s", sheet_name, cell_ref, type(e).__name__)
        return _err.CELL_WRITE_FAILED
    return None


# ── 저장 / 종료 ────────────────────────────────────────────────────
def save_workbook(
    workbook: Any,
    *,
    approval_token: Optional[str] = None,
    dry_run: bool = True,
    allow_write: bool = False,
) -> Optional[str]:
    """현재 경로로 저장. 승인/dry-run 게이트 포함."""
    if dry_run:
        logger.info("[EXCEL-DRY-RUN] save_workbook would_write=True")
        return None
    approval_err = _require_approval_for_write("excel.save_workbook", approval_token, allow_write)
    if approval_err:
        return approval_err
    try:
        workbook.Save()
    except Exception as e:  # noqa: BLE001
        logger.info("Save 실패: %s", type(e).__name__)
        return _err.WORKBOOK_SAVE_FAILED
    return None


def save_workbook_as(
    workbook: Any,
    output_path: str,
    *,
    approval_token: Optional[str] = None,
    dry_run: bool = True,
    allow_write: bool = False,
) -> Optional[str]:
    """별도 경로로 저장 (권장 경로). 절대경로만 허용, 승인/dry-run 게이트 포함."""
    if not isinstance(output_path, str) or not output_path.strip():
        return _err.OUTPUT_PATH_REQUIRED
    try:
        p = Path(output_path).expanduser()
    except (OSError, ValueError):
        return _err.OUTPUT_PATH_NOT_ALLOWED
    if not p.is_absolute():
        return _err.OUTPUT_PATH_NOT_ALLOWED
    if dry_run:
        logger.info("[EXCEL-DRY-RUN] save_workbook_as path=%s would_write=True", output_path)
        return None
    approval_err = _require_approval_for_write("excel.save_workbook_as", approval_token, allow_write)
    if approval_err:
        return approval_err
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return _err.OUTPUT_PATH_NOT_ALLOWED
    try:
        workbook.SaveAs(str(p), FileFormat=_XL_OPEN_XML_WORKBOOK)
    except Exception as e:  # noqa: BLE001
        logger.info("SaveAs 실패: %s", type(e).__name__)
        return _err.WORKBOOK_SAVE_FAILED
    return None


def close_workbook(workbook: Any, save_changes: bool = False) -> None:
    try:
        workbook.Close(SaveChanges=bool(save_changes))
    except Exception as e:  # noqa: BLE001
        logger.info("Close 실패 (정리 단계): %s", type(e).__name__)


def quit_excel(app: Any) -> None:
    try:
        app.Quit()
    except Exception as e:  # noqa: BLE001
        logger.info("Quit 실패 (정리 단계): %s", type(e).__name__)


# ── 통합 POC ───────────────────────────────────────────────────────
def run_basic_poc(
    file_path: str,
    sheet_name: str = "Sheet1",
    *,
    visible: bool = True,
    save_as: Optional[str] = None,
    read_cell_ref: str = "A1",
    write_cell_ref: str = "B2",
    write_value: str = "POC_OK",
    dry_run: bool = True,
    approval_token: Optional[str] = None,
    allow_write: bool = False,
) -> dict:
    """Excel 실행 → 열기 → 읽기 → 쓰기 → 저장 → 종료 를 한 번에 수행.

    - dry_run=True (기본): COM 객체 미생성, planned_actions만 반환
    - approval_token 필수 (쓰기용)
    - allow_write=True만 실제 쓰기 허용

    모든 단계의 진행 상황을 ``result`` dict 에 순차 기록해 실패 지점을
    분리 가능한 진단 로그로 반환한다.
    """
    result: dict = {
        "ok": False,
        "file_path": file_path,
        "sheet_name": sheet_name,
        "excel_visible": bool(visible),
        "save_as": save_as,
        "dry_run": bool(dry_run),
        "allow_write": bool(allow_write),
        "planned_actions": [],
        "dispatched": False,
        "workbook_opened": False,
        "read_cell": read_cell_ref,
        "read_value": None,
        "written_cell": write_cell_ref,
        "written_value": None,
        "saved": False,
        "closed": False,
        "quit": False,
        "error": None,
    }

    if dry_run:
        result["planned_actions"] = [
            {"action": "excel.open", "file_path": file_path},
            {"action": "excel.read_cell", "ref": read_cell_ref, "requires_approval": False},
            {"action": "excel.write_cell", "ref": write_cell_ref, "requires_approval": True},
            {"action": "excel.save_as" if save_as else "excel.save", "requires_approval": True},
        ]
        logger.info("[EXCEL-DRY-RUN] planned_actions=%d", len(result["planned_actions"]))
        result["ok"] = True
        return result

    avail = is_excel_available()
    if not avail.get("ok"):
        result["error"] = avail.get("error") or _err.EXCEL_COM_NOT_SUPPORTED
        return result

    app, err = open_excel_app(visible=visible)
    if err or app is None:
        result["error"] = err or _err.EXCEL_APP_NOT_FOUND
        return result
    result["dispatched"] = True

    wb = None
    try:
        wb, err = open_workbook(app, file_path, read_only=False)
        if err or wb is None:
            result["error"] = err or _err.WORKBOOK_OPEN_FAILED
            return result
        result["workbook_opened"] = True

        value, err = read_cell(wb, sheet_name, read_cell_ref)
        if err:
            result["error"] = err
            return result
        result["read_value"] = value

        err = write_cell(
            wb, sheet_name, write_cell_ref, write_value,
            approval_token=approval_token, dry_run=False, allow_write=allow_write,
        )
        if err:
            result["error"] = err
            return result
        result["written_value"] = write_value

        if save_as:
            err = save_workbook_as(
                wb, save_as,
                approval_token=approval_token, dry_run=False, allow_write=allow_write,
            )
        else:
            err = save_workbook(
                wb,
                approval_token=approval_token, dry_run=False, allow_write=allow_write,
            )
        if err:
            result["error"] = err
            return result
        result["saved"] = True
        result["ok"] = True
        return result
    finally:
        if wb is not None:
            close_workbook(wb, save_changes=False)
            result["closed"] = True
        quit_excel(app)
        result["quit"] = True


# ── read-only probe (실행 중인 Excel 감지) ──────────────────────────────
def get_active_excel_app() -> Tuple[Optional[Any], Optional[str]]:
    """실행 중인 Excel Application을 GetActiveObject로 반환.

    새로 실행하지 않고, 이미 열려 있는 Excel만 연결한다.
    Excel이 실행 중이지 않으면 NO_ACTIVE_EXCEL 반환.
    """
    win32com_mod, err = _try_import_win32com()
    if err or win32com_mod is None:
        return None, err or _err.EXCEL_COM_DISPATCH_FAILED

    try:
        app = win32com_mod.GetObject(None, "Excel.Application")
        return app, None
    except Exception as e:  # noqa: BLE001 - COM 예외 다양
        logger.debug("GetActiveObject(Excel.Application) 실패: %s", type(e).__name__)
        return None, _err.EXCEL_APP_NOT_FOUND


def probe_active_workbook_readonly(
    max_sample_rows: int = 10,
    max_sample_columns: int = 10,
    include_formulas: bool = False,
) -> dict:
    """실행 중인 Excel의 Workbook 정보를 read-only로 조회.

    Args:
        max_sample_rows: 샘플 셀 읽기 최대 행 수
        max_sample_columns: 샘플 셀 읽기 최대 열 수
        include_formulas: 수식 포함 여부 (False 기본, 값만 읽음)

    Returns:
        {
            "success": bool,
            "excel_running": bool,
            "error_code": str | None,
            "workbook_count": int | None,
            "active_workbook": {
                "name": str,
                "sheet_count": int,
                "active_sheet": str,
                "used_range": str,  # e.g., "A1:K52"
                "rows": int,
                "columns": int,
            } | None,
            "sample_cells": [{"row": int, "column": int, "address": str, "value": Any}],
            "read_only": True,
        }
    """
    result: dict = {
        "success": False,
        "excel_running": False,
        "error_code": None,
        "workbook_count": None,
        "active_workbook": None,
        "sample_cells": [],
        "read_only": True,
    }

    app, err = get_active_excel_app()
    if err or app is None:
        result["error_code"] = _err.EXCEL_APP_NOT_FOUND
        result["excel_running"] = False
        return result

    try:
        result["excel_running"] = True

        # Workbook 정보
        try:
            workbooks = app.Workbooks
            wb_count = workbooks.Count
            result["workbook_count"] = wb_count
        except Exception:  # noqa: BLE001
            result["error_code"] = _err.EXCEL_APP_NOT_FOUND
            return result

        # 활성 Workbook
        try:
            wb = app.ActiveWorkbook
            if wb is None:
                result["error_code"] = "NO_ACTIVE_WORKBOOK"
                return result
        except Exception:  # noqa: BLE001
            result["error_code"] = "NO_ACTIVE_WORKBOOK"
            return result

        wb_info: dict = {}
        try:
            wb_info["name"] = str(wb.Name)
        except Exception:  # noqa: BLE001
            wb_info["name"] = "(unknown)"

        # 시트 정보
        try:
            sheets = wb.Sheets
            sheet_count = sheets.Count
            wb_info["sheet_count"] = sheet_count
        except Exception:  # noqa: BLE001
            wb_info["sheet_count"] = 0

        try:
            active_sheet = wb.ActiveSheet
            wb_info["active_sheet"] = str(active_sheet.Name) if active_sheet else "(unknown)"
        except Exception:  # noqa: BLE001
            wb_info["active_sheet"] = "(unknown)"
            active_sheet = None

        # UsedRange (Sheet.UsedRange 사용, Workbook.UsedRange는 없음)
        try:
            if active_sheet is not None:
                used_range = active_sheet.UsedRange
                # Note: Address는 프로퍼티이지 메서드가 아님 (Address(external=False) 사용 불가)
                wb_info["used_range"] = str(used_range.Address)
                wb_info["rows"] = used_range.Rows.Count
                wb_info["columns"] = used_range.Columns.Count
            else:
                wb_info["used_range"] = "(unknown)"
                wb_info["rows"] = 0
                wb_info["columns"] = 0
        except Exception:  # noqa: BLE001
            wb_info["used_range"] = "(unknown)"
            wb_info["rows"] = 0
            wb_info["columns"] = 0

        # 샘플 셀 읽기 (상위 max_sample_rows x max_sample_columns)
        sample_cells: list = []
        try:
            if wb_info.get("rows", 0) > 0 and wb_info.get("columns", 0) > 0:
                ws = wb.ActiveSheet
                max_r = min(max_sample_rows, wb_info.get("rows", 0))
                max_c = min(max_sample_columns, wb_info.get("columns", 0))

                for row in range(1, max_r + 1):
                    for col in range(1, max_c + 1):
                        try:
                            cell = ws.Cells(row, col)
                            value = cell.Value
                            if include_formulas and value is not None:
                                try:
                                    formula = cell.Formula
                                    if formula and str(formula).startswith("="):
                                        value = {"value": value, "formula": str(formula)}
                                except Exception:  # noqa: BLE001
                                    pass

                            # 빈 셀은 제외
                            if value is not None:
                                sample_cells.append({
                                    "row": row,
                                    "column": col,
                                    "address": f"{_col_letter(col)}{row}",
                                    "value": value,
                                })
                        except Exception:  # noqa: BLE001
                            pass
        except Exception:  # noqa: BLE001
            pass

        result["active_workbook"] = wb_info
        result["sample_cells"] = sample_cells
        result["success"] = True
        return result

    except Exception as e:  # noqa: BLE001
        logger.error("probe_active_workbook_readonly 실패: %s", type(e).__name__)
        result["error_code"] = "PROBE_FAILED"
        return result


def _col_letter(col_num: int) -> str:
    """열 번호를 알파벳으로 변환 (1 → A, 27 → AA)."""
    result = ""
    while col_num > 0:
        col_num -= 1
        result = chr(65 + (col_num % 26)) + result
        col_num //= 26
    return result


# ── 헤더 자동 인식 ───────────────────────────────────────────────────
# ── Wrapper: 하위 호환성 (agent/excel 모듈 사용) ───────────────────────────────
def detect_header_row_from_active_sheet(
    sheet: Any,
    max_scan_rows: int = 20,
    max_columns: int = 50,
) -> Tuple[Optional[int], Optional[str]]:
    """(Deprecated: agent/excel/header_detector 사용) 헤더 행 자동 인식."""
    from agent import excel as excel_mod
    return excel_mod.detect_header_row(sheet, max_scan_rows, max_columns)


def map_headers_from_row(
    sheet: Any,
    header_row: int,
    max_columns: int = 50,
) -> Tuple[Optional[dict], Optional[str]]:
    """(Deprecated: agent/excel/header_detector 사용) 헤더 매핑."""
    from agent import excel as excel_mod
    return excel_mod.map_headers(sheet, header_row, max_columns)


def update_cell_by_header_and_row_copy(
    row_match_header: str,
    row_match_value: Any,
    target_header: str,
    new_value: Any,
    output_path: Optional[str] = None,
    *,
    approval_token: Optional[str] = None,
    allow_write: bool = False,
) -> dict:
    """(Refactored: agent.task_executor 경유) 헤더명 기준 셀 수정 + 복사본 저장.

    이 함수는 호환성만 유지하며, 실제 구현은 agent/excel 모듈과
    agent.task_executor 핸들러로 이동했다.
    """
    from agent import excel as excel_mod

    result = excel_mod.build_update_result()

    # 승인 검증
    approval_err = _require_approval_for_write(
        "excel.update_cell_by_header_copy", approval_token, allow_write,
    )
    if approval_err:
        result["error"] = approval_err
        return result

    # GetActiveObject로 Excel 연결
    app, err = get_active_excel_app()
    if err or app is None:
        result["error"] = _err.EXCEL_APP_NOT_FOUND
        return result

    try:
        # ActiveWorkbook 확인
        try:
            wb = app.ActiveWorkbook
            if wb is None:
                result["error"] = "NO_ACTIVE_WORKBOOK"
                return result
        except Exception:  # noqa: BLE001
            result["error"] = "NO_ACTIVE_WORKBOOK"
            return result

        # ActiveSheet 확인
        try:
            sheet = wb.ActiveSheet
            if sheet is None:
                result["error"] = _err.SHEET_NOT_FOUND
                return result
            result["sheet"] = str(sheet.Name)
        except Exception:  # noqa: BLE001
            result["error"] = _err.SHEET_NOT_FOUND
            return result

        # 헤더 행 자동 인식
        header_row, err = excel_mod.detect_header_row(sheet)
        if err or header_row is None:
            result["error"] = err or "HEADER_DETECTION_FAILED"
            return result
        result["header_row"] = header_row

        # 헤더 매핑
        headers, err = excel_mod.map_headers(sheet, header_row)
        if err or headers is None:
            result["error"] = err or "HEADER_MAPPING_FAILED"
            return result

        # row_match_header 열 번호 확인
        if row_match_header not in headers:
            result["error"] = f"HEADER_NOT_FOUND: {row_match_header}"
            return result
        match_col = headers[row_match_header]

        # target_header 열 번호 확인
        if target_header not in headers:
            result["error"] = f"HEADER_NOT_FOUND: {target_header}"
            return result
        target_col = headers[target_header]

        # row_match_value가 포함된 행 찾기
        matched_row, err = excel_mod.find_row_by_header_value(
            sheet, header_row, match_col, row_match_value,
        )
        if err or matched_row is None:
            result["error"] = err or "ROW_NOT_FOUND"
            return result
        result["matched_row"] = matched_row

        # 셀 수정
        cell_info, err = excel_mod.update_cell(sheet, matched_row, target_col, new_value)
        if err or cell_info is None:
            result["error"] = err or "CELL_WRITE_FAILED"
            return result

        result["target_cell"] = cell_info.get("cell_address")
        result["old_value"] = cell_info.get("old_value")
        result["new_value"] = cell_info.get("new_value")

        # 복사본 저장
        safe_path, err = excel_mod.build_safe_copy_path(wb, output_path)
        if err or safe_path is None:
            result["error"] = err or "COPY_PATH_FAILED"
            return result

        err = excel_mod.save_copy(wb, safe_path)
        if err:
            result["error"] = err
            return result

        result["output_file"] = f"...{safe_path[-30:]}"
        result["success"] = True
        return result

    except Exception as e:  # noqa: BLE001
        logger.error("update_cell_by_header_and_row_copy 실패: %s", type(e).__name__)
        result["error"] = "UPDATE_FAILED"
        return result


def insert_row_by_header_copy(
    row_match_header: str,
    row_match_value: Any,
    position: str = "below",
    values: Optional[dict] = None,
    output_path: Optional[str] = None,
    *,
    approval_token: Optional[str] = None,
    allow_write: bool = False,
) -> dict:
    """Thin wrapper for agent.excel.workflows.insert_row_by_header_copy."""
    from agent import excel as excel_mod

    return excel_mod.workflows.insert_row_by_header_copy(
        row_match_header=row_match_header,
        row_match_value=row_match_value,
        position=position,
        values=values,
        output_path=output_path,
        approval_token=approval_token,
        allow_write=allow_write,
    )


def insert_column_by_header_copy(
    anchor_header: str,
    new_header: str,
    position: str = "right",
    output_path: Optional[str] = None,
    *,
    approval_token: Optional[str] = None,
    allow_write: bool = False,
) -> dict:
    """Thin wrapper for agent.excel.workflows.insert_column_by_header_copy."""
    from agent import excel as excel_mod

    return excel_mod.workflows.insert_column_by_header_copy(
        anchor_header=anchor_header,
        new_header=new_header,
        position=position,
        output_path=output_path,
        approval_token=approval_token,
        allow_write=allow_write,
    )


def write_formula_by_header_copy(
    target_header: str,
    formula: str,
    start_row: Optional[int] = None,
    end_row: Optional[int] = None,
    output_path: Optional[str] = None,
    *,
    approval_token: Optional[str] = None,
    allow_write: bool = False,
) -> dict:
    """Thin wrapper for agent.excel.workflows.write_formula_by_header_copy."""
    from agent import excel as excel_mod

    return excel_mod.workflows.write_formula_by_header_copy(
        target_header=target_header,
        formula=formula,
        start_row=start_row,
        end_row=end_row,
        output_path=output_path,
        approval_token=approval_token,
        allow_write=allow_write,
    )


def analyze_active_workbook() -> dict:
    """Thin wrapper for agent.excel.analysis_workflows.analyze_active_workbook."""
    from agent import excel as excel_mod

    return excel_mod.analysis_workflows.analyze_active_workbook()


def analyze_active_sheet_structure() -> dict:
    """Thin wrapper for agent.excel.analysis_workflows.analyze_active_sheet_structure."""
    from agent import excel as excel_mod

    return excel_mod.analysis_workflows.analyze_active_sheet_structure()


def plan_changes(operations: list) -> dict:
    """Thin wrapper for agent.excel.planning_workflows.plan_changes."""
    from agent import excel as excel_mod

    return excel_mod.planning_workflows.plan_changes(operations=operations)


def apply_change_plan_copy(
    plan: dict,
    output_path: str,
    approval_token: str,
) -> dict:
    """Thin wrapper for agent.excel.execution_workflows.apply_change_plan_copy."""
    from agent import excel as excel_mod

    return excel_mod.execution_workflows.apply_change_plan_copy(
        plan=plan,
        output_path=output_path,
        approval_token=approval_token,
    )


def validate_active_workbook() -> dict:
    """Thin wrapper for agent.excel.validation_workflows.validate_active_workbook."""
    from agent import excel as excel_mod

    return excel_mod.validation_workflows.validate_active_workbook()


def validate_change_result(
    before_state: dict,
    change_log: dict,
) -> dict:
    """Thin wrapper for agent.excel.validation_workflows.validate_change_result."""
    from agent import excel as excel_mod

    return excel_mod.validation_workflows.validate_change_result(
        before_state=before_state,
        change_log=change_log,
    )


def create_review_summary_sheet_copy(
    output_path: str,
    approval_token: str,
    change_log: dict = None,
    validation_report: dict = None,
) -> dict:
    """Thin wrapper for agent.excel.report_workflows.create_review_summary_sheet_copy."""
    from agent import excel as excel_mod

    return excel_mod.report_workflows.create_review_summary_sheet_copy(
        output_path=output_path,
        approval_token=approval_token,
        change_log=change_log,
        validation_report=validation_report,
    )


def export_pdf_copy(
    output_path: str,
    approval_token: str,
    export_type: str = "active_sheet",
    sheet_names: list = None,
) -> dict:
    """Thin wrapper for agent.excel.pdf_workflows.export_pdf_copy."""
    from agent import excel as excel_mod

    sheet_names = sheet_names or []
    return excel_mod.pdf_workflows.export_pdf_copy(
        output_path=output_path,
        approval_token=approval_token,
        export_type=export_type,
        sheet_names=sheet_names,
    )


def review_estimate_copy(
    output_path: str,
    approval_token: str,
    header_row: int = None,
) -> dict:
    """Thin wrapper for agent.excel.packs.estimate_workflows.review_estimate_copy."""
    from agent import excel as excel_mod

    return excel_mod.packs.estimate_workflows.review_estimate_copy(
        output_path=output_path,
        approval_token=approval_token,
        header_row=header_row,
    )


def review_settlement_copy(
    output_path: str,
    approval_token: str,
    header_row: int = None,
    difference_threshold: float = 0.05,
) -> dict:
    """Thin wrapper for agent.excel.packs.settlement_workflows.review_settlement_copy."""
    from agent import excel as excel_mod

    return excel_mod.packs.settlement_workflows.review_settlement_copy(
        output_path=output_path,
        approval_token=approval_token,
        header_row=header_row,
        difference_threshold=difference_threshold,
    )


def check_material_prices_copy(
    output_path: str,
    approval_token: str,
    material_col: int = None,
    unit_price_col: int = None,
    outlier_threshold: float = 2.0,
) -> dict:
    """Thin wrapper for agent.excel.packs.price_check_workflows.check_material_prices_copy."""
    from agent import excel as excel_mod

    return excel_mod.packs.price_check_workflows.check_material_prices_copy(
        output_path=output_path,
        approval_token=approval_token,
        material_col=material_col,
        unit_price_col=unit_price_col,
        outlier_threshold=outlier_threshold,
    )


def validate_data_quality() -> dict:
    """Thin wrapper for agent.excel.analysis_workflows.validate_data_quality."""
    from agent import excel as excel_mod

    return excel_mod.analysis_workflows.validate_data_quality()


def validate_formulas() -> dict:
    """Thin wrapper for agent.excel.analysis_workflows.validate_formulas."""
    from agent import excel as excel_mod

    return excel_mod.analysis_workflows.validate_formulas()


def generate_analysis_report() -> dict:
    """Thin wrapper for agent.excel.analysis_workflows.generate_analysis_report."""
    from agent import excel as excel_mod

    return excel_mod.analysis_workflows.generate_analysis_report()


__all__ = [
    "is_excel_available",
    "open_excel_app",
    "open_workbook",
    "read_cell",
    "write_cell",
    "save_workbook",
    "save_workbook_as",
    "close_workbook",
    "quit_excel",
    "run_basic_poc",
    "get_active_excel_app",
    "probe_active_workbook_readonly",
    # 호환성 wrapper (실제 구현은 agent/excel 모듈)
    "detect_header_row_from_active_sheet",
    "map_headers_from_row",
    "update_cell_by_header_and_row_copy",
    "insert_row_by_header_copy",
    "insert_column_by_header_copy",
    "write_formula_by_header_copy",
    "analyze_active_workbook",
    "analyze_active_sheet_structure",
    "plan_changes",
    "apply_change_plan_copy",
    "validate_active_workbook",
    "validate_change_result",
    "create_review_summary_sheet_copy",
    "export_pdf_copy",
    "review_estimate_copy",
    "review_settlement_copy",
    "check_material_prices_copy",
    "validate_data_quality",
    "validate_formulas",
    "generate_analysis_report",
]

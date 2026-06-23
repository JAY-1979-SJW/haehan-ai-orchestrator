"""Excel COM 공통 유틸리티.

- COM 앱 초기화 / 정리
- 인쇄영역 파싱
- 행높이·셀 테두리 추출
- A4 가용 높이 계산
"""

import contextlib
from pathlib import Path

import win32com.client as win32
from openpyxl.utils import get_column_letter

from .constants import (
    A4_HEIGHT_PT,
    BORDER_BOTTOM,
    BORDER_LEFT,
    BORDER_RIGHT,
    BORDER_TOP,
    DATA_COLUMN_COUNT,
    PRINT_AREA_RE,
    PT_PER_INCH,
    XL_CONTINUOUS,
)

# ── COM 초기화 ────────────────────────────────────────────────────────────────


def open_excel(file_path: str) -> tuple:
    """숨김 Excel 앱과 워크시트를 열어 반환.

    Returns:
        (xl_app, workbook, worksheet, page_setup)
    """
    xl = win32.Dispatch("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    wb = xl.Workbooks.Open(str(Path(file_path).resolve()))
    ws = wb.Sheets(1)
    return xl, wb, ws, ws.PageSetup


@contextlib.contextmanager
def excel_session(file_path: str):
    """with 블록 안에서 Excel COM 세션을 안전하게 사용.

    Usage:
        with excel_session(path) as (wb, ws, ps):
            ...
    """
    try:
        xl = win32.GetActiveObject("Excel.Application")
    except Exception:
        xl = win32.Dispatch("Excel.Application")
    try:
        xl.Visible = False
        xl.DisplayAlerts = False
    except Exception:
        pass
    wb = None
    try:
        wb = xl.Workbooks.Open(str(Path(file_path).resolve()))
        ws = wb.Sheets(1)
        yield wb, ws, ws.PageSetup
    finally:
        try:
            if wb is not None:
                wb.Close(False)
        except Exception:
            pass
        try:
            xl.Quit()
        except Exception:
            pass


# ── 계산 헬퍼 ─────────────────────────────────────────────────────────────────


def available_height(ps) -> float:
    """A4 가용 높이(pt) = A4 전체 - 상하여백 - 머리글/바닥글."""
    return A4_HEIGHT_PT - ps.TopMargin - ps.BottomMargin - ps.HeaderMargin - ps.FooterMargin


def parse_last_row(ps, fallback: int = 30) -> int:
    """PageSetup.PrintArea 문자열에서 마지막 행 번호를 파싱."""
    m = PRINT_AREA_RE.search(ps.PrintArea or "")
    return int(m.group(1)) if m else fallback


# ── 데이터 추출 ───────────────────────────────────────────────────────────────


def row_heights(ws, last_row: int) -> dict[int, dict]:
    """1~last_row 행의 높이와 숨김 여부를 반환."""
    return {
        r: {
            "height": round(ws.Rows(r).RowHeight, 1),
            "hidden": bool(ws.Rows(r).Hidden),
        }
        for r in range(1, last_row + 1)
    }


def visible_height_sum(rows: dict) -> float:
    """숨김 아닌 행의 높이 합계."""
    return sum(info["height"] for info in rows.values() if not info["hidden"])


def cell_borders(cell) -> dict[str, bool]:
    """셀의 상하좌우 테두리 유무를 반환."""
    return {
        "T": cell.Borders(BORDER_TOP).LineStyle == XL_CONTINUOUS,
        "B": cell.Borders(BORDER_BOTTOM).LineStyle == XL_CONTINUOUS,
        "L": cell.Borders(BORDER_LEFT).LineStyle == XL_CONTINUOUS,
        "R": cell.Borders(BORDER_RIGHT).LineStyle == XL_CONTINUOUS,
    }


def column_widths(ws, count: int = DATA_COLUMN_COUNT) -> dict[str, float]:
    """A~(count)열 너비를 반환."""
    return {get_column_letter(c): round(ws.Columns(c).ColumnWidth, 2) for c in range(1, count + 1)}


def page_setup_info(ps) -> dict:
    """페이지 설정 값을 딕셔너리로 반환."""
    return {
        "paper": ps.PaperSize,
        "orientation": "portrait" if ps.Orientation == 1 else "landscape",
        "fitW": ps.FitToPagesWide,
        "fitH": ps.FitToPagesTall,
        "zoom": ps.Zoom,
        "margin_top": round(ps.TopMargin / PT_PER_INCH, 3),
        "margin_bot": round(ps.BottomMargin / PT_PER_INCH, 3),
        "margin_left": round(ps.LeftMargin / PT_PER_INCH, 3),
        "margin_right": round(ps.RightMargin / PT_PER_INCH, 3),
        "print_area": ps.PrintArea,
    }

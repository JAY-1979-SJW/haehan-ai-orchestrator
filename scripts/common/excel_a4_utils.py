"""Excel COM 공통 유틸리티 — A4 서식 점검용.

- COM 앱 초기화 / 정리
- 인쇄영역 파싱
- 행높이·셀 테두리 추출
- A4 가용 높이 계산

이식 출처: "42. excel-ai-agent" 저장소의 excel_ai_agent/excel_utils.py.
scripts/common/excel_a4_constants.py 와 같은 이유(docs/defect_index.json #32)로
2026-09-29 이식. 로직은 원본과 동일(excel_session의 안전한 COM 인스턴스 분리 방식 포함).
단위 확인(WebFetch, 2026-09-29): PageSetup.TopMargin 등은 포인트 단위이고
Application.InchesToPoints(1) = 72 로 나누면 인치가 된다
(learn.microsoft.com/en-us/office/vba/api/excel.pagesetup.topmargin) — 이 파일의
PT_PER_INCH=72 나눗셈과 일치.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

import win32com.client as win32
from openpyxl.utils.cell import get_column_letter

from scripts.common.excel_a4_constants import (
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


@contextlib.contextmanager
def excel_session(file_path: str):
    """with 블록 안에서 Excel COM 세션을 안전하게 사용.

    Usage:
        with excel_session(path) as (wb, ws, ps):
            ...
    """
    # 원본 저장소의 2026-09-24 사고 기록: 예전엔 GetActiveObject 로 **사용자가 켜 둔
    # Excel** 에 붙은 뒤 Visible=False·DisplayAlerts=False 로 바꾸고 끝에 Quit() 을
    # 불렀다 — 사용자의 창을 숨기고, 저장 안 한 작업을 묻지도 않고 닫을 수 있는
    # 경로였다. 항상 **별도 인스턴스**(DispatchEx)를 새로 띄우고, Quit 은 그
    # 인스턴스에만 한다. 사용자 Excel 에는 닿지 않는다.
    xl = win32.DispatchEx("Excel.Application")
    with contextlib.suppress(
        Exception
    ):  # 검사용 Excel 인스턴스 속성 설정 실패는 무시하고 계속(읽기전용 점검, 실패해도 아래 Open()에서 진짜 오류면 드러남)
        xl.Visible = False
        xl.DisplayAlerts = False
    wb = None
    try:
        wb = xl.Workbooks.Open(str(Path(file_path).resolve()))
        ws = wb.Sheets(1)
        yield wb, ws, ws.PageSetup
    finally:
        if wb is not None:
            with contextlib.suppress(
                Exception
            ):  # 검사 끝에 워크북 닫기 실패 무시(읽기전용 점검 인스턴스, 아래 Quit()으로 최종 정리)
                wb.Close(False)
        with contextlib.suppress(
            Exception
        ):  # 검사 끝에 Excel 인스턴스 종료 실패 무시(별도 DispatchEx 인스턴스라 사용자 Excel에는 영향 없음)
            xl.Quit()


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

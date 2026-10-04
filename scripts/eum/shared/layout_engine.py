"""win32com 렌더 엔진 — LAYOUT 스키마를 열린 Excel에 적용.

사용법:
    from scripts.eum.shared.layout_engine import render, verify_layout

    xl, ws = _connect()
    render(ws, xl)
    errors = verify_layout(ws)
"""

from __future__ import annotations

import contextlib
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


from .layout_schema import (
    A4_AVAIL,
    COL_W,
    ITEM_START,
    LAST_ROW,
    LAYOUT,
    N_ITEMS,
    STD_H,
    UNIT,
    CellDef,
)
from .style_presets import PRINT_MARGINS, get_preset

# ── Excel COM 상수 ────────────────────────────────────────────────────────────
XL_CONTINUOUS = 1
XL_THIN = 2
XL_MEDIUM = -4138
XL_EDGE_LEFT = 7
XL_EDGE_TOP = 8
XL_EDGE_BOTTOM = 9
XL_EDGE_RIGHT = 10
XL_H_LEFT = -4131
XL_H_CENTER = -4108
XL_H_RIGHT = -4152
XL_V_CENTER = -4108
XL_V_TOP = -4160
XL_V_BOTTOM = -4107
XL_PORTRAIT = 1
XL_PAPER_A4 = 9
XL_NO_COLOR = -4142

_HALIGN = {"left": XL_H_LEFT, "center": XL_H_CENTER, "right": XL_H_RIGHT}
_VALIGN = {"center": XL_V_CENTER, "top": XL_V_TOP, "bottom": XL_V_BOTTOM}
_WEIGHT = {"thin": XL_THIN, "medium": XL_MEDIUM}


def _rgb(color: tuple[int, int, int]) -> int:
    r, g, b = color
    return r + g * 256 + b * 65536


# ── 저수준 COM 헬퍼 ───────────────────────────────────────────────────────────


def _rng(ws, r1: int, c1: int, r2: int, c2: int):
    return ws.Range(ws.Cells(r1, c1), ws.Cells(r2, c2))


def _apply_style(ws, r: int, c: int, preset: dict, value: str = ""):
    cl = ws.Cells(r, c)
    cl.Value = value
    cl.Font.Bold = preset["bold"]
    cl.Font.Size = preset["size"]
    cl.Font.Italic = preset["italic"]
    cl.Font.Name = "맑은 고딕"
    cl.HorizontalAlignment = _HALIGN.get(preset["halign"], XL_H_LEFT)
    cl.VerticalAlignment = _VALIGN.get(preset["valign"], XL_V_CENTER)
    cl.WrapText = preset["wrap"]
    if preset["bg"] is not None:
        cl.Interior.Color = _rgb(preset["bg"])
    else:
        cl.Interior.ColorIndex = XL_NO_COLOR
    if preset.get("fg") and preset["fg"] != (0, 0, 0):
        cl.Font.Color = _rgb(preset["fg"])


def _apply_border(ws, r1: int, c1: int, r2: int, c2: int, weight: str = "thin"):
    rng = _rng(ws, r1, c1, r2, c2)
    w = _WEIGHT.get(weight, XL_THIN)
    for side in [XL_EDGE_LEFT, XL_EDGE_TOP, XL_EDGE_BOTTOM, XL_EDGE_RIGHT]:
        rng.Borders(side).LineStyle = XL_CONTINUOUS
        rng.Borders(side).Weight = w


# ── 렌더 엔진 ─────────────────────────────────────────────────────────────────


def render(ws, xl_app, layout: list[CellDef] | None = None) -> None:
    """LAYOUT 스키마를 ws(워크시트)에 적용."""
    if layout is None:
        layout = LAYOUT

    # 초기화
    ws.Cells.UnMerge()
    ws.Cells.Clear()
    # 그리드라인 숨김 실패는 무시(기능·데이터에 영향 없는 스타일 설정)
    with contextlib.suppress(Exception):
        ws.Parent.Windows(1).DisplayGridlines = False

    # 열 너비
    for c, w in COL_W.items():
        ws.Columns(c).ColumnWidth = w

    # 전체 행 높이 22pt
    for r in range(1, LAST_ROW + 1):
        ws.Rows(r).RowHeight = STD_H

    # 셀 렌더
    for cell in layout:
        r1, r2 = cell.rows
        c1, c2 = cell.cols
        preset = get_preset(cell.preset)

        # 병합
        if cell.merged:
            _rng(ws, r1, c1, r2, c2).Merge()

        # 스타일 + 값 (동적 셀은 빈값으로 두고 update_values 에서 채움)
        _apply_style(ws, r1, c1, preset, value="" if cell.dynamic else cell.value)

        # 테두리
        if cell.border:
            _apply_border(ws, r1, c1, r2, c2, cell.border)

    # 수량 입력 셀 배경 (item_qty 프리셋이 이미 C_YELLOW 이지만 기준 셀도 추가)
    for i in range(N_ITEMS):
        r = ITEM_START + i
        ws.Cells(r, 6).Interior.Color = _rgb((255, 255, 153))  # 기준 셀

    # A4 인쇄 설정
    _apply_page_setup(ws, xl_app)

    # 페이지 레이아웃 뷰 전환 실패는 무시(기능·데이터에 영향 없는 스타일 설정)
    with contextlib.suppress(Exception):
        ws.Parent.Windows(1).View = 2


def _apply_page_setup(ws, xl_app) -> None:
    ps = ws.PageSetup
    ps.PaperSize = XL_PAPER_A4
    ps.Orientation = XL_PORTRAIT
    ps.Zoom = False
    ps.FitToPagesWide = 1
    ps.FitToPagesTall = 1
    m = PRINT_MARGINS
    ps.TopMargin = xl_app.InchesToPoints(m["top"])
    ps.BottomMargin = xl_app.InchesToPoints(m["bottom"])
    ps.LeftMargin = xl_app.InchesToPoints(m["left"])
    ps.RightMargin = xl_app.InchesToPoints(m["right"])
    ps.HeaderMargin = xl_app.InchesToPoints(m["header"])
    ps.FooterMargin = xl_app.InchesToPoints(m["footer"])
    ps.PrintGridlines = False
    ps.PrintArea = f"$A$1:$J${LAST_ROW}"


# ── 값 갱신 ──────────────────────────────────────────────────────────────────


def update_values(  # noqa: PLR0913 - 공개 시그니처 유지(동작 불변 리팩터링 범위)
    ws,
    recipient: str,
    qty1: int = 1,
    mo1: int = 24,
    qty2: int = 1,
    mo2: int = 24,
    qty3: int = 1,
) -> None:
    """동적 셀(날짜·수신처·금액)만 갱신."""
    if not recipient or not recipient.strip():
        raise ValueError("수신처(recipient)가 비어 있습니다.")
    if any(q <= 0 for q in (qty1, qty2, qty3)):
        raise ValueError("수량은 1 이상이어야 합니다.")
    if any(m <= 0 for m in (mo1, mo2)):
        raise ValueError("임대 개월 수는 1 이상이어야 합니다.")

    ws.Cells(3, 2).Value = date.today().strftime("%Y년  %m월  %d일")
    ws.Cells(4, 2).Value = f"{recipient}  귀 하"

    for row, qt, qty, mo, is_r in [
        (ITEM_START, "이동형_임대", qty1, mo1, True),
        (ITEM_START + 1, "벽부형_임대", qty2, mo2, True),
        (ITEM_START + 2, "벽부형_구매", qty3, None, False),
    ]:
        supply = UNIT[qt] * qty * (mo or 1) if is_r else UNIT[qt] * qty
        tax = int(supply * 0.1)
        kijun = f"{mo}개월" if is_r else "구  매"
        ws.Cells(row, 4).Value = qty
        ws.Cells(row, 6).Value = kijun
        ws.Cells(row, 7).Value = f"{supply:,}"
        ws.Cells(row, 8).Value = f"{tax:,}"


# ── 자가 검증 ─────────────────────────────────────────────────────────────────


@dataclass
class VerifyResult:
    passed: bool
    errors: list[str]
    warnings: list[str]


def _verify_page_setup(ws, errors: list[str]) -> None:
    """인쇄 영역·Zoom·FitToPage 설정을 검사해 errors 에 누적."""
    # 2) 인쇄 영역 확인
    pa = ws.PageSetup.PrintArea or ""
    if f"$J${LAST_ROW}" not in pa:
        errors.append(f"인쇄영역 불일치: {pa!r} (기대: $A$1:$J${LAST_ROW})")

    # 3) Zoom 해제 확인
    if ws.PageSetup.Zoom:
        errors.append(f"Zoom={ws.PageSetup.Zoom} — False 여야 함")

    # 4) FitToPage 설정
    if ws.PageSetup.FitToPagesWide != 1:
        errors.append("FitToPagesWide != 1")
    if ws.PageSetup.FitToPagesTall != 1:
        errors.append("FitToPagesTall != 1")


def verify_layout(ws) -> VerifyResult:
    """렌더 후 워크시트를 검사해 VerifyResult 반환."""
    errors: list[str] = []
    warnings: list[str] = []

    # 1) 전체 행 높이 합계
    total_h = sum(ws.Rows(r).RowHeight for r in range(1, LAST_ROW + 1))
    if total_h > A4_AVAIL + 30:
        errors.append(f"행높이 합계 {total_h:.1f}pt > A4_AVAIL({A4_AVAIL}pt)+30")
    elif total_h < A4_AVAIL - 60:
        warnings.append(f"행높이 합계 {total_h:.1f}pt — A4 대비 여백 과다")

    _verify_page_setup(ws, errors)

    # 5) 필수 셀 값 존재 (title, notice_left)
    title_val = ws.Cells(1, 1).Value or ""
    if "견" not in str(title_val):
        errors.append(f"제목 셀 값 이상: {title_val!r}")

    notice_val = ws.Cells(9, 2).Value or ""
    if not notice_val:
        warnings.append("안내박스(9,2) 값 없음")

    # 6) 숨김 행 없어야 함
    for r in range(1, LAST_ROW + 1):
        if ws.Rows(r).Hidden:
            errors.append(f"행 {r} 숨김 — 모든 행이 표시돼야 함")

    return VerifyResult(passed=len(errors) == 0, errors=errors, warnings=warnings)


def print_verify(result: VerifyResult) -> None:
    if result.passed:
        print("[PASS] layout_engine 자가검증 통과")
    else:
        print("[FAIL] layout_engine 자가검증 실패:")
        for e in result.errors:
            print(f"  ✗ {e}")
    for w in result.warnings:
        print(f"  ⚠  {w}")

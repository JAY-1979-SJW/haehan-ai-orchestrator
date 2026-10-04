"""openpyxl 렌더 엔진 — LAYOUT 스키마를 xlsx 파일로 저장.

layout_engine.py (win32com) 와 동일한 LAYOUT / style_presets 를 소비해
파일 저장용 렌더를 수행한다.

사용법:
    from scripts.eum.shared.layout_openpyxl import render_to_file
    path = render_to_file("data/견적서.xlsx", recipient="(주)아람정보통신 귀중")
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import (
    Alignment,
    Border,
    Font,
    PatternFill,
    Side,
)
from openpyxl.utils import get_column_letter

from .layout_schema import (
    COL_W,
    ITEM_START,
    LAST_ROW,
    LAYOUT,
    STD_H,
    UNIT,
    CellDef,
)
from .style_presets import PRINT_MARGINS, get_preset

# ── openpyxl 단위 변환 ────────────────────────────────────────────────────────
# openpyxl RowDimension.height 는 pt 단위
# openpyxl ColumnDimension.width 는 문자 너비(character width)
_PT_TO_EMU = 12700  # 1pt = 12700 EMU (사용 안 하지만 참고)


def _color_hex(rgb: tuple[int, int, int] | None) -> str | None:
    if rgb is None:
        return None
    return "{:02X}{:02X}{:02X}".format(*rgb)


def _make_fill(rgb: tuple[int, int, int] | None) -> PatternFill | None:
    if rgb is None:
        return None
    return PatternFill(fill_type="solid", fgColor=_color_hex(rgb))


def _halign_map(h: str) -> str:
    return {"left": "left", "center": "center", "right": "right"}.get(h, "left")


def _valign_map(v: str) -> str:
    return {"center": "center", "top": "top", "bottom": "bottom"}.get(v, "center")


# ── 렌더 엔진 ─────────────────────────────────────────────────────────────────


def render_to_wb(  # noqa: PLR0913 - 공개 시그니처 유지(동작 불변 리팩터링 범위)
    recipient: str = "",
    qty1: int = 1,
    mo1: int = 24,
    qty2: int = 1,
    mo2: int = 24,
    qty3: int = 1,
    layout: list[CellDef] | None = None,
) -> Workbook:
    """LAYOUT 스키마를 openpyxl Workbook 으로 렌더링."""
    if layout is None:
        layout = LAYOUT

    wb = Workbook()
    ws = wb.active
    ws.title = "견적서"

    # 열 너비
    for c_idx, w in COL_W.items():
        col_letter = get_column_letter(c_idx)
        ws.column_dimensions[col_letter].width = w

    # 전체 행 높이
    for r in range(1, LAST_ROW + 1):
        ws.row_dimensions[r].height = STD_H

    # 셀 렌더
    for cell in layout:
        r1, r2 = cell.rows
        c1, c2 = cell.cols
        preset = get_preset(cell.preset)

        # 병합
        if cell.merged:
            ws.merge_cells(
                start_row=r1,
                start_column=c1,
                end_row=r2,
                end_column=c2,
            )

        # 값 (동적 셀은 별도 처리)
        value = "" if cell.dynamic else cell.value
        xl_cell = ws.cell(row=r1, column=c1, value=value)

        # 폰트
        xl_cell.font = Font(
            bold=preset["bold"],
            size=preset["size"],
            italic=preset["italic"],
            name="맑은 고딕",
            color=_color_hex(preset.get("fg")) or "000000",
        )

        # 정렬
        xl_cell.alignment = Alignment(
            horizontal=_halign_map(preset["halign"]),
            vertical=_valign_map(preset["valign"]),
            wrap_text=preset["wrap"],
        )

        # 배경
        fill = _make_fill(preset.get("bg"))
        if fill:
            xl_cell.fill = fill

        # 테두리 — 병합 셀은 전체 범위에 적용
        if cell.border:
            _apply_border_range(ws, r1, c1, r2, c2, cell.border)

    # 동적 값 적용
    _apply_dynamic_values(ws, recipient, qty1, mo1, qty2, mo2, qty3)

    # 인쇄 설정
    _apply_print_setup(ws)

    return wb


def _apply_dynamic_values(  # noqa: PLR0913 - 공개 시그니처 유지(동작 불변 리팩터링 범위)
    ws,
    recipient: str,
    qty1: int,
    mo1: int,
    qty2: int,
    mo2: int,
    qty3: int,
) -> None:
    ws.cell(3, 2).value = date.today().strftime("%Y년  %m월  %d일")
    if recipient:
        ws.cell(4, 2).value = f"{recipient}  귀 하"

    for row, qt, qty, mo, is_r in [
        (ITEM_START, "이동형_임대", qty1, mo1, True),
        (ITEM_START + 1, "벽부형_임대", qty2, mo2, True),
        (ITEM_START + 2, "벽부형_구매", qty3, None, False),
    ]:
        supply = UNIT[qt] * qty * (mo or 1) if is_r else UNIT[qt] * qty
        tax = int(supply * 0.1)
        kijun = f"{mo}개월" if is_r else "구  매"
        ws.cell(row, 4).value = qty
        ws.cell(row, 6).value = kijun
        ws.cell(row, 7).value = f"{supply:,}"
        ws.cell(row, 8).value = f"{tax:,}"


def _apply_border_range(ws, r1, c1, r2, c2, weight: str) -> None:
    """병합 범위 외곽 + 내부 셀 모두에 테두리 적용.

    openpyxl 병합 셀에서 covered cell(primary 제외)의 border는 무시됨.
    primary cell(r1,c1)에 4방향 외곽 border를 모두 설정해 우측·하단도 닫힘.
    """
    style = "medium" if weight == "medium" else "thin"
    s = Side(style=style)
    is_merged = r1 != r2 or c1 != c2

    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            cl = ws.cell(r, c)
            if is_merged and r == r1 and c == c1:
                # primary cell: 4방향 외곽 모두 설정
                cl.border = Border(top=s, bottom=s, left=s, right=s)
            else:
                top = s if r == r1 else None
                bottom = s if r == r2 else None
                left = s if c == c1 else None
                right = s if c == c2 else None
                cl.border = Border(top=top, bottom=bottom, left=left, right=right)


def _apply_print_setup(ws) -> None:
    from openpyxl.worksheet.page import PageMargins

    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.orientation = "portrait"
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True

    m = PRINT_MARGINS
    ws.page_margins = PageMargins(
        top=m["top"],
        bottom=m["bottom"],
        left=m["left"],
        right=m["right"],
        header=m["header"],
        footer=m["footer"],
    )
    ws.print_area = f"A1:J{LAST_ROW}"


def render_to_file(  # noqa: PLR0913 - 공개 시그니처 유지(동작 불변 리팩터링 범위)
    output_path: str,
    recipient: str = "",
    qty1: int = 1,
    mo1: int = 24,
    qty2: int = 1,
    mo2: int = 24,
    qty3: int = 1,
) -> Path:
    """xlsx 파일로 저장 후 Path 반환."""
    wb = render_to_wb(recipient, qty1, mo1, qty2, mo2, qty3)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


# ── 구조 검증 ─────────────────────────────────────────────────────────────────


def verify_file(path: str | Path) -> list[str]:
    """저장된 xlsx 파일의 구조를 검증. 오류 목록 반환."""
    from openpyxl import load_workbook

    errors: list[str] = []
    wb = load_workbook(path)
    ws = wb.active

    # 행 수
    if ws.max_row < LAST_ROW:
        errors.append(f"행 수 {ws.max_row} < LAST_ROW({LAST_ROW})")

    # 제목 셀
    title = ws.cell(1, 1).value or ""
    if "견" not in str(title):
        errors.append(f"제목 셀 값 이상: {title!r}")

    # 인쇄 영역
    pa = ws.print_area or ""
    if str(LAST_ROW) not in str(pa):
        errors.append(f"인쇄영역 불일치: {pa!r}")

    return errors


if __name__ == "__main__":
    import sys

    out = Path("data/test_layout_openpyxl.xlsx")
    print(f"[layout_openpyxl] 테스트 파일 생성: {out}")
    p = render_to_file(str(out), recipient="테스트 수신처")
    errs = verify_file(p)
    if errs:
        print("[FAIL] 파일 검증 실패:")
        for e in errs:
            print(f"  ✗ {e}")
        sys.exit(1)
    else:
        print(f"[PASS] 파일 검증 통과: {p}")

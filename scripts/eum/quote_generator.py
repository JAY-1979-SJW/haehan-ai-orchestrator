"""견적서 xlsx 자동 생성 (openpyxl).

공급자 정보: 승민 F&G, 사업자 372-34-00685, 대표 신재우
지원 유형: 이동형 임대 / 벽부형 임대 / 벽부형 구매
"""

from __future__ import annotations

import io
from datetime import date
from typing import Literal

from openpyxl import Workbook
from openpyxl.styles import (
    Alignment,
    Border,
    Font,
    PatternFill,
    Side,
)

QuoteType = Literal["이동형_임대", "벽부형_임대", "벽부형_구매"]

_SUPPLIER = {
    "등록번호": "372-34-00685",
    "상호": "승민 F&G",
    "대표": "신 재 우",
    "주소": "서울시 강남구 봉은사로114길38 3층303호",
    "업태": "건설업, 도매 및 소매",
    "종목": "전기통신, 소방자재",
    "전화": "02-562-6652",
    "팩스": "02-6442-6665",
}

_UNIT_PRICE: dict[QuoteType, int] = {
    "이동형_임대": 130_000,
    "벽부형_임대": 70_000,
    "벽부형_구매": 1_200_000,
}

_THIN = Side(style="thin")
_MEDIUM = Side(style="medium")


def _border(top=None, bottom=None, left=None, right=None) -> Border:
    return Border(top=top, bottom=bottom, left=left, right=right)


def _all_thin() -> Border:
    return Border(top=_THIN, bottom=_THIN, left=_THIN, right=_THIN)


def _center(wrap=False) -> Alignment:
    return Alignment(horizontal="center", vertical="center", wrap_text=wrap)


def _left(wrap=False) -> Alignment:
    return Alignment(horizontal="left", vertical="center", wrap_text=wrap)


def _right() -> Alignment:
    return Alignment(horizontal="right", vertical="center")


def _header_fill() -> PatternFill:
    return PatternFill("solid", fgColor="D9E1F2")


def _set_col_widths(ws, widths: dict[str, float]) -> None:
    for col_letter, w in widths.items():
        ws.column_dimensions[col_letter].width = w


def _build_quote_sheet(
    ws,
    *,
    recipient: str,
    quote_date: date,
    quote_type: QuoteType,
    quantity: int,
    months: int | None,
) -> None:
    """단일 견적서 시트 구성."""
    ws.sheet_view.showGridLines = False

    # 열 너비
    _set_col_widths(
        ws,
        {
            "A": 2,
            "B": 18,
            "C": 12,
            "D": 8,
            "E": 8,
            "F": 10,
            "G": 10,
            "H": 10,
            "I": 14,
            "J": 2,
        },
    )

    unit_price = _UNIT_PRICE[quote_type]
    is_rental = quote_type in ("이동형_임대", "벽부형_임대")
    supply_amount = unit_price * quantity * (months or 1) if is_rental else unit_price * quantity
    tax_amount = int(supply_amount * 0.1)
    total = supply_amount + tax_amount

    product_name_map: dict[QuoteType, str] = {
        "이동형_임대": "이동형(ACR-C) 본체+함체",
        "벽부형_임대": "벽부형(ACR-C) 본체",
        "벽부형_구매": "벽부형(ACR-C) 본체",
    }
    product_name = product_name_map[quote_type]
    spec = "EA"

    def mc(r1, c1, r2, c2):
        ws.merge_cells(start_row=r1, start_column=c1, end_row=r2, end_column=c2)

    bold11 = Font(bold=True, size=11)

    # ── 행 높이 ──
    for r in range(1, 30):
        ws.row_dimensions[r].height = 18
    ws.row_dimensions[1].height = 36
    ws.row_dimensions[8].height = 30

    # ── 1행: 제목 ──
    mc(1, 2, 1, 9)
    c = ws.cell(1, 2, "견   적   서")
    c.font = Font(bold=True, size=20)
    c.alignment = _center()

    # ── 2행: 날짜 / 공급자 블록 헤더 ──
    mc(2, 2, 2, 5)
    ws.cell(2, 2, quote_date.strftime("%Y년 %m월 %d일")).alignment = _left()
    ws.cell(2, 6, "공 급 자").font = bold11
    ws.cell(2, 6).alignment = _center()
    ws.cell(2, 7, "등록번호").alignment = _center()
    mc(2, 8, 2, 9)
    ws.cell(2, 8, _SUPPLIER["등록번호"]).alignment = _center()

    # ── 3행: 수신처 / 상호 ──
    mc(3, 2, 3, 5)
    ws.cell(3, 2).alignment = _left()
    ws.cell(3, 7, "상호(법인명)").alignment = _center()
    mc(3, 8, 3, 8)
    ws.cell(3, 8, _SUPPLIER["상호"]).alignment = _left()
    ws.cell(3, 9, f"대표: {_SUPPLIER['대표']}  (인)").alignment = _left()

    # ── 4행: 귀하 / 주소 ──
    mc(4, 2, 4, 3)
    ws.cell(4, 2, recipient).font = bold11
    ws.cell(4, 4, "귀하").font = bold11
    ws.cell(4, 7, "주    소").alignment = _center()
    mc(4, 8, 4, 9)
    ws.cell(4, 8, _SUPPLIER["주소"]).alignment = _left(wrap=True)

    # ── 5행: 업태 ──
    ws.cell(5, 2, "아래와 같이 견적합니다.").alignment = _left()
    ws.cell(5, 7, "업    태").alignment = _center()
    mc(5, 8, 5, 8)
    ws.cell(5, 8, _SUPPLIER["업태"]).alignment = _left()
    ws.cell(5, 9, f"종목: {_SUPPLIER['종목']}").alignment = _left()

    # ── 6행: 전화 ──
    ws.cell(6, 7, "전    화").alignment = _center()
    mc(6, 8, 6, 8)
    ws.cell(6, 8, _SUPPLIER["전화"]).alignment = _left()
    ws.cell(6, 9, f"팩스: {_SUPPLIER['팩스']}").alignment = _left()

    # ── 7행: 구분선 ──

    # ── 8행: 합계금액 ──
    mc(8, 2, 8, 5)
    ws.cell(8, 2, "합계금액\n(공급가액 + 세액)").font = bold11
    ws.cell(8, 2).alignment = _center(wrap=True)
    mc(8, 6, 8, 9)
    ws.cell(8, 6, f"₩ {total:,} 원").font = Font(bold=True, size=13)
    ws.cell(8, 6).alignment = _center()
    ws.cell(8, 6).border = _all_thin()

    # ── 9행: 테이블 헤더 ──
    headers_row = 10
    ws.row_dimensions[headers_row].height = 22
    cols = [
        "품      명",
        "규격",
        "수량",
        "단    가",
        "임대기준(월)" if is_rental else "구매기준",
        "공급가액",
        "세    액",
        "비고",
    ]
    col_map = [2, 3, 4, 5, 6, 7, 8, 9]  # B~I
    for i, (h, c_) in enumerate(zip(cols, col_map)):
        cell = ws.cell(headers_row, c_, h)
        cell.font = bold11
        cell.fill = _header_fill()
        cell.alignment = _center(wrap=True)
        cell.border = _all_thin()

    # ── 10행 (실제 11행): 품목 ──
    data_row = 11
    ws.row_dimensions[data_row].height = 22
    values = [
        product_name,
        spec,
        quantity,
        f"{unit_price:,}",
        months if is_rental else "",
        f"{supply_amount:,}",
        f"{tax_amount:,}",
        "이동형배터리 및 통신라우터 포함" if quote_type == "이동형_임대" else "",
    ]
    for i, (v, c_) in enumerate(zip(values, col_map)):
        cell = ws.cell(data_row, c_, v)
        cell.alignment = _center()
        cell.border = _all_thin()

    # ── 계 행 ──
    total_row = 13
    ws.row_dimensions[total_row].height = 22
    mc(total_row, 2, total_row, 6)
    ws.cell(total_row, 2, "계").font = bold11
    ws.cell(total_row, 2).alignment = _center()
    ws.cell(total_row, 2).fill = _header_fill()
    ws.cell(total_row, 2).border = _all_thin()
    ws.cell(total_row, 7, f"{supply_amount:,}").alignment = _right()
    ws.cell(total_row, 7).border = _all_thin()
    ws.cell(total_row, 8, f"{tax_amount:,}").alignment = _right()
    ws.cell(total_row, 8).border = _all_thin()
    ws.cell(total_row, 9).border = _all_thin()

    # ── A/S 안내 문구 ──
    note_row = 12
    mc(note_row, 2, note_row, 9)
    note_text = (
        "무상 1년 A/S이며 정산 시 감가상각 기준이 적용됩니다."
        if quote_type == "이동형_임대"
        else "무상 1년 A/S이며 정산 시 100% 환급 됩니다."
    )
    ws.cell(note_row, 2, note_text).alignment = _left()

    # 공급자 블록 테두리
    for r in range(2, 7):
        for c_ in range(6, 10):
            ws.cell(r, c_).border = _all_thin()


def generate_quote_xlsx(
    *,
    recipient: str,
    quote_type: QuoteType,
    quantity: int,
    months: int | None = None,
    quote_date: date | None = None,
) -> bytes:
    """견적서 xlsx bytes 반환."""
    if quote_date is None:
        quote_date = date.today()
    if quote_type in ("이동형_임대", "벽부형_임대") and not months:
        raise ValueError("임대 유형은 개월수(months)가 필요합니다.")

    wb = Workbook()
    ws = wb.active
    ws.title = quote_type.replace("_", " ")

    _build_quote_sheet(
        ws,
        recipient=recipient,
        quote_date=quote_date,
        quote_type=quote_type,
        quantity=quantity,
        months=months,
    )

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

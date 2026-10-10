"""견적서 레이아웃 단일 진실 공급원 (Single Source of Truth).

quote_generator.py (openpyxl) 와 excel_live.py (win32com) 이
동일한 LAYOUT / 행번호 상수를 참조한다.

셀 정의 필드:
    id       : 식별자 (검증·참조용)
    rows     : (r1, r2) — 병합 범위, 단일 행이면 r1==r2
    cols     : (c1, c2) — 병합 범위, 단일 열이면 c1==c2
    value    : 고정 텍스트 (동적 값은 update_values() 에서 덮어씀)
    preset   : style_presets.py 키 이름
    border   : "thin" | "medium" | None
    dynamic  : True → update_values() 가 value 를 덮어씀 (기본 False)
    id_group : 같은 그룹 셀을 묶어 검증 (선택)
"""

from __future__ import annotations

from dataclasses import dataclass

# ── 기본 출력 경로 ───────────────────────────────────────────────────────────
from pathlib import Path as _Path

from scripts.common.app_paths import onedrive_root, resolve_external

OUTPUT_DIR: _Path = resolve_external(
    "HAEHAN_EUM_QUOTE_DIR", "01. PROJECT_FILE", "01. HAEHAN_ENGNEERING", "10. 견적서", "단말기 견적서", base=onedrive_root()
)  # OneDrive 가 없으면 문서 폴더 아래

# ── A4 레이아웃 수치 ──────────────────────────────────────────────────────────
STD_H: float = 22.0  # 표준 행 높이 (pt) — 전체 통일
A4_AVAIL: float = 690.7  # A4 가용 높이 (pt, 상하여백+머리글/바닥글 제외)
N_ITEMS: int = 3  # 품목 행 수 (가변 가능)
OVERHEAD: int = 15  # 고정행 수: 제목2+정보6+박스2+헤더1+바닥4

# ── 행 번호 상수 ──────────────────────────────────────────────────────────────
ITEM_START: int = 12
N_FILLER: int = max(int((A4_AVAIL - (OVERHEAD + N_ITEMS) * STD_H) / STD_H), 3)
FILLER_START: int = ITEM_START + N_ITEMS  # 15
SUB_ROW: int = FILLER_START + N_FILLER  # 28
TOTAL_ROW: int = SUB_ROW + 1  # 29
NOTE1: int = TOTAL_ROW + 1  # 30
NOTE2: int = NOTE1 + 1  # 31
LAST_ROW: int = NOTE2  # 31

# ── 열 너비 ───────────────────────────────────────────────────────────────────
COL_W: dict[int, float] = {
    1: 1.2,
    2: 21,
    3: 6,
    4: 5,
    5: 13,
    6: 9,
    7: 14,
    8: 11,
    9: 17,
    10: 1.2,
}

# ── 사업자 정보 ───────────────────────────────────────────────────────────────
SUPPLIER: dict[str, str] = {
    "등록번호": "372-34-00685",
    "상호": "해한AI엔지니어링",
    "대표": "신 재 우",
    "주소": "서울특별시 강동구 고덕비즈밸리로 26, 3층 비325호",
    "업태": "건설업, 도매 및 소매업, 정보통신업",
    "종목": "전기통신, 소방자재/전기자재, 안전용품, 소프트웨어개발",
    "전화": "02-562-6652",
    "팩스": "02-6442-6665",
}

# ── 품목 단가 / 제품명 ────────────────────────────────────────────────────────
UNIT: dict[str, int] = {
    "이동형_임대": 90_000,
    "벽부형_임대": 70_000,
    "벽부형_구매": 1_200_000,
}
PRODUCT: dict[str, str] = {
    "이동형_임대": "이동형(ACR-C) 본체+함체",
    "벽부형_임대": "벽부형(ACR-C) 본체",
    "벽부형_구매": "벽부형(ACR-C) 본체",
}
ITEMS_DEF: list[tuple[str, str]] = [
    ("이동형_임대", "배터리·라우터 포함 / 안전 사이트 제공"),
    ("벽부형_임대", ""),
    ("벽부형_구매", ""),
]

# ── 테이블 헤더 ───────────────────────────────────────────────────────────────
TABLE_HEADERS: list[str] = [
    "품      명",
    "규격",
    "수량",
    "단    가",
    "기    준",
    "공 급 가 액",
    "세    액",
    "비    고",
]

# ── 안내 문구 ─────────────────────────────────────────────────────────────────
NOTES: list[tuple[int, str]] = [
    (SUB_ROW, "※ 위 옵션은 단말기 1대 기준이며, 부가세(VAT 10%) 포함 금액입니다. 수량 추가 시 별도 협의."),
    (
        TOTAL_ROW,
        "※ 이동형은 배터리·통신 라우터 내장으로 현장 전원·인터넷 불필요. 벽부형은 유선 전원·네트워크 연결 필요.",
    ),
    (NOTE1, "※ 임대형은 무상 1년 A/S 적용, 구매형은 무상 1년 A/S 후 100% 환급 적용됩니다."),
    (NOTE2, "※ 위 견적금액은 부가세(VAT 10%) 포함 금액입니다."),
]


# ── 셀 정의 dataclass ─────────────────────────────────────────────────────────
@dataclass
class CellDef:
    id: str
    rows: tuple[int, int]
    cols: tuple[int, int]
    value: str = ""
    preset: str = "default"
    border: str | None = "thin"
    dynamic: bool = False
    id_group: str | None = None

    @property
    def merged(self) -> bool:
        r1, r2 = self.rows
        c1, c2 = self.cols
        return r1 != r2 or c1 != c2


# ── LAYOUT 정의 ───────────────────────────────────────────────────────────────
def build_layout() -> list[CellDef]:
    """전체 셀 정의 리스트를 반환. N_ITEMS 변경 시 자동 재계산."""
    layout: list[CellDef] = []

    # 행 1~2: 제목
    layout.append(
        CellDef(
            id="title",
            rows=(1, 2),
            cols=(1, 10),
            value="견   적   서",
            preset="title",
            border="medium",
        )
    )

    # 행 3: 날짜 (동적)
    layout.append(
        CellDef(
            id="date",
            rows=(3, 3),
            cols=(2, 5),
            preset="body",
            border="thin",
            dynamic=True,
        )
    )

    # 행 4~5: 수신처 (동적)
    layout.append(
        CellDef(
            id="recipient",
            rows=(4, 5),
            cols=(2, 5),
            preset="recipient",
            border="thin",
            dynamic=True,
        )
    )

    # 행 6: 아래와 같이
    layout.append(
        CellDef(
            id="greeting",
            rows=(6, 6),
            cols=(2, 5),
            value="아래와 같이 견적합니다.",
            preset="body",
            border=None,
        )
    )

    # 행 3~8: 공급자 블록 (레이블 F열, 값 G:I)
    sup_rows = [
        ("sup_regno", 3, "등  록  번  호", SUPPLIER["등록번호"]),
        ("sup_name", 4, "상      호", SUPPLIER["상호"]),
        ("sup_ceo", 5, "대      표", f"{SUPPLIER['대표']}  (인)"),
        ("sup_addr", 6, "주      소", SUPPLIER["주소"]),
        ("sup_biz", 7, "업      태", f"{SUPPLIER['업태']} / 종목: {SUPPLIER['종목']}"),
        ("sup_tel", 8, "전      화", f"{SUPPLIER['전화']}  /  팩스: {SUPPLIER['팩스']}"),
    ]
    for sid, r, lbl, val in sup_rows:
        layout.append(
            CellDef(
                id=f"{sid}_label",
                rows=(r, r),
                cols=(6, 6),
                value=lbl,
                preset="sup_label",
                border="thin",
                id_group="supplier",
            )
        )
        layout.append(
            CellDef(
                id=f"{sid}_value",
                rows=(r, r),
                cols=(7, 9),
                value=val,
                preset="sup_value",
                border="thin",
                id_group="supplier",
            )
        )

    # 행 9~10: 안내 박스
    layout.append(
        CellDef(
            id="notice_left",
            rows=(9, 10),
            cols=(2, 5),
            value="아래 3가지 옵션 중\n1가지를 선택하여 주십시오.",
            preset="notice_left",
            border="thin",
        )
    )
    layout.append(
        CellDef(
            id="notice_right",
            rows=(9, 10),
            cols=(6, 9),
            value="✔  선택하신 항목에 동그라미(○) 표시 후 회신 바랍니다.",
            preset="notice_right",
            border="medium",
        )
    )

    # 행 11: 테이블 헤더
    for i, h in enumerate(TABLE_HEADERS):
        layout.append(
            CellDef(
                id=f"hdr_{i}",
                rows=(11, 11),
                cols=(i + 2, i + 2),
                value=h,
                preset="table_header",
                border="thin",
                id_group="header",
            )
        )

    # 행 12~(ITEM_START+N_ITEMS-1): 품목
    for i, (qt, bigo) in enumerate(ITEMS_DEF):
        r = ITEM_START + i
        is_r = qt != "벽부형_구매"
        kijun = "24개월" if is_r else "구  매"
        vals = [PRODUCT[qt], "EA", 1, f"{UNIT[qt]:,}", kijun, "", "", bigo]
        for j, v in enumerate(vals):
            c = j + 2
            layout.append(
                CellDef(
                    id=f"item_{i}_c{c}",
                    rows=(r, r),
                    cols=(c, c),
                    value=str(v) if v != "" else "",
                    preset="item_note" if c == 9 else "item_qty" if c == 4 else "item_cell",
                    border="thin",
                    dynamic=(c in (4, 6, 7, 8)),  # 수량·기준·금액은 동적
                    id_group=f"item_{i}",
                )
            )

    # filler 빈 행 (테두리만)
    for r in range(FILLER_START, FILLER_START + N_FILLER):
        for c in range(2, 10):
            layout.append(
                CellDef(
                    id=f"filler_{r}_c{c}",
                    rows=(r, r),
                    cols=(c, c),
                    value="",
                    preset="filler",
                    border="thin",
                    id_group="filler",
                )
            )

    # 안내 문구 4행 (cols 2~10: J열까지 닫아 우측 테두리 완결)
    for row, text in NOTES:
        layout.append(
            CellDef(
                id=f"note_{row}",
                rows=(row, row),
                cols=(2, 10),
                value=text,
                preset="note",
                border="thin",
            )
        )

    return layout


LAYOUT: list[CellDef] = build_layout()

# ── 필수 셀 ID (검증용) ───────────────────────────────────────────────────────
REQUIRED_IDS: list[str] = [
    "title",
    "date",
    "recipient",
    "greeting",
    "notice_left",
    "notice_right",
    "hdr_0",  # 테이블 헤더 첫 번째
    "item_0_c2",  # 첫 품목 첫 셀
    f"note_{SUB_ROW}",
]


# ── 자가 검증 ─────────────────────────────────────────────────────────────────
def validate_schema() -> list[str]:
    """스키마 상수 및 LAYOUT 일관성 검사. 오류 목록 반환 (빈 리스트 = PASS)."""
    errors: list[str] = []

    # 행 번호 계산 검증
    expected = {
        "ITEM_START": 12,
        "FILLER_START": 15,
        "SUB_ROW": 28,
        "TOTAL_ROW": 29,
        "NOTE1": 30,
        "NOTE2": 31,
        "LAST_ROW": 31,
        "N_FILLER": 13,
    }
    actual = {
        "ITEM_START": ITEM_START,
        "FILLER_START": FILLER_START,
        "SUB_ROW": SUB_ROW,
        "TOTAL_ROW": TOTAL_ROW,
        "NOTE1": NOTE1,
        "NOTE2": NOTE2,
        "LAST_ROW": LAST_ROW,
        "N_FILLER": N_FILLER,
    }
    for k, exp in expected.items():
        if actual[k] != exp:
            errors.append(f"{k}: 기대={exp}, 실제={actual[k]}")

    # LAYOUT 내 모든 행이 LAST_ROW 초과하지 않는지
    for cell in LAYOUT:
        if cell.rows[1] > LAST_ROW:
            errors.append(f"셀 {cell.id}: 행{cell.rows[1]} > LAST_ROW({LAST_ROW})")

    # 필수 ID 존재 여부
    ids = {c.id for c in LAYOUT}
    for rid in REQUIRED_IDS:
        if rid not in ids:
            errors.append(f"필수 셀 없음: {rid}")

    # 전체 가시 행 높이 합계 vs A4
    total_h = LAST_ROW * STD_H
    if total_h > A4_AVAIL + 30:  # 30pt 여유
        errors.append(f"행높이 합계 {total_h}pt > A4_AVAIL({A4_AVAIL}pt)+30")

    return errors


if __name__ == "__main__":
    errs = validate_schema()
    if errs:
        print("[FAIL] layout_schema 검증 실패:")
        for e in errs:
            print(f"  ✗ {e}")
    else:
        print("[PASS] layout_schema 검증 통과")
        print(f"  행 번호: ITEM_START={ITEM_START}, FILLER_START={FILLER_START}")
        print(f"  N_FILLER={N_FILLER}, LAST_ROW={LAST_ROW}")
        print(f"  LAYOUT 셀 수: {len(LAYOUT)}")
        print(f"  전체 행 높이: {LAST_ROW * STD_H}pt / A4 가용 {A4_AVAIL}pt")

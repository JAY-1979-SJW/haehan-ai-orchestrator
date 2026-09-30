"""견적서 스타일 프리셋 — 색상·폰트·정렬 상수.

layout_engine.py (win32com) 과 layout_openpyxl.py (openpyxl) 이
동일한 프리셋 키를 참조한다.

프리셋 구조:
    bold     : bool
    size     : int (pt)
    italic   : bool
    halign   : "left" | "center" | "right"
    valign   : "center" | "top" | "bottom"
    wrap     : bool
    bg       : (R, G, B) | None
    fg       : (R, G, B) | None  — 글자색 (기본 검정)
"""

from __future__ import annotations

Color = tuple[int, int, int] | None

# ── 색상 팔레트 ───────────────────────────────────────────────────────────────
C_WHITE: Color = (255, 255, 255)
C_BLACK: Color = (0, 0, 0)
C_BLUE: Color = (217, 225, 242)  # 헤더 배경
C_GRAY: Color = (242, 242, 242)  # 공급자 레이블·안내박스 배경
C_YELLOW: Color = (255, 255, 153)  # 수량·기준 입력 셀
C_NONE: Color = None  # 배경 없음

# ── 스타일 프리셋 정의 ────────────────────────────────────────────────────────
STYLE_PRESETS: dict[str, dict] = {
    "default": {
        "bold": False,
        "size": 10,
        "italic": False,
        "halign": "left",
        "valign": "center",
        "wrap": False,
        "bg": C_NONE,
        "fg": C_BLACK,
    },
    "title": {
        "bold": True,
        "size": 24,
        "italic": False,
        "halign": "center",
        "valign": "center",
        "wrap": False,
        "bg": C_NONE,
        "fg": C_BLACK,
    },
    "body": {
        "bold": False,
        "size": 10,
        "italic": False,
        "halign": "left",
        "valign": "center",
        "wrap": False,
        "bg": C_NONE,
        "fg": C_BLACK,
    },
    "recipient": {
        "bold": True,
        "size": 13,
        "italic": False,
        "halign": "left",
        "valign": "center",
        "wrap": False,
        "bg": C_NONE,
        "fg": C_BLACK,
    },
    "sup_label": {
        "bold": True,
        "size": 10,
        "italic": False,
        "halign": "center",
        "valign": "center",
        "wrap": False,
        "bg": C_GRAY,
        "fg": C_BLACK,
    },
    "sup_value": {
        "bold": False,
        "size": 10,
        "italic": False,
        "halign": "left",
        "valign": "center",
        "wrap": True,
        "bg": C_GRAY,
        "fg": C_BLACK,
    },
    "notice_left": {
        "bold": True,
        "size": 11,
        "italic": False,
        "halign": "center",
        "valign": "center",
        "wrap": True,
        "bg": C_GRAY,
        "fg": C_BLACK,
    },
    "notice_right": {
        "bold": False,
        "size": 10,
        "italic": False,
        "halign": "left",
        "valign": "center",
        "wrap": True,
        "bg": C_NONE,
        "fg": C_BLACK,
    },
    "table_header": {
        "bold": True,
        "size": 10,
        "italic": False,
        "halign": "center",
        "valign": "center",
        "wrap": True,
        "bg": C_BLUE,
        "fg": C_BLACK,
    },
    "item_cell": {
        "bold": False,
        "size": 10,
        "italic": False,
        "halign": "center",
        "valign": "center",
        "wrap": False,
        "bg": C_NONE,
        "fg": C_BLACK,
    },
    "item_qty": {
        "bold": False,
        "size": 10,
        "italic": False,
        "halign": "center",
        "valign": "center",
        "wrap": False,
        "bg": C_YELLOW,
        "fg": C_BLACK,
    },
    "item_note": {
        "bold": False,
        "size": 10,
        "italic": False,
        "halign": "left",
        "valign": "center",
        "wrap": True,
        "bg": C_NONE,
        "fg": C_BLACK,
    },
    "filler": {
        "bold": False,
        "size": 10,
        "italic": False,
        "halign": "left",
        "valign": "center",
        "wrap": False,
        "bg": C_NONE,
        "fg": C_BLACK,
    },
    "note": {
        "bold": False,
        "size": 9,
        "italic": True,
        "halign": "left",
        "valign": "center",
        "wrap": False,
        "bg": C_NONE,
        "fg": C_BLACK,
    },
}

# ── 테두리 굵기 키 ────────────────────────────────────────────────────────────
BORDER_WEIGHTS: dict[str, str] = {
    "thin": "thin",
    "medium": "medium",
}

# ── 인쇄 여백 (인치) ──────────────────────────────────────────────────────────
PRINT_MARGINS: dict[str, float] = {
    "top": 0.75,
    "bottom": 0.75,
    "left": 0.55,
    "right": 0.55,
    "header": 0.30,
    "footer": 0.30,
}


def get_preset(name: str) -> dict:
    """프리셋 이름으로 스타일 딕셔너리 반환. 없으면 default 반환."""
    return dict(STYLE_PRESETS.get(name, STYLE_PRESETS["default"]))


def validate_style() -> list[str]:
    """프리셋 구조 일관성 검사. 오류 목록 반환 (빈 리스트 = PASS)."""
    errors: list[str] = []
    required_keys = {"bold", "size", "italic", "halign", "valign", "wrap", "bg", "fg"}
    valid_halign = {"left", "center", "right"}
    valid_valign = {"center", "top", "bottom"}

    for name, preset in STYLE_PRESETS.items():
        missing = required_keys - preset.keys()
        if missing:
            errors.append(f"[{name}] 누락 키: {missing}")
        if preset.get("halign") not in valid_halign:
            errors.append(f"[{name}] 잘못된 halign: {preset.get('halign')}")
        if preset.get("valign") not in valid_valign:
            errors.append(f"[{name}] 잘못된 valign: {preset.get('valign')}")
        bg = preset.get("bg")
        if bg is not None and (not isinstance(bg, tuple) or len(bg) != 3):
            errors.append(f"[{name}] bg 형식 오류: {bg}")

    # layout_schema 에서 사용하는 프리셋이 모두 등록됐는지
    try:
        from .layout_schema import LAYOUT

        used = {c.preset for c in LAYOUT}
        for p in used:
            if p not in STYLE_PRESETS:
                errors.append(f"LAYOUT 참조 프리셋 미등록: '{p}'")
    except ImportError:
        errors.append("layout_schema import 실패 — 프리셋 교차 검증 불가")

    return errors


if __name__ == "__main__":
    errs = validate_style()
    if errs:
        print("[FAIL] style_presets 검증 실패:")
        for e in errs:
            print(f"  ✗ {e}")
    else:
        print("[PASS] style_presets 검증 통과")
        print(f"  프리셋 수: {len(STYLE_PRESETS)}")
        print(f"  색상 상수: C_BLUE={C_BLUE}, C_GRAY={C_GRAY}, C_YELLOW={C_YELLOW}")

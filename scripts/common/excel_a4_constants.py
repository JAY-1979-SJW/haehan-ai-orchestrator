"""A4 서식 검사에 사용되는 상수 모음.

이식 출처: "42. excel-ai-agent" 저장소의 excel_ai_agent/constants.py.
tools/office/check_a4.py 가 `from shared.constants import ...` 로 이 저장소에 없는
`shared` 패키지를 참조해 매 xlsx 편집마다 도는 PostToolUse 훅이 100% 실패하던
문제(docs/defect_index.json #32)를 고치기 위해 2026-09-29 이식. 값은 원본과 동일.
"""

from __future__ import annotations

import re

# ── A4 치수 ──────────────────────────────────────────────────────────────────
A4_HEIGHT_MM = 297
PT_PER_INCH = 72
MM_PER_INCH = 25.4
A4_HEIGHT_PT = A4_HEIGHT_MM / MM_PER_INCH * PT_PER_INCH  # ≈ 841.89 pt

# ── Excel COM 상수 ────────────────────────────────────────────────────────────
XL_CONTINUOUS = 1
PAPER_SIZE_A4 = 9
ORIENTATION_PORTRAIT = 1

BORDER_LEFT = 7
BORDER_TOP = 8
BORDER_BOTTOM = 9
BORDER_RIGHT = 10

# ── 기본 인쇄 여백 (인치) ─────────────────────────────────────────────────────
MARGIN_TOP_IN = 0.75
MARGIN_BOTTOM_IN = 0.75

# ── 인쇄영역 파싱 ─────────────────────────────────────────────────────────────
PRINT_AREA_RE = re.compile(r"\$[A-Z]+\$(\d+)$")

# ── 검사 허용 오차 ────────────────────────────────────────────────────────────
MARGIN_TOLERANCE_IN = 0.01  # 여백 허용 오차 (인치)
ROW_HEIGHT_TOLERANCE = 12.0  # 행높이 합계 허용 오차 (pt) — 22pt 표준 행의 절반, FitToPage가 잔량 흡수

# ── 열 범위 (A~J) ─────────────────────────────────────────────────────────────
DATA_COLUMN_COUNT = 10

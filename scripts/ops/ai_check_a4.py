"""AI A4 서식 검증 — 셀 데이터를 OpenAI API로 전송해 품질 판단.

코드 검사(check_a4.py) 통과 후 실행.
셀 값·행높이·열너비·테두리·페이지설정을 추출해 GPT-4o-mini에게 평가 요청.

사용법:
    python scripts/ops/ai_check_a4.py <xlsx_파일경로>
    python scripts/ops/ai_check_a4.py data/견적서_아람정보통신_v6.xlsx
"""

import json
import os
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from openpyxl.utils import get_column_letter  # noqa: E402
from shared.constants import DATA_COLUMN_COUNT  # noqa: E402
from shared.excel_utils import (  # noqa: E402
    cell_borders,
    column_widths,
    excel_session,
    page_setup_info,
    parse_last_row,
    row_heights,
)

# ── Excel 셀 데이터 추출 ──────────────────────────────────────────────────────


def extract_sheet_data(file_path: str) -> dict:
    with excel_session(file_path) as (_wb, ws, ps):
        last_row = parse_last_row(ps, fallback=30)

        page = page_setup_info(ps)
        rows = row_heights(ws, last_row)
        cols = column_widths(ws, DATA_COLUMN_COUNT)
        cells = _extract_cells(ws, last_row)

    return {"page": page, "rows": rows, "cols": cols, "cells": cells, "last_row": last_row}


def _extract_cells(ws, last_row: int) -> dict:
    cells = {}
    for r in range(1, last_row + 1):
        for c in range(1, DATA_COLUMN_COUNT + 1):
            cell = ws.Cells(r, c)
            val = cell.Value
            borders = cell_borders(cell)
            merged = cell.MergeArea.Count > 1

            if val is None and not merged and not any(borders.values()):
                continue  # 완전히 빈 셀 생략

            addr = f"{get_column_letter(c)}{r}"
            cells[addr] = {
                "value": str(val)[:60] if val is not None else None,
                "bold": bool(cell.Font.Bold),
                "size": cell.Font.Size,
                "halign": cell.HorizontalAlignment,
                "borders": borders,
                "merged": merged,
                "bg": bool(cell.Interior.ColorIndex not in (-4142, None)),
            }
    return cells


# ── OpenAI 평가 요청 ──────────────────────────────────────────────────────────

SYSTEM_PROMPT = """당신은 Excel A4 견적서 서식 품질 전문가입니다.
추출된 셀 데이터를 분석하여 다음 관점에서 평가합니다:

1. 레이아웃 균형 — 제목·정보블록·테이블·안내문구 비율이 자연스러운가
2. 행 높이 배분 — 섹션별 높이가 내용에 비례하는가, 너무 좁거나 넓은 행이 있는가
3. 테두리 완결성 — 표 영역 테두리가 빠진 곳 없이 닫혀있는가
4. 필수 항목 존재 — 수신처·날짜·공급자 정보·품목 테이블·안내문구가 모두 있는가
5. A4 인쇄 적합성 — 여백·FitToPage 설정이 인쇄 시 잘리거나 비는 문제없는가
6. 가독성 — 폰트 크기·볼드 사용이 계층 구조를 명확히 전달하는가

평가 결과를 JSON으로만 반환하세요:
{
  "grade": "A|B|C",
  "summary": "한 줄 요약",
  "passed": ["통과 항목 목록"],
  "issues": [{"item": "항목명", "detail": "문제 내용", "suggestion": "개선 제안"}],
  "print_ready": true|false
}"""

USER_TEMPLATE = """아래는 A4 세로 견적서 Excel 파일의 셀 데이터입니다.

## 페이지 설정
{page_json}

## 행 높이 (pt) — 숨김 행 제외
{rows_text}

## 열 너비
{cols_json}

## 주요 셀 내용 (값이 있거나 테두리 있는 셀)
{cells_text}

위 데이터를 분석하여 A4 견적서 서식 품질을 평가해주세요."""


def ai_evaluate(data: dict) -> dict:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise OSError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")

    from openai import OpenAI

    client = OpenAI(api_key=api_key)

    rows_text = "\n".join(f"  행{r:02d}: {info['height']}pt" for r, info in data["rows"].items() if not info["hidden"])
    cells_text = "\n".join(
        f"  {addr}: value={info['value']!r}  bold={info['bold']}  size={info['size']}"
        f"  borders={info['borders']}  merged={info['merged']}  bg={info['bg']}"
        for addr, info in data["cells"].items()
        if info["value"] is not None
    )

    prompt = USER_TEMPLATE.format(
        page_json=json.dumps(data["page"], ensure_ascii=False, indent=2),
        rows_text=rows_text,
        cols_json=json.dumps(data["cols"], ensure_ascii=False),
        cells_text=cells_text,
    )

    resp = client.chat.completions.create(
        model="gpt-4.1",
        max_tokens=1024,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )

    raw = resp.choices[0].message.content.strip()
    m = re.search(r"\{[\s\S]+\}", raw)
    return (
        json.loads(m.group())
        if m
        else {
            "grade": "?",
            "summary": raw,
            "passed": [],
            "issues": [],
            "print_ready": False,
        }
    )


# ── 결과 출력 ─────────────────────────────────────────────────────────────────

GRADE_ICON = {"A": "🏆", "B": "✅", "C": "⚠️"}


def print_result(result: dict, file_name: str):
    grade = result.get("grade", "?")
    icon = GRADE_ICON.get(grade, "❓")
    ready = "인쇄 준비 완료 ✅" if result.get("print_ready") else "인쇄 전 확인 필요 ⚠️"

    print(f"\n[AI 검증] {file_name}")
    print("─" * 55)
    print(f"  등급: {icon} {grade}등급   {result.get('summary', '')}")
    print(f"  인쇄: {ready}")

    passed = result.get("passed", [])
    if passed:
        print("\n  통과 항목:")
        for p in passed:
            print(f"    ✅ {p}")

    issues = result.get("issues", [])
    if issues:
        print("\n  개선 필요:")
        for iss in issues:
            print(f"    ❌ [{iss.get('item', '')}] {iss.get('detail', '')}")
            if iss.get("suggestion"):
                print(f"       → {iss['suggestion']}")
    print("─" * 55)


# ── 메인 ─────────────────────────────────────────────────────────────────────


def run(file_path: str) -> bool:
    path = Path(file_path)
    if not path.exists():
        print(f"[ai_check_a4] ❌ 파일 없음: {path}")
        return False

    print("[ai_check_a4] 셀 데이터 추출 중...")
    data = extract_sheet_data(file_path)

    print("[ai_check_a4] GPT-4.1 평가 요청 중...")
    result = ai_evaluate(data)

    print_result(result, path.name)
    return result.get("print_ready", False)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python scripts/ops/ai_check_a4.py <xlsx_파일경로>")
        sys.exit(1)
    ok = run(sys.argv[1])
    sys.exit(0 if ok else 1)

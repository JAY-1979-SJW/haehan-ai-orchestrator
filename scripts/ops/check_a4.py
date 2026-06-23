"""A4 Excel 서식 자동 검사 스크립트 (범용).

백그라운드 Excel COM으로 파일을 열어 A4 인쇄 설정 · 행높이 · 격자선을 검사합니다.

사용법:
    python scripts/ops/check_a4.py <xlsx_파일경로>
    python scripts/ops/check_a4.py data/견적서_아람정보통신_v6.xlsx
"""

import os
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from shared.constants import (  # noqa: E402
    MARGIN_BOTTOM_IN,
    MARGIN_TOLERANCE_IN,
    MARGIN_TOP_IN,
    ORIENTATION_PORTRAIT,
    PAPER_SIZE_A4,
    PT_PER_INCH,
    ROW_HEIGHT_TOLERANCE,
)
from shared.excel_utils import (  # noqa: E402
    available_height,
    excel_session,
    parse_last_row,
    row_heights,
    visible_height_sum,
)


def check_a4(file_path: str) -> bool:
    """A4 설정을 검사하고 모두 통과하면 True 반환."""
    path = Path(file_path).resolve()
    if not path.exists():
        print(f"[check_a4] ❌ 파일 없음: {path}")
        return False

    try:
        with excel_session(str(path)) as (wb, ws, ps):
            avail = available_height(ps)
            lr = parse_last_row(ps, fallback=ws.UsedRange.Rows.Count)
            rows = row_heights(ws, lr)
            total = visible_height_sum(rows)
            diff = abs(avail - total)

            try:
                no_grid = not wb.Application.ActiveWindow.DisplayGridlines
            except Exception:
                no_grid = True

            results = [
                ("A4 용지", ps.PaperSize == PAPER_SIZE_A4, f"paperSize={ps.PaperSize:.0f}"),
                ("세로 방향", ps.Orientation == ORIENTATION_PORTRAIT, f"orientation={ps.Orientation:.0f}"),
                ("FitToPagesWide", ps.FitToPagesWide == 1, f"FitW={ps.FitToPagesWide}"),
                ("FitToPagesTall", ps.FitToPagesTall == 1, f"FitH={ps.FitToPagesTall}"),
                ("Zoom 해제", not ps.Zoom, f"Zoom={ps.Zoom}"),
                (
                    '상단여백 0.75"',
                    abs(ps.TopMargin / PT_PER_INCH - MARGIN_TOP_IN) < MARGIN_TOLERANCE_IN,
                    f'{ps.TopMargin / PT_PER_INCH:.3f}"',
                ),
                (
                    '하단여백 0.75"',
                    abs(ps.BottomMargin / PT_PER_INCH - MARGIN_BOTTOM_IN) < MARGIN_TOLERANCE_IN,
                    f'{ps.BottomMargin / PT_PER_INCH:.3f}"',
                ),
                ("인쇄영역 설정", bool(ps.PrintArea), ps.PrintArea or "-"),
                (
                    "행높이 합계≈A4",
                    diff < ROW_HEIGHT_TOLERANCE,
                    f"합계={total:.1f}pt / 가용={avail:.1f}pt / 차이={avail - total:+.1f}pt",
                ),
                ("격자선 숨김", no_grid, ""),
            ]

            print(f"\n[check_a4] {path.name}")
            print("─" * 55)
            all_pass = True
            for label, ok, detail in results:
                print(f"  {'✅' if ok else '❌'} {label:20s}  {detail}")
                if not ok:
                    all_pass = False
            print("─" * 55)
            if all_pass:
                print("  🎉 모든 A4 서식 검사 통과\n")
            else:
                print("  ⚠️  일부 항목 불일치 — 위 ❌ 항목 확인 필요\n")

            return all_pass

    except Exception as e:
        print(f"[check_a4] ❌ 오류: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python scripts/ops/check_a4.py <xlsx_파일경로>")
        sys.exit(1)

    ok = check_a4(sys.argv[1])

    if ok:
        try:
            here = os.path.dirname(os.path.abspath(__file__))
            ai_script = os.path.join(here, "ai_check_a4.py")
            subprocess.run(
                [sys.executable, ai_script, sys.argv[1]],
                check=False,
                env=os.environ.copy(),
            )
        except Exception as e:
            print(f"[check_a4] AI 검증 실행 실패: {e}")

    sys.exit(0 if ok else 1)

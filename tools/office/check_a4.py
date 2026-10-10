"""A4 Excel 서식 자동 검사 스크립트 (범용).

백그라운드 Excel COM으로 파일을 열어 A4 인쇄 설정 · 행높이 · 격자선을 검사합니다.

사용법:
    python tools/office/check_a4.py <xlsx_파일경로>
    python tools/office/check_a4.py data/견적서_아람정보통신_v6.xlsx
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# hook_check_a4.py가 `python tools/office/check_a4.py <path>`로 -m 없이 직접
# 실행하므로(cwd=repo root 이긴 하나 그것만으론 sys.path에 안 잡힘) 절대 패키지
# import(scripts.common...)가 되게 저장소 루트를 앞에 넣는다(scripts/ops 하위
# 다른 스크립트들의 기존 관례, 예: audit_backend_runtime_contract.py).
_ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# 2026-09-29 정정(docs/defect_index.json #32): 원래 여기서 참조하던 `shared` 패키지는
# 이 저장소에 없어(다른 저장소 "42. excel-ai-agent"의 excel_ai_agent 패키지를 잘못
# 가리킴) 이 스크립트가 xlsx 편집마다 도는 PostToolUse 훅에서 매번 ImportError로
# 실패하고 있었다. 실제 구현을 scripts/common/excel_a4_constants.py·excel_a4_utils.py
# 로 이식해 정상 경로로 고쳤다.
from scripts.common.excel_a4_constants import (  # noqa: E402
    MARGIN_BOTTOM_IN,
    MARGIN_TOLERANCE_IN,
    MARGIN_TOP_IN,
    ORIENTATION_PORTRAIT,
    PAPER_SIZE_A4,
    PT_PER_INCH,
    ROW_HEIGHT_TOLERANCE,
)
from scripts.common.excel_a4_utils import (  # noqa: E402
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
            except Exception:  # noqa: BLE001 - 엑셀 A4 인쇄설정 점검 스크립트(COM 자동화, 읽기전용 점검) — 그리드라인 속성 조회 실패는 기본값 True로 폴백, 전체 점검/AI검증 실행 실패는 오류 출력 후 False 반환
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

    except Exception as e:  # noqa: BLE001 - 엑셀 A4 인쇄설정 점검 스크립트(COM 자동화, 읽기전용 점검) — 그리드라인 속성 조회 실패는 기본값 True로 폴백, 전체 점검/AI검증 실행 실패는 오류 출력 후 False 반환
        print(f"[check_a4] ❌ 오류: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python tools/office/check_a4.py <xlsx_파일경로>")
        sys.exit(1)

    ok = check_a4(sys.argv[1])
    sys.exit(0 if ok else 1)

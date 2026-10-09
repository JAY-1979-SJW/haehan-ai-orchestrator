"""tools/office/check_excel_live.py — 실행 중인 Excel(견적서 워크북)의 페이지 설정을
그대로 읽어 A4 한 장에 맞는지 점검하는 즉석 진단 스크립트.

Excel이 켜져 있어야만 동작한다(임포트 실패가 아니라 설계상 전제조건 —
2026-09-29 defect_index #32 조사: 최상위 코드가 임포트 시점에 즉시 GetActiveObject
COM 호출을 시도해 "임포트 자체가 실패"로 보였을 뿐, 실제 결함은 아니었음. 다만
직접 실행 스크립트를 라이브러리처럼 import하면 안 된다는 것과 Excel 미실행 시
안내 없이 원본 COM 에러가 그대로 튀는 문제는 있어 `main()` 가드로 감싼다).

사용: python tools/office/check_excel_live.py
"""

from __future__ import annotations

import sys


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    import win32com.client as win32

    try:
        xl = win32.GetActiveObject("Excel.Application")
    except Exception:  # noqa: BLE001 - COM 활성 객체 없음(pywintypes.com_error 등) 을 하나로 묶어 안내, Excel 미실행이 유일한 실제 원인
        print("[check_excel_live] 실행 중인 Excel을 찾지 못했습니다 — 견적서 워크북을 열어둔 뒤 재실행하세요.")
        return 1

    wb = None
    for i in range(1, xl.Workbooks.Count + 1):
        if "견적서" in xl.Workbooks(i).Name:
            wb = xl.Workbooks(i)
            break
    if wb is None:
        print("[check_excel_live] 열려 있는 워크북 중 이름에 '견적서'가 포함된 것이 없습니다.")
        return 1

    ws = wb.Sheets(1)
    ps = ws.PageSetup

    a4_pt = 297 / 25.4 * 72
    top = ps.TopMargin
    bottom = ps.BottomMargin
    header = ps.HeaderMargin
    footer = ps.FooterMargin
    avail = a4_pt - top - bottom - header - footer

    print("=== 페이지 설정 ===")
    print(f"  용지: A4({ps.PaperSize:.0f})  방향: {'세로' if ps.Orientation == 1 else '가로'}")
    print(f"  FitToPagesWide={ps.FitToPagesWide}  FitToPagesTall={ps.FitToPagesTall}  Zoom={ps.Zoom}")
    print(
        f"  여백(인치) 상={top / 72:.3f}  하={bottom / 72:.3f}  좌={ps.LeftMargin / 72:.3f}  우={ps.RightMargin / 72:.3f}"
    )
    print(f'  헤더={header / 72:.3f}"  푸터={footer / 72:.3f}"')
    print(f"  A4 전체={a4_pt:.1f}pt  가용={avail:.1f}pt")
    print(f"  인쇄영역: {ps.PrintArea}")
    print()

    print("=== 행 높이 (행1~25) ===")
    total_vis = 0
    for r in range(1, 26):
        h = ws.Rows(r).RowHeight
        hidden = ws.Rows(r).Hidden
        mark = " [숨김]" if hidden else ""
        if not hidden:
            total_vis += h
        print(f"  행{r:02d}: {h:5.1f}pt{mark}")

    diff = avail - total_vis
    print(f"\n  가시행 합계: {total_vis:.1f}pt")
    print(f"  A4 가용:     {avail:.1f}pt")
    print(f"  차이:        {diff:+.1f}pt  ({'하단 여백 남음' if diff > 2 else '초과' if diff < -2 else 'OK'})")
    print()
    print("=== 시트 뷰 ===")
    print(f"  View={ws.Parent.Windows(1).View}  (1=일반 2=페이지레이아웃 3=나누기미리보기)")
    print(f"  GridLines={ws.Parent.Windows(1).DisplayGridlines}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

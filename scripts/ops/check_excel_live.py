import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import win32com.client as win32  # noqa: E402

xl = win32.GetActiveObject("Excel.Application")
wb = None
for i in range(1, xl.Workbooks.Count + 1):
    if "견적서" in xl.Workbooks(i).Name:
        wb = xl.Workbooks(i)
        break
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

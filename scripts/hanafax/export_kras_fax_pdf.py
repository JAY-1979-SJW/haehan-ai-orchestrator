"""
scripts/hanafax/export_kras_fax_pdf.py

해한AI_AI안전관리시스템_영업공문_최종.xlsx → PDF (A4 세로, 정확히 2페이지).

기준: docs/directives/kras_safety_sales_document_spec.md
- 시트 '1_제안공문', '2_법령참고' 만 출력 (근거자료 제외)
- A4 Portrait, Fit to 1 page wide x 1 page tall, 좁은 여백
- 텍스트 잘림 방지: 줄바꿈(WrapText) 있는 행은 AutoFit으로 높이 재계산

방법: Workbook.ExportAsFixedFormat 은 시트 선택과 무관하게 워크북 전체를
내보낸다(실측 확인 — 6페이지=3시트 전부). 그래서 임시 복사본에서 '근거자료'
시트 자체를 삭제한 뒤 워크북 단위로 내보낸다(원본 파일은 건드리지 않음).
"""

from __future__ import annotations

import contextlib
import shutil
import sys
import tempfile
from pathlib import Path

import fitz  # PyMuPDF
import win32com.client as win32

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:  # 단독 실행 시에도 scripts 패키지를 import 할 수 있게
    sys.path.insert(0, str(_ROOT))
from scripts.common.app_paths import known_folder  # noqa: E402

A4_WIDTH_PT = 595.32  # 210mm
A4_HEIGHT_PT = 841.92  # 297mm
A4_TOLERANCE_PT = 3.0

SRC_XLSX = sys.argv[1] if len(sys.argv) > 1 else str(known_folder("downloads") / "해한AI_AI안전관리시스템_영업공문_최종.xlsx")
OUT_PDF = sys.argv[2] if len(sys.argv) > 2 else str(known_folder("downloads") / "해한AI_AI안전관리시스템_영업공문_최종.pdf")

KEEP_SHEETS = ["1_제안공문", "2_법령참고"]
DROP_SHEETS = ["근거자료"]

XL_PAPER_A4 = 9
XL_PORTRAIT = 1


def _ensure_a4(src_pdf: str, out_pdf: str) -> None:
    """내보낸 PDF의 페이지 크기를 정확한 A4로 강제한다.

    실측: 기본프린터(ALPDF, 비표준 가상 프린터) 상태에서는 Excel
    PageSetup.PaperSize=A4 를 지정해도 실제 출력이 A4가 아닌 크기
    (653.8x925.3pt)로 나올 수 있다. 콘텐츠 자체는 Fit-to-page로 이미
    페이지 좌상단 영역 안에 다 들어가 있으므로(오른쪽 빈 여백만 초과분),
    페이지 경계(MediaBox)만 A4로 다시 정의해도 내용 손실이 없다 — 단,
    실제로 콘텐츠가 A4 밖으로 나가는지 먼저 확인하고, 나가면 조용히
    자르지 않고 예외를 낸다(그 경우는 Excel 쪽 배율을 다시 봐야 한다).
    """
    doc = fitz.open(src_pdf)
    for page in doc:
        w, h = page.rect.width, page.rect.height
        if abs(w - A4_WIDTH_PT) <= A4_TOLERANCE_PT and abs(h - A4_HEIGHT_PT) <= A4_TOLERANCE_PT:
            continue
        max_x = max_y = 0.0
        for block in page.get_text("blocks"):
            _x0, _y0, x1, y1 = block[:4]
            max_x, max_y = max(max_x, x1), max(max_y, y1)
        if max_x > A4_WIDTH_PT + A4_TOLERANCE_PT or max_y > A4_HEIGHT_PT + A4_TOLERANCE_PT:
            raise RuntimeError(
                f"페이지 {page.number + 1}: 실제 크기 {w:.1f}x{h:.1f}pt, 콘텐츠가 "
                f"({max_x:.1f}, {max_y:.1f})까지 있어 A4({A4_WIDTH_PT:.0f}x{A4_HEIGHT_PT:.0f}pt) "
                "밖으로 나감 — 단순 크롭 불가, Excel 쪽 배율/여백 재확인 필요"
            )
        page.set_mediabox(fitz.Rect(0, 0, A4_WIDTH_PT, A4_HEIGHT_PT))
    doc.save(out_pdf)
    doc.close()


def _fit_merged_wrap_rows(ws) -> None:
    """세로 병합 + 줄바꿈 셀의 실제 필요 높이를 계산해서 적용(scripts/hanafax/excel_merge_fit.py 공용 함수)."""
    from scripts.hanafax.excel_merge_fit import fit_merged_wrap_rows

    fit_merged_wrap_rows(ws)


def main():
    tmp_dir = Path(tempfile.mkdtemp(prefix="kras_pdf_"))
    tmp_xlsx = str(tmp_dir / "work.xlsx")
    shutil.copy(SRC_XLSX, tmp_xlsx)

    excel = win32.gencache.EnsureDispatch("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    # 실측 확인: 기본프린터가 "ALPDF"(비표준 가상 프린터)일 때 PageSetup.PaperSize
    # = A4 로 지정해도 실제 출력 크기가 A4가 아니게 나온 적이 있었다(653.8x925.3pt) —
    # PaperSize는 활성 프린터 드라이버가 지원하는 용지에 종속되는 COM 특성.
    # ActivePrinter를 "Microsoft Print to PDF"로 바꾸면 Workbooks.Open 자체가
    # None을 반환하는 부작용이 있어(실측) 프린터는 건드리지 않고, 대신
    # 내보낸 뒤 실제 크기를 확인해서 A4가 아니면 후처리로 맞춘다(main 하단).
    wb = excel.Workbooks.Open(tmp_xlsx)
    try:
        # 1) 근거자료 시트는 PDF에 넣지 않는다 — 복사본에서 삭제
        for name in DROP_SHEETS:
            # PDF 변환용 임시 복사본(tmp_xlsx, 원본과 별개)에서 불필요한 시트 삭제 - 원본 파일이나 운영 DB가 아니며 삭제 실패해도 무시 가능
            with contextlib.suppress(Exception):
                wb.Sheets(name).Delete()

        for name in KEEP_SHEETS:
            ws = wb.Sheets(name)
            ws.ResetAllPageBreaks()

            # 인쇄영역은 병합-높이 보정(스크래치 행 500 사용) 전에 미리
            # 확정해둔다 — 보정 이후 UsedRange 를 다시 읽으면 스크래치 행
            # 때문에 500행까지로 부풀어(실측 확인) 빈 페이지가 생긴다.
            content_addr = ws.UsedRange.Address

            # 2) 텍스트 잘림 방지: 줄바꿈 있는 셀이 속한 행 높이를 재계산.
            #    열 너비는 손대지 않는다(그리드 레이아웃 보존).
            ws.Rows.AutoFit()
            # 2-1) 세로 병합 셀은 위 AutoFit이 못 잡는다 — 별도로 보정.
            _fit_merged_wrap_rows(ws)

            ps = ws.PageSetup
            ps.Orientation = XL_PORTRAIT
            ps.PaperSize = XL_PAPER_A4
            # 순서 중요: FitToPages* 를 먼저 지정한 뒤 Zoom=False 로 확정해야
            # Excel COM이 자동확대축소 모드로 실제 전환된다(역순이면 Zoom=100
            # 자동배율로 되돌아가 콘텐츠가 여러 장으로 쪼개짐 — 실측 확인됨).
            ps.FitToPagesWide = 1
            ps.FitToPagesTall = 1
            ps.Zoom = False
            ps.TopMargin = excel.InchesToPoints(0.3)
            ps.BottomMargin = excel.InchesToPoints(0.3)
            ps.LeftMargin = excel.InchesToPoints(0.3)
            ps.RightMargin = excel.InchesToPoints(0.3)
            ps.HeaderMargin = excel.InchesToPoints(0.1)
            ps.FooterMargin = excel.InchesToPoints(0.1)
            ps.CenterHeader = ""
            ps.CenterFooter = ""
            ps.LeftHeader = ""
            ps.RightHeader = ""
            ps.LeftFooter = ""
            ps.RightFooter = ""
            ps.PrintGridlines = False
            ps.PrintHeadings = False
            ps.PrintArea = content_addr
            print(
                f"  {name}: Zoom={ps.Zoom} FitW={ps.FitToPagesWide} FitT={ps.FitToPagesTall} PrintArea={ps.PrintArea}"
            )

        # xlOpenXMLWorkbook = 51 (.xlsx) — Save() 단독 호출은 "문서가 저장되지
        # 않았습니다" 오류로 실패했다(실측) — 형식을 명시한 SaveAs 로 교체.
        wb.SaveAs(tmp_xlsx, FileFormat=51)

        # 실측 확인: ExportAsFixedFormat 의 출력 경로에 한글이 섞이면
        # "문서가 저장되지 않았습니다" COM 오류가 난다(ASCII 경로는 정상
        # 동작, 페이지 수도 정확히 2). ASCII 임시 경로로 내보낸 뒤
        # 최종 한글 파일명으로 옮긴다.
        tmp_pdf = str(tmp_dir / "out.pdf")
        wb.ExportAsFixedFormat(0, tmp_pdf)  # 0 = xlTypePDF — 워크북에 시트 2개만 남음
        Path(OUT_PDF).parent.mkdir(parents=True, exist_ok=True)
        _ensure_a4(tmp_pdf, OUT_PDF)
        print(f"OK: {OUT_PDF}")
    finally:
        wb.Close(SaveChanges=False)
        excel.Quit()
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()

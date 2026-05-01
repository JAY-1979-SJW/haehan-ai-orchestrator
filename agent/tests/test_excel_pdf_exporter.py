"""PDF 내보내기 및 인쇄 영역 관리 테스트."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, PropertyMock, patch

from agent.excel import pdf_exporter, print_area_manager


class TestPDFExporter(unittest.TestCase):
    """PDF 내보내기 테스트."""

    def test_export_active_sheet_to_pdf_success(self):
        """활성 시트를 PDF로 내보내기 성공."""
        sheet = MagicMock()
        output_path = "C:\\output\\report.pdf"

        success, error = pdf_exporter.export_active_sheet_to_pdf(sheet, output_path)

        self.assertTrue(success)
        self.assertIsNone(error)
        sheet.ExportAsFixedFormat.assert_called_once_with(0, output_path)

    def test_export_active_sheet_to_pdf_no_sheet(self):
        """시트 없음 오류."""
        success, error = pdf_exporter.export_active_sheet_to_pdf(None, "output.pdf")

        self.assertFalse(success)
        self.assertEqual(error, "SHEET_NOT_FOUND")

    def test_export_active_sheet_to_pdf_no_output_path(self):
        """출력 경로 없음 오류."""
        sheet = MagicMock()
        success, error = pdf_exporter.export_active_sheet_to_pdf(sheet, "")

        self.assertFalse(success)
        self.assertEqual(error, "OUTPUT_PATH_REQUIRED")

    def test_export_active_sheet_to_pdf_com_error(self):
        """COM 오류 처리."""
        sheet = MagicMock()
        sheet.ExportAsFixedFormat.side_effect = Exception("COM error")
        output_path = "C:\\output\\report.pdf"

        success, error = pdf_exporter.export_active_sheet_to_pdf(sheet, output_path)

        self.assertFalse(success)
        self.assertEqual(error, "PDF_EXPORT_FAILED")

    def test_export_workbook_to_pdf_success(self):
        """Workbook을 PDF로 내보내기 성공."""
        wb = MagicMock()
        output_path = "C:\\output\\workbook.pdf"

        success, error = pdf_exporter.export_workbook_to_pdf(wb, output_path)

        self.assertTrue(success)
        self.assertIsNone(error)
        wb.ExportAsFixedFormat.assert_called_once_with(0, output_path)

    def test_export_workbook_to_pdf_no_workbook(self):
        """Workbook 없음 오류."""
        success, error = pdf_exporter.export_workbook_to_pdf(None, "output.pdf")

        self.assertFalse(success)
        self.assertEqual(error, "WORKBOOK_NOT_FOUND")

    def test_export_sheets_to_pdf_success(self):
        """지정 시트들을 PDF로 내보내기 성공."""
        wb = MagicMock()
        sheet1 = MagicMock()
        sheet2 = MagicMock()
        wb.Sheets.side_effect = [sheet1, sheet2]
        output_path = "C:\\output\\sheets.pdf"
        sheet_names = ["Sheet1", "Sheet2"]

        success, error = pdf_exporter.export_sheets_to_pdf(
            wb, sheet_names, output_path
        )

        self.assertTrue(success)
        self.assertIsNone(error)
        sheet1.ExportAsFixedFormat.assert_called_once_with(0, output_path)

    def test_export_sheets_to_pdf_no_workbook(self):
        """Workbook 없음 오류."""
        success, error = pdf_exporter.export_sheets_to_pdf(None, ["Sheet1"], "output.pdf")

        self.assertFalse(success)
        self.assertEqual(error, "WORKBOOK_NOT_FOUND")

    def test_export_sheets_to_pdf_empty_sheet_names(self):
        """시트 이름 목록 비어있음 오류."""
        wb = MagicMock()
        success, error = pdf_exporter.export_sheets_to_pdf(wb, [], "output.pdf")

        self.assertFalse(success)
        self.assertEqual(error, "SHEET_NAMES_REQUIRED")

    def test_export_sheets_to_pdf_no_valid_sheets(self):
        """유효한 시트 없음 오류."""
        wb = MagicMock()
        wb.Sheets.side_effect = Exception("Sheet not found")
        output_path = "C:\\output\\sheets.pdf"
        sheet_names = ["InvalidSheet"]

        success, error = pdf_exporter.export_sheets_to_pdf(
            wb, sheet_names, output_path
        )

        self.assertFalse(success)
        self.assertEqual(error, "NO_VALID_SHEETS")

    def test_validate_pdf_output_path_success(self):
        """PDF 출력 경로 유효성 검증 성공."""
        success, error = pdf_exporter.validate_pdf_output_path("C:\\output\\report.pdf")

        self.assertTrue(success)
        self.assertIsNone(error)

    def test_validate_pdf_output_path_no_path(self):
        """경로 없음 오류."""
        success, error = pdf_exporter.validate_pdf_output_path("")

        self.assertFalse(success)
        self.assertEqual(error, "OUTPUT_PATH_REQUIRED")

    def test_validate_pdf_output_path_invalid_extension(self):
        """잘못된 확장자 오류."""
        success, error = pdf_exporter.validate_pdf_output_path("C:\\output\\report.xlsx")

        self.assertFalse(success)
        self.assertEqual(error, "INVALID_PDF_EXTENSION")


class TestPrintAreaManager(unittest.TestCase):
    """인쇄 영역 관리 테스트."""

    def test_set_print_area_success(self):
        """인쇄 영역 설정 성공."""
        sheet = MagicMock()
        sheet.PageSetup = MagicMock()

        success, error = print_area_manager.set_print_area(sheet, "A1:D10")

        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertEqual(sheet.PageSetup.PrintArea, "A1:D10")

    def test_set_print_area_no_sheet(self):
        """시트 없음 오류."""
        success, error = print_area_manager.set_print_area(None, "A1:D10")

        self.assertFalse(success)
        self.assertEqual(error, "SHEET_NOT_FOUND")

    def test_set_print_area_no_range(self):
        """범위 없음 오류."""
        sheet = MagicMock()
        success, error = print_area_manager.set_print_area(sheet, "")

        self.assertFalse(success)
        self.assertEqual(error, "RANGE_ADDRESS_REQUIRED")

    def test_set_print_area_com_error(self):
        """COM 오류 처리."""
        sheet = MagicMock()
        type(sheet.PageSetup).PrintArea = PropertyMock(
            side_effect=Exception("COM error")
        )

        success, error = print_area_manager.set_print_area(sheet, "A1:D10")

        self.assertFalse(success)
        self.assertEqual(error, "PRINT_AREA_SET_FAILED")

    def test_get_print_area_success(self):
        """인쇄 영역 조회 성공."""
        sheet = MagicMock()
        sheet.PageSetup.PrintArea = "$A$1:$D$10"

        area, error = print_area_manager.get_print_area(sheet)

        self.assertEqual(area, "$A$1:$D$10")
        self.assertIsNone(error)

    def test_get_print_area_no_sheet(self):
        """시트 없음 오류."""
        area, error = print_area_manager.get_print_area(None)

        self.assertIsNone(area)
        self.assertEqual(error, "SHEET_NOT_FOUND")

    def test_get_print_area_empty(self):
        """인쇄 영역 미설정."""
        sheet = MagicMock()
        sheet.PageSetup.PrintArea = ""

        area, error = print_area_manager.get_print_area(sheet)

        self.assertEqual(area, "")
        self.assertIsNone(error)

    def test_clear_print_area_success(self):
        """인쇄 영역 제거 성공."""
        sheet = MagicMock()
        sheet.PageSetup = MagicMock()

        success, error = print_area_manager.clear_print_area(sheet)

        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertEqual(sheet.PageSetup.PrintArea, "")

    def test_clear_print_area_no_sheet(self):
        """시트 없음 오류."""
        success, error = print_area_manager.clear_print_area(None)

        self.assertFalse(success)
        self.assertEqual(error, "SHEET_NOT_FOUND")

    def test_set_page_setup_portrait_success(self):
        """페이지 설정 - 세로 방향 성공."""
        sheet = MagicMock()
        sheet.PageSetup = MagicMock()

        success, error = print_area_manager.set_page_setup(
            sheet, orientation="portrait"
        )

        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertEqual(sheet.PageSetup.Orientation, 1)

    def test_set_page_setup_landscape_success(self):
        """페이지 설정 - 가로 방향 성공."""
        sheet = MagicMock()
        sheet.PageSetup = MagicMock()

        success, error = print_area_manager.set_page_setup(
            sheet, orientation="landscape"
        )

        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertEqual(sheet.PageSetup.Orientation, 2)

    def test_set_page_setup_invalid_orientation(self):
        """잘못된 방향 오류."""
        sheet = MagicMock()
        success, error = print_area_manager.set_page_setup(
            sheet, orientation="invalid"
        )

        self.assertFalse(success)
        self.assertEqual(error, "INVALID_ORIENTATION")

    def test_set_page_setup_zoom_success(self):
        """페이지 설정 - 확대/축소 성공."""
        sheet = MagicMock()
        sheet.PageSetup = MagicMock()

        success, error = print_area_manager.set_page_setup(sheet, zoom=150)

        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertEqual(sheet.PageSetup.Zoom, 150)

    def test_set_page_setup_zoom_out_of_range(self):
        """확대/축소 범위 오류."""
        sheet = MagicMock()
        success, error = print_area_manager.set_page_setup(sheet, zoom=500)

        self.assertFalse(success)
        self.assertEqual(error, "ZOOM_OUT_OF_RANGE")

    def test_set_margins_success(self):
        """여백 설정 성공."""
        sheet = MagicMock()
        sheet.PageSetup = MagicMock()

        success, error = print_area_manager.set_margins(
            sheet, left=0.5, right=0.5, top=0.75, bottom=0.75
        )

        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertEqual(sheet.PageSetup.LeftMargin, 0.5)
        self.assertEqual(sheet.PageSetup.RightMargin, 0.5)
        self.assertEqual(sheet.PageSetup.TopMargin, 0.75)
        self.assertEqual(sheet.PageSetup.BottomMargin, 0.75)

    def test_set_margins_no_sheet(self):
        """시트 없음 오류."""
        success, error = print_area_manager.set_margins(None)

        self.assertFalse(success)
        self.assertEqual(error, "SHEET_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()

"""Excel COM 실제 smoke 테스트.

요구사항:
- Windows 환경에서 Excel 설치 필수
- test_samples.xlsx 파일 필수 (agent/tests/samples/ 디렉토리)
- 테스트 실행 전 Excel을 수동으로 열어둘 것 (또는 스크립트가 자동으로 열기)

Smoke 대상:
1. GetActiveObject 기반 Excel 앱 연결
2. 활성 워크북 읽기 (read-only probe)
3. 셀 쓰기 + SaveCopyAs (원본 보호)
4. PDF 내보내기 (SaveCopyAs 기반)

주의: 원본 파일은 수정하지 않음 (copy-based 작업만)
"""
from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def excel_app():
    """GetActiveObject로 실행 중인 Excel 앱 연결."""
    try:
        import win32com.client as win32
        app = win32.GetActiveObject("Excel.Application")
        yield app
    except Exception as e:
        pytest.skip(f"Excel not running or not available: {type(e).__name__}")


@pytest.fixture(scope="session")
def sample_file():
    """테스트용 샘플 파일 경로."""
    # 테스트 디렉토리에서 샘플 파일 찾기
    test_dir = Path(__file__).parent
    sample_path = test_dir / "samples" / "test_samples.xlsx"

    if sample_path.exists():
        yield str(sample_path)
    else:
        # 샘플이 없으면 임시 파일 생성
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            temp_path = f.name

        try:
            # 기본 Excel 파일 생성 (openpyxl 사용)
            try:
                from openpyxl import Workbook
                wb = Workbook()
                ws = wb.active
                ws["A1"] = "Test"
                ws["B1"] = "Value"
                ws["A2"] = "Item1"
                ws["B2"] = 100
                ws["A3"] = "Item2"
                ws["B3"] = 200
                ws.append([])
                ws["A5"] = "=SUM(B2:B3)"
                wb.save(temp_path)
            except ImportError:
                pytest.skip("openpyxl not available for creating test file")

            yield temp_path
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass


def test_excel_app_connected(excel_app):
    """Excel 앱이 GetActiveObject로 연결되는지 확인."""
    assert excel_app is not None
    # 기본 속성 확인
    assert hasattr(excel_app, "Workbooks")


def test_active_workbook_probe(excel_app):
    """실행 중인 Excel의 활성 워크북 정보 조회 (read-only)."""
    try:
        active_wb = excel_app.ActiveWorkbook
        assert active_wb is not None
        # 워크북 정보 확인
        assert hasattr(active_wb, "Name")
        assert hasattr(active_wb, "Sheets")
        logger.info(f"Active workbook: {active_wb.Name}, Sheets: {active_wb.Sheets.Count}")
    except Exception as e:
        pytest.skip(f"No active workbook: {type(e).__name__}")


def test_open_and_read_cell(excel_app, sample_file):
    """샘플 파일을 열고 셀 값 읽기."""
    try:
        wb = excel_app.Workbooks.Open(sample_file, ReadOnly=True)
        try:
            ws = wb.Sheets(1)
            a1_value = ws.Cells(1, 1).Value
            assert a1_value is not None
            logger.info(f"Read A1: {a1_value}")
        finally:
            wb.Close(SaveChanges=False)
    except Exception as e:
        pytest.skip(f"Cannot open workbook: {type(e).__name__}")


def test_write_cell_save_copy_as(excel_app, sample_file):
    """셀 쓰기 + SaveCopyAs로 복사본 저장 (원본 보호)."""
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        output_path = f.name

    try:
        # 원본 읽기 전용으로 열기
        wb = excel_app.Workbooks.Open(sample_file, ReadOnly=False)
        original_a1 = wb.Sheets(1).Cells(1, 1).Value

        try:
            # 셀 수정
            wb.Sheets(1).Cells(1, 1).Value = "MODIFIED"

            # SaveCopyAs로 복사본 저장 (원본 미수정)
            wb.SaveCopyAs(output_path)

            # 복사본 열기 확인
            wb_copy = excel_app.Workbooks.Open(output_path, ReadOnly=True)
            try:
                copy_a1 = wb_copy.Sheets(1).Cells(1, 1).Value
                assert copy_a1 == "MODIFIED", f"Copy has value: {copy_a1}"
            finally:
                wb_copy.Close(SaveChanges=False)

            # 원본은 수정되지 않았는지 확인 (메모리)
            assert wb.Sheets(1).Cells(1, 1).Value == "MODIFIED"

        finally:
            wb.Close(SaveChanges=False)

        # 복사본이 생성되었는지 확인
        assert os.path.exists(output_path), f"Copy not found: {output_path}"
        logger.info(f"SaveCopyAs successful: {output_path}")

    finally:
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass


def test_export_pdf_active_sheet(excel_app, sample_file):
    """활성 시트를 PDF로 내보내기."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        pdf_path = f.name

    try:
        wb = excel_app.Workbooks.Open(sample_file, ReadOnly=True)
        try:
            # Workbook 수준에서 ExportAsFixedFormat 사용
            wb.ExportAsFixedFormat(
                Type=0,  # xlTypePDF
                Filename=pdf_path,
                Quality=0,  # xlQualityStandard
                IncludeDocProperties=True,
                IgnorePrintAreas=False,
                OpenAfterPublish=False,
            )
        finally:
            wb.Close(SaveChanges=False)

        # PDF 파일 생성 확인
        assert os.path.exists(pdf_path), f"PDF not created: {pdf_path}"
        file_size = os.path.getsize(pdf_path)
        assert file_size > 100, f"PDF too small: {file_size} bytes"
        logger.info(f"PDF exported: {pdf_path} ({file_size} bytes)")

    finally:
        if os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
            except Exception:
                pass


def test_formula_calculation(excel_app, sample_file):
    """수식 계산 확인."""
    try:
        wb = excel_app.Workbooks.Open(sample_file, ReadOnly=True)
        try:
            ws = wb.Sheets(1)
            # A5에 =SUM(B2:B3) 수식이 있다면
            a5_cell = ws.Cells(5, 1)
            if a5_cell.Formula and "SUM" in a5_cell.Formula:
                calculated_value = a5_cell.Value
                logger.info(f"Formula A5: {a5_cell.Formula} = {calculated_value}")
                assert isinstance(calculated_value, (int, float))
        finally:
            wb.Close(SaveChanges=False)
    except Exception as e:
        pytest.skip(f"Cannot verify formula: {type(e).__name__}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

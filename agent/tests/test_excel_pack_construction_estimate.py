"""건설 내역서 팩 테스트."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from agent.excel.packs import construction_estimate, settlement_review, material_price_check


class TestConstructionEstimate(unittest.TestCase):
    """내역서 분석 및 검토 테스트."""

    def test_analyze_estimate_sheet_success(self):
        """내역서 시트 분석 성공."""
        sheet = MagicMock()
        sheet.UsedRange.Rows.Count = 50
        sheet.Cells.return_value.Value = "품명"

        success, error, result = construction_estimate.analyze_estimate_sheet(sheet)

        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertEqual(result["total_rows"], 50)

    def test_analyze_estimate_sheet_no_sheet(self):
        """시트 없음 오류."""
        success, error, result = construction_estimate.analyze_estimate_sheet(None)

        self.assertFalse(success)
        self.assertEqual(error, "SHEET_NOT_FOUND")
        self.assertEqual(result, {})

    def test_map_estimate_columns_success(self):
        """내역서 열 매핑 성공."""
        sheet = MagicMock()
        sheet.UsedRange.Columns.Count = 10

        def cell_value(row, col):
            if col == 1:
                return "품명"
            elif col == 2:
                return "규격"
            elif col == 3:
                return "수량"
            elif col == 4:
                return "단가"
            elif col == 5:
                return "금액"
            return None

        sheet.Cells.return_value.Value = None

        def cells(row, col):
            cell = MagicMock()
            cell.Value = cell_value(row, col)
            return cell

        sheet.Cells = cells

        success, error, mapping = construction_estimate.map_estimate_columns(sheet, 1)

        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertEqual(mapping["item_name"], 1)
        self.assertEqual(mapping["spec"], 2)
        self.assertEqual(mapping["quantity"], 3)
        self.assertEqual(mapping["unit_price"], 4)
        self.assertEqual(mapping["amount"], 5)

    def test_map_estimate_columns_no_sheet(self):
        """시트 없음 오류."""
        success, error, mapping = construction_estimate.map_estimate_columns(None, 1)

        self.assertFalse(success)
        self.assertEqual(error, "SHEET_NOT_FOUND")

    def test_validate_estimate_amounts_success(self):
        """금액 검증 성공."""
        sheet = MagicMock()

        def cells(row, col):
            cell = MagicMock()
            if col == 1:  # quantity
                cell.Value = 10.0
            elif col == 2:  # unit_price
                cell.Value = 100.0
            elif col == 3:  # amount
                cell.Value = 1000.0
            return cell

        sheet.Cells = cells

        success, error, results = construction_estimate.validate_estimate_amounts(
            sheet, amount_col=3, quantity_col=1, unit_price_col=2, data_start=2, data_end=5
        )

        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertTrue(len(results) > 0)

    def test_validate_estimate_amounts_no_sheet(self):
        """시트 없음 오류."""
        success, error, results = construction_estimate.validate_estimate_amounts(
            None, 1, 2, 3, 2, 5
        )

        self.assertFalse(success)
        self.assertEqual(error, "SHEET_NOT_FOUND")

    def test_detect_price_anomalies_success(self):
        """단가 이상치 감지 성공."""
        sheet = MagicMock()

        def cells(row, col):
            cell = MagicMock()
            if row == 2:
                cell.Value = 100.0
            elif row == 3:
                cell.Value = 110.0
            elif row == 4:
                cell.Value = 1000.0  # 이상치
            else:
                cell.Value = 105.0
            return cell

        sheet.Cells = cells

        success, error, results = construction_estimate.detect_price_anomalies(
            sheet, unit_price_col=1, data_start=2, data_end=5
        )

        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertTrue(len(results) > 0)

    def test_detect_missing_quantities_success(self):
        """수량 누락 감지 성공."""
        sheet = MagicMock()

        def cells(row, col):
            cell = MagicMock()
            if col == 1:  # item
                cell.Value = f"Item{row}" if row != 3 else "Item3"
            elif col == 2:  # quantity
                cell.Value = 10.0 if row != 3 else None  # row 3은 누락
            return cell

        sheet.Cells = cells

        success, error, results = construction_estimate.detect_missing_quantities(
            sheet, item_col=1, quantity_col=2, data_start=2, data_end=5
        )

        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertTrue(len(results) > 0)

    def test_detect_duplicate_items_success(self):
        """중복 품목 감지 성공."""
        sheet = MagicMock()

        def cells(row, col):
            cell = MagicMock()
            if col == 1:  # item
                cell.Value = "ItemA" if row <= 3 else "ItemB"
            elif col == 2:  # spec
                cell.Value = "TypeX"
            return cell

        sheet.Cells = cells

        success, error, results = construction_estimate.detect_duplicate_items(
            sheet, item_col=1, spec_col=2, data_start=2, data_end=5
        )

        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertTrue(len(results) > 0)

    def test_generate_estimate_review_success(self):
        """검토결과 생성 성공."""
        analysis = {"total_items": 10}
        amount_validation = [
            {"issue": None},
            {"issue": "AMOUNT_MISMATCH"},
        ]
        price_anomalies = [
            {"is_anomaly": False},
            {"is_anomaly": True},
        ]
        missing_quantities = [
            {"is_missing": False},
        ]
        duplicate_items = [
            {"is_duplicate": False},
            {"is_duplicate": True},
        ]

        success, error, result = construction_estimate.generate_estimate_review(
            analysis, amount_validation, price_anomalies, missing_quantities, duplicate_items
        )

        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertEqual(result["total_items"], 2)
        self.assertEqual(result["validation_issues"], 1)
        self.assertEqual(result["price_anomalies"], 1)
        self.assertEqual(result["duplicate_items"], 1)


class TestSettlementReview(unittest.TestCase):
    """정산서 검토 테스트."""

    def test_analyze_settlement_sheet_success(self):
        """정산서 시트 분석 성공."""
        sheet = MagicMock()
        sheet.UsedRange.Rows.Count = 30
        sheet.Cells.return_value.Value = "항목"

        success, error, result = settlement_review.analyze_settlement_sheet(sheet)

        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertEqual(result["total_rows"], 30)

    def test_detect_settlement_issues_success(self):
        """정산 이슈 감지 성공."""
        sheet = MagicMock()

        def cells(row, col):
            cell = MagicMock()
            if col == 1:  # claim
                cell.Value = 1000.0
            elif col == 2:  # actual
                cell.Value = 950.0 if row != 3 else 500.0  # row 3은 큰 차이
            return cell

        sheet.Cells = cells

        success, error, results = settlement_review.detect_settlement_issues(
            sheet, claim_col=1, actual_col=2, data_start=2, data_end=5
        )

        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertTrue(len(results) > 0)

    def test_generate_settlement_report_success(self):
        """정산서 보고서 생성 성공."""
        analysis = {}
        settlement_issues = [
            {"claim": 1000, "actual": 950, "is_issue": False},
            {"claim": 1000, "actual": 500, "is_issue": True},
        ]

        success, error, result = settlement_review.generate_settlement_report(
            analysis, settlement_issues
        )

        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertEqual(result["total_items"], 2)
        self.assertEqual(result["discrepancy_items"], 1)


class TestMaterialPriceCheck(unittest.TestCase):
    """자재 단가 검증 테스트."""

    def test_analyze_material_prices_success(self):
        """자재 단가 분석 성공."""
        sheet = MagicMock()

        def cells(row, col):
            cell = MagicMock()
            if col == 1:  # material
                cell.Value = "ConcreteA" if row <= 3 else "ConcreteB"
            elif col == 2:  # price
                cell.Value = 100.0 if row <= 3 else 105.0
            return cell

        sheet.Cells = cells

        success, error, result = material_price_check.analyze_material_prices(
            sheet, material_col=1, unit_price_col=2, data_start=2, data_end=5
        )

        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertIn("unique_materials", result)

    def test_check_price_consistency_success(self):
        """단가 일관성 검사 성공."""
        sheet = MagicMock()

        def cells(row, col):
            cell = MagicMock()
            if col == 1:  # material
                cell.Value = "MaterialA" if row <= 3 else "MaterialB"
            elif col == 2:  # price
                cell.Value = 100.0
            return cell

        sheet.Cells = cells

        success, error, results = material_price_check.check_price_consistency(
            sheet, material_col=1, unit_price_col=2, data_start=2, data_end=5
        )

        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertTrue(len(results) > 0)

    def test_detect_price_outliers_success(self):
        """가격 이상치 감지 성공."""
        sheet = MagicMock()

        def cells(row, col):
            cell = MagicMock()
            if row == 2:
                cell.Value = 100.0
            elif row == 3:
                cell.Value = 105.0
            elif row == 4:
                cell.Value = 1000.0  # 이상치
            else:
                cell.Value = 102.0
            return cell

        sheet.Cells = cells

        success, error, results = material_price_check.detect_price_outliers(
            sheet, unit_price_col=1, data_start=2, data_end=5
        )

        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertTrue(len(results) > 0)


if __name__ == "__main__":
    unittest.main()

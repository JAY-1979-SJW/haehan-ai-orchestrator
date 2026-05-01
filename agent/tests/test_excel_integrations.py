"""Excel 통합 어댑터 테스트."""
from __future__ import annotations

import unittest

from agent.excel.integrations import (
    MaterialDBRecord,
    match_materials_with_estimate,
    detect_unmatched_items,
    generate_material_matching_report,
    CADTakeoffData,
    match_cad_quantity_with_estimate,
    detect_quantity_discrepancies,
    generate_cad_integration_report,
    BidAnalysisRecord,
    match_bid_results_with_estimate,
    detect_price_deviations,
    generate_bid_analysis_report,
)


class TestMaterialDBAdapter(unittest.TestCase):
    """자재 DB 어댑터 테스트."""

    def test_material_db_record_creation(self):
        """자재 DB 레코드 생성."""
        record = MaterialDBRecord(
            id="MAT001",
            name="콘크리트",
            spec="보통강도",
            unit="m3",
            standard_price=100000,
            supplier="건설자재사",
        )

        self.assertEqual(record.id, "MAT001")
        self.assertEqual(record.name, "콘크리트")
        self.assertEqual(record.standard_price, 100000)

    def test_material_db_record_from_dict(self):
        """딕셔너리에서 레코드 생성."""
        data = {
            "id": "MAT002",
            "name": "철근",
            "spec": "D16",
            "unit": "ton",
            "standard_price": 500000,
        }
        record = MaterialDBRecord.from_dict(data)

        self.assertEqual(record.id, "MAT002")
        self.assertEqual(record.name, "철근")

    def test_match_materials_with_estimate_success(self):
        """자재 매칭 성공."""
        estimate_items = [
            {"row": 2, "item_name": "콘크리트", "spec": "보통강도"},
            {"row": 3, "item_name": "철근", "spec": "D16"},
        ]
        material_db = [
            MaterialDBRecord(
                id="MAT001", name="콘크리트", spec="보통강도", unit="m3", standard_price=100000
            ),
            MaterialDBRecord(
                id="MAT002", name="철근", spec="D16", unit="ton", standard_price=500000
            ),
        ]

        results = match_materials_with_estimate(estimate_items, material_db)

        self.assertEqual(len(results), 2)
        self.assertTrue(results[0]["matched"])
        self.assertTrue(results[1]["matched"])

    def test_detect_unmatched_items(self):
        """미매칭 품목 감지."""
        matching_results = [
            {"estimate_row": 2, "estimate_item": "콘크리트", "matched": True},
            {
                "estimate_row": 3,
                "estimate_item": "미상품목",
                "matched": False,
                "similarity": 0,
            },
        ]

        unmatched = detect_unmatched_items(matching_results)

        self.assertEqual(len(unmatched), 1)
        self.assertEqual(unmatched[0]["estimate_item"], "미상품목")

    def test_generate_material_matching_report(self):
        """매칭 보고서 생성."""
        matching_results = [
            {"matched": True},
            {"matched": True},
            {"matched": False},
        ]
        unmatched_items = [{"estimate_item": "미상품목"}]

        report = generate_material_matching_report(matching_results, unmatched_items)

        self.assertEqual(report["total_items"], 3)
        self.assertEqual(report["matched_count"], 2)
        self.assertEqual(report["unmatched_count"], 1)


class TestCADTakeoffAdapter(unittest.TestCase):
    """CAD 산출 어댑터 테스트."""

    def test_cad_takeoff_data_creation(self):
        """CAD 산출 데이터 생성."""
        data = CADTakeoffData(
            item_id="CAD001",
            description="콘크리트 기초",
            quantity=50,
            unit="m3",
            drawing_ref="A-101",
        )

        self.assertEqual(data.item_id, "CAD001")
        self.assertEqual(data.quantity, 50)
        self.assertEqual(data.unit, "m3")

    def test_match_cad_quantity_with_estimate(self):
        """CAD 수량 매칭."""
        estimate_items = [
            {"row": 2, "item_name": "콘크리트", "quantity": 50, "unit": "m3"},
        ]
        cad_data = [
            CADTakeoffData(
                item_id="CAD001",
                description="콘크리트 기초",
                quantity=50,
                unit="m3",
            ),
        ]

        results = match_cad_quantity_with_estimate(estimate_items, cad_data)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["matched"])
        self.assertEqual(results[0]["quantity_diff"], 0)

    def test_detect_quantity_discrepancies(self):
        """수량 차이 감지."""
        matching_results = [
            {
                "estimate_row": 2,
                "estimate_item": "콘크리트",
                "estimate_qty": 50,
                "cad_qty": 55,
                "matched": True,
            },
            {
                "estimate_row": 3,
                "estimate_item": "철근",
                "estimate_qty": 100,
                "cad_qty": 100,
                "matched": True,
            },
        ]

        discrepancies = detect_quantity_discrepancies(matching_results, threshold=0.05)

        self.assertEqual(len(discrepancies), 1)
        self.assertEqual(discrepancies[0]["estimate_item"], "콘크리트")

    def test_generate_cad_integration_report(self):
        """CAD 통합 보고서 생성."""
        matching_results = [
            {"matched": True},
            {"matched": True},
            {"matched": False},
        ]
        discrepancies = [{"difference": 5}]

        report = generate_cad_integration_report(matching_results, discrepancies)

        self.assertEqual(report["total_items"], 3)
        self.assertEqual(report["matched_count"], 2)
        self.assertEqual(report["discrepancy_count"], 1)


class TestBidAnalysisAdapter(unittest.TestCase):
    """입찰 분석 어댑터 테스트."""

    def test_bid_analysis_record_creation(self):
        """입찰 분석 레코드 생성."""
        record = BidAnalysisRecord(
            bid_id="BID001",
            item_description="콘크리트",
            bid_price=95000,
            winning_price=100000,
            bid_count=5,
        )

        self.assertEqual(record.bid_id, "BID001")
        self.assertEqual(record.winning_price, 100000)

    def test_match_bid_results_with_estimate(self):
        """입찰 결과 매칭."""
        estimate_items = [
            {"row": 2, "item_name": "콘크리트", "unit_price": 90000},
        ]
        bid_data = [
            BidAnalysisRecord(
                bid_id="BID001",
                item_description="콘크리트",
                bid_price=95000,
                winning_price=100000,
                bid_count=5,
            ),
        ]

        results = match_bid_results_with_estimate(estimate_items, bid_data)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["matched"])
        self.assertEqual(results[0]["price_competitiveness"], "COMPETITIVE")

    def test_detect_price_deviations(self):
        """가격 편차 감지."""
        matching_results = [
            {
                "estimate_row": 2,
                "estimate_item": "콘크리트",
                "estimate_price": 120000,
                "winning_price": 100000,
                "matched": True,
            },
            {
                "estimate_row": 3,
                "estimate_item": "철근",
                "estimate_price": 500000,
                "winning_price": 500000,
                "matched": True,
            },
        ]

        deviations = detect_price_deviations(matching_results, deviation_threshold=0.15)

        self.assertEqual(len(deviations), 1)
        self.assertEqual(deviations[0]["direction"], "OVER")

    def test_generate_bid_analysis_report(self):
        """입찰 분석 보고서 생성."""
        matching_results = [
            {"price_competitiveness": "COMPETITIVE"},
            {"price_competitiveness": "MARKET_PRICE"},
            {"price_competitiveness": "ABOVE_MARKET"},
            {"price_competitiveness": "UNKNOWN"},
        ]
        price_deviations = [{"estimate_item": "고가품목"}]

        report = generate_bid_analysis_report(matching_results, price_deviations)

        self.assertEqual(report["total_items"], 4)
        self.assertEqual(report["competitive_count"], 1)
        self.assertEqual(report["market_price_count"], 1)
        self.assertEqual(report["above_market_count"], 1)
        self.assertEqual(report["deviation_count"], 1)


class TestIntegrationAdaptersDataConversion(unittest.TestCase):
    """어댑터 데이터 변환 테스트."""

    def test_material_record_to_dict(self):
        """자재 레코드를 딕셔너리로 변환."""
        record = MaterialDBRecord(
            id="MAT001",
            name="콘크리트",
            spec="보통강도",
            unit="m3",
            standard_price=100000,
        )
        data = record.to_dict()

        self.assertEqual(data["id"], "MAT001")
        self.assertEqual(data["standard_price"], 100000)

    def test_cad_data_to_dict(self):
        """CAD 데이터를 딕셔너리로 변환."""
        cad = CADTakeoffData(
            item_id="CAD001",
            description="기초",
            quantity=50,
            unit="m3",
        )
        data = cad.to_dict()

        self.assertEqual(data["item_id"], "CAD001")
        self.assertEqual(data["quantity"], 50)

    def test_bid_record_to_dict(self):
        """입찰 레코드를 딕셔너리로 변환."""
        record = BidAnalysisRecord(
            bid_id="BID001",
            item_description="콘크리트",
            bid_price=95000,
            winning_price=100000,
            bid_count=5,
        )
        data = record.to_dict()

        self.assertEqual(data["bid_id"], "BID001")
        self.assertEqual(data["winning_price"], 100000)


if __name__ == "__main__":
    unittest.main()

"""CAD 산출 결과 연동 어댑터 (실제 CAD 수정 없음)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CADTakeoffData:
    """CAD 산출 데이터 스키마.

    Attributes:
        item_id: 항목 고유 ID (CAD 내)
        description: 항목 설명
        quantity: 산출 수량
        unit: 단위 (m, m2, m3, EA 등)
        drawing_ref: 도면 참조 (예: A-101)
        extraction_date: 산출 일자
        confidence: 신뢰도 (0.0~1.0)
    """

    item_id: str
    description: str
    quantity: float
    unit: str
    drawing_ref: Optional[str] = None
    extraction_date: Optional[str] = None
    confidence: float = 1.0

    @classmethod
    def from_dict(cls, data: dict) -> CADTakeoffData:
        """딕셔너리에서 데이터 생성."""
        return cls(
            item_id=data.get("item_id", ""),
            description=data.get("description", ""),
            quantity=float(data.get("quantity", 0)),
            unit=data.get("unit", ""),
            drawing_ref=data.get("drawing_ref"),
            extraction_date=data.get("extraction_date"),
            confidence=float(data.get("confidence", 1.0)),
        )

    def to_dict(self) -> dict:
        """딕셔너리로 변환."""
        return {
            "item_id": self.item_id,
            "description": self.description,
            "quantity": self.quantity,
            "unit": self.unit,
            "drawing_ref": self.drawing_ref,
            "extraction_date": self.extraction_date,
            "confidence": self.confidence,
        }


def match_cad_quantity_with_estimate(
    estimate_items: list[dict], cad_data: list[CADTakeoffData]
) -> list[dict]:
    """CAD 산출 수량과 내역서 수량 매칭.

    Args:
        estimate_items: [{"row": int, "item_name": str, "quantity": float, "unit": str}, ...]
        cad_data: [CADTakeoffData, ...]

    Returns:
        [
            {
                "estimate_row": int,
                "estimate_item": str,
                "estimate_qty": float,
                "estimate_unit": str,
                "matched": bool,
                "cad_id": str | None,
                "cad_description": str | None,
                "cad_qty": float | None,
                "cad_unit": str | None,
                "quantity_diff": float | None,
            },
            ...
        ]
    """
    try:
        results = []

        for estimate_item in estimate_items:
            row = estimate_item.get("row")
            item_name = str(estimate_item.get("item_name", "")).strip().lower()
            item_qty = estimate_item.get("quantity")
            item_unit = estimate_item.get("unit", "").lower()

            best_match = None
            best_match_diff = float("inf")

            for cad_item in cad_data:
                cad_desc = cad_item.description.lower()
                cad_unit = cad_item.unit.lower()

                # 설명과 단위가 비슷한지 확인
                if item_name in cad_desc or cad_desc in item_name:
                    if item_unit == cad_unit or not item_unit:
                        qty_diff = abs(cad_item.quantity - (item_qty or 0))
                        if qty_diff < best_match_diff:
                            best_match_diff = qty_diff
                            best_match = cad_item

            matched = best_match is not None
            quantity_diff = best_match_diff if best_match_diff != float("inf") else None

            results.append({
                "estimate_row": row,
                "estimate_item": estimate_item.get("item_name"),
                "estimate_qty": item_qty,
                "estimate_unit": estimate_item.get("unit"),
                "matched": matched,
                "cad_id": best_match.item_id if best_match else None,
                "cad_description": best_match.description if best_match else None,
                "cad_qty": best_match.quantity if best_match else None,
                "cad_unit": best_match.unit if best_match else None,
                "quantity_diff": round(quantity_diff, 2) if quantity_diff is not None else None,
            })

        return results
    except Exception as e:  # noqa: BLE001
        logger.error("CAD matching failed: %s", type(e).__name__)
        return []


def detect_quantity_discrepancies(
    matching_results: list[dict], threshold: float = 0.1
) -> list[dict]:
    """수량 차이가 임계값을 초과하는 항목 감지.

    Args:
        matching_results: CAD 매칭 결과
        threshold: 차이 임계값 (기본 10%)

    Returns:
        [
            {
                "estimate_row": int,
                "estimate_item": str,
                "estimate_qty": float,
                "cad_qty": float,
                "difference": float,
                "percentage": float,
            },
            ...
        ]
    """
    try:
        discrepancies = []

        for result in matching_results:
            if result.get("matched"):
                estimate_qty = result.get("estimate_qty") or 0
                cad_qty = result.get("cad_qty") or 0

                if estimate_qty > 0:
                    percentage = abs(cad_qty - estimate_qty) / estimate_qty
                    if percentage > threshold:
                        discrepancies.append({
                            "estimate_row": result.get("estimate_row"),
                            "estimate_item": result.get("estimate_item"),
                            "estimate_qty": estimate_qty,
                            "cad_qty": cad_qty,
                            "difference": round(cad_qty - estimate_qty, 2),
                            "percentage": round(percentage * 100, 1),
                        })

        return discrepancies
    except Exception as e:  # noqa: BLE001
        logger.error("Discrepancy detection failed: %s", type(e).__name__)
        return []


def generate_cad_integration_report(
    matching_results: list[dict], discrepancies: list[dict]
) -> dict:
    """CAD 통합 검토 보고서 생성.

    Returns:
        {
            "total_items": int,
            "matched_count": int,
            "discrepancy_count": int,
            "match_rate": float,
            "avg_difference": float,
            "summary": [...]
        }
    """
    try:
        total_items = len(matching_results)
        matched_count = len([m for m in matching_results if m.get("matched")])
        discrepancy_count = len(discrepancies)
        match_rate = (matched_count / total_items * 100) if total_items > 0 else 0

        avg_difference = 0.0
        if discrepancies:
            avg_difference = sum([abs(d.get("difference", 0)) for d in discrepancies]) / len(
                discrepancies
            )

        summary = [
            f"총 항목: {total_items}개",
            f"CAD 매칭: {matched_count}개",
            f"수량 차이: {discrepancy_count}개",
            f"매칭율: {match_rate:.1f}%",
            f"평균 차이: {avg_difference:.2f}",
        ]

        return {
            "total_items": total_items,
            "matched_count": matched_count,
            "discrepancy_count": discrepancy_count,
            "match_rate": round(match_rate, 1),
            "avg_difference": round(avg_difference, 2),
            "summary": summary,
        }
    except Exception as e:  # noqa: BLE001
        logger.error("CAD report generation failed: %s", type(e).__name__)
        return {}

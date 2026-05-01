"""자재 DB 연동 어댑터 (실제 DB write 없음)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class MaterialDBRecord:
    """자재 DB 레코드 스키마.

    Attributes:
        id: 자재 고유 ID
        name: 자재명
        spec: 규격/사양
        unit: 단위 (m, m2, m3, EA 등)
        standard_price: 표준 단가
        supplier: 공급업체
        last_updated: 마지막 갱신일
    """

    id: str
    name: str
    spec: str
    unit: str
    standard_price: float
    supplier: Optional[str] = None
    last_updated: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> MaterialDBRecord:
        """딕셔너리에서 레코드 생성."""
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            spec=data.get("spec", ""),
            unit=data.get("unit", ""),
            standard_price=float(data.get("standard_price", 0)),
            supplier=data.get("supplier"),
            last_updated=data.get("last_updated"),
        )

    def to_dict(self) -> dict:
        """딕셔너리로 변환."""
        return {
            "id": self.id,
            "name": self.name,
            "spec": self.spec,
            "unit": self.unit,
            "standard_price": self.standard_price,
            "supplier": self.supplier,
            "last_updated": self.last_updated,
        }


def match_materials_with_estimate(
    estimate_items: list[dict], material_db: list[MaterialDBRecord], similarity_threshold: float = 0.7
) -> list[dict]:
    """내역서 품목과 자재 DB 매칭.

    Args:
        estimate_items: [{"row": int, "item_name": str, "spec": str}, ...]
        material_db: [MaterialDBRecord, ...]
        similarity_threshold: 매칭 유사도 임계값 (0.0~1.0)

    Returns:
        [
            {
                "estimate_row": int,
                "estimate_item": str,
                "estimate_spec": str,
                "matched": bool,
                "db_id": str | None,
                "db_name": str | None,
                "db_spec": str | None,
                "db_price": float | None,
                "similarity": float,
            },
            ...
        ]
    """
    try:
        results = []

        for estimate_item in estimate_items:
            row = estimate_item.get("row")
            item_name = str(estimate_item.get("item_name", "")).strip().lower()
            item_spec = str(estimate_item.get("spec", "")).strip().lower()

            best_match = None
            best_similarity = 0.0

            for db_record in material_db:
                db_name = db_record.name.lower()
                db_spec = db_record.spec.lower() if db_record.spec else ""

                # 간단한 문자열 매칭 (정규식 기반 유사도는 추후 고도화)
                name_match = 1.0 if item_name in db_name or db_name in item_name else 0.0
                spec_match = 1.0 if (not item_spec or item_spec in db_spec or db_spec in item_spec) else 0.0

                similarity = (name_match + spec_match) / 2

                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = db_record

            matched = best_similarity >= similarity_threshold

            results.append({
                "estimate_row": row,
                "estimate_item": estimate_item.get("item_name"),
                "estimate_spec": estimate_item.get("spec"),
                "matched": matched,
                "db_id": best_match.id if best_match else None,
                "db_name": best_match.name if best_match else None,
                "db_spec": best_match.spec if best_match else None,
                "db_price": best_match.standard_price if best_match else None,
                "similarity": round(best_similarity, 2),
            })

        return results
    except Exception as e:  # noqa: BLE001
        logger.error("Material matching failed: %s", type(e).__name__)
        return []


def detect_unmatched_items(
    matching_results: list[dict],
) -> list[dict]:
    """매칭되지 않은 품목 감지.

    Returns:
        [
            {
                "estimate_row": int,
                "estimate_item": str,
                "estimate_spec": str,
                "reason": str,
            },
            ...
        ]
    """
    try:
        unmatched = []

        for result in matching_results:
            if not result.get("matched"):
                unmatched.append({
                    "estimate_row": result.get("estimate_row"),
                    "estimate_item": result.get("estimate_item"),
                    "estimate_spec": result.get("estimate_spec"),
                    "reason": "DB_MATCH_NOT_FOUND" if result.get("similarity", 0) == 0
                    else "SIMILARITY_BELOW_THRESHOLD",
                })

        return unmatched
    except Exception as e:  # noqa: BLE001
        logger.error("Unmatched detection failed: %s", type(e).__name__)
        return []


def generate_material_matching_report(
    matching_results: list[dict], unmatched_items: list[dict]
) -> dict:
    """자재 매칭 검토 보고서 생성.

    Returns:
        {
            "total_items": int,
            "matched_count": int,
            "unmatched_count": int,
            "match_rate": float,
            "summary": [...]
        }
    """
    try:
        total_items = len(matching_results)
        matched_count = len([m for m in matching_results if m.get("matched")])
        unmatched_count = len(unmatched_items)
        match_rate = (matched_count / total_items * 100) if total_items > 0 else 0

        summary = [
            f"총 품목: {total_items}개",
            f"매칭됨: {matched_count}개",
            f"미매칭: {unmatched_count}개",
            f"매칭율: {match_rate:.1f}%",
        ]

        return {
            "total_items": total_items,
            "matched_count": matched_count,
            "unmatched_count": unmatched_count,
            "match_rate": round(match_rate, 1),
            "summary": summary,
        }
    except Exception as e:  # noqa: BLE001
        logger.error("Report generation failed: %s", type(e).__name__)
        return {}

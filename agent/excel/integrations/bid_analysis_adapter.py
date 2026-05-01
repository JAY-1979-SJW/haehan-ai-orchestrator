"""입찰 분석 결과 연동 어댑터 (실제 서버 호출 없음)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class BidAnalysisRecord:
    """입찰 분석 결과 레코드 스키마.

    Attributes:
        bid_id: 입찰 고유 ID
        item_description: 품목 설명
        bid_price: 입찰 단가
        winning_price: 낙찰 단가 (평균)
        bid_count: 입찰 건수
        percentile: 백분위 (낙찰가 대비 %)
        analysis_date: 분석 일자
    """

    bid_id: str
    item_description: str
    bid_price: float
    winning_price: float
    bid_count: int
    percentile: Optional[float] = None
    analysis_date: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> BidAnalysisRecord:
        """딕셔너리에서 레코드 생성."""
        return cls(
            bid_id=data.get("bid_id", ""),
            item_description=data.get("item_description", ""),
            bid_price=float(data.get("bid_price", 0)),
            winning_price=float(data.get("winning_price", 0)),
            bid_count=int(data.get("bid_count", 0)),
            percentile=float(data.get("percentile")) if data.get("percentile") else None,
            analysis_date=data.get("analysis_date"),
        )

    def to_dict(self) -> dict:
        """딕셔너리로 변환."""
        return {
            "bid_id": self.bid_id,
            "item_description": self.item_description,
            "bid_price": self.bid_price,
            "winning_price": self.winning_price,
            "bid_count": self.bid_count,
            "percentile": self.percentile,
            "analysis_date": self.analysis_date,
        }


def match_bid_results_with_estimate(
    estimate_items: list[dict], bid_data: list[BidAnalysisRecord]
) -> list[dict]:
    """입찰 분석 결과와 내역서 단가 매칭.

    Args:
        estimate_items: [{"row": int, "item_name": str, "unit_price": float}, ...]
        bid_data: [BidAnalysisRecord, ...]

    Returns:
        [
            {
                "estimate_row": int,
                "estimate_item": str,
                "estimate_price": float,
                "matched": bool,
                "bid_id": str | None,
                "bid_description": str | None,
                "bid_price": float | None,
                "winning_price": float | None,
                "percentile": float | None,
                "price_competitiveness": str,
            },
            ...
        ]
    """
    try:
        results = []

        for estimate_item in estimate_items:
            row = estimate_item.get("row")
            item_name = str(estimate_item.get("item_name", "")).strip().lower()
            item_price = estimate_item.get("unit_price")

            best_match = None
            best_similarity = 0.0

            for bid_item in bid_data:
                bid_desc = bid_item.item_description.lower()

                # 간단한 텍스트 매칭
                if item_name in bid_desc or bid_desc in item_name:
                    best_similarity = 1.0
                    best_match = bid_item
                    break

            matched = best_match is not None

            # 가격 경쟁력 평가
            price_competitiveness = "UNKNOWN"
            if matched and best_match.winning_price > 0 and item_price:
                price_ratio = item_price / best_match.winning_price
                if price_ratio < 0.95:
                    price_competitiveness = "COMPETITIVE"
                elif price_ratio < 1.05:
                    price_competitiveness = "MARKET_PRICE"
                else:
                    price_competitiveness = "ABOVE_MARKET"

            results.append({
                "estimate_row": row,
                "estimate_item": estimate_item.get("item_name"),
                "estimate_price": item_price,
                "matched": matched,
                "bid_id": best_match.bid_id if best_match else None,
                "bid_description": best_match.item_description if best_match else None,
                "bid_price": best_match.bid_price if best_match else None,
                "winning_price": best_match.winning_price if best_match else None,
                "percentile": best_match.percentile if best_match else None,
                "price_competitiveness": price_competitiveness,
            })

        return results
    except Exception as e:  # noqa: BLE001
        logger.error("Bid matching failed: %s", type(e).__name__)
        return []


def detect_price_deviations(
    matching_results: list[dict], deviation_threshold: float = 0.15
) -> list[dict]:
    """시장가 대비 가격 편차 감지.

    Args:
        matching_results: 입찰 매칭 결과
        deviation_threshold: 편차 임계값 (기본 15%)

    Returns:
        [
            {
                "estimate_row": int,
                "estimate_item": str,
                "estimate_price": float,
                "market_price": float,
                "deviation": float,
                "percentage": float,
                "direction": "OVER" | "UNDER"
            },
            ...
        ]
    """
    try:
        deviations = []

        for result in matching_results:
            if result.get("matched"):
                estimate_price = result.get("estimate_price") or 0
                market_price = result.get("winning_price") or 0

                if market_price > 0:
                    deviation = estimate_price - market_price
                    percentage = abs(deviation) / market_price

                    if percentage > deviation_threshold:
                        direction = "OVER" if deviation > 0 else "UNDER"

                        deviations.append({
                            "estimate_row": result.get("estimate_row"),
                            "estimate_item": result.get("estimate_item"),
                            "estimate_price": estimate_price,
                            "market_price": market_price,
                            "deviation": round(deviation, 2),
                            "percentage": round(percentage * 100, 1),
                            "direction": direction,
                        })

        return deviations
    except Exception as e:  # noqa: BLE001
        logger.error("Price deviation detection failed: %s", type(e).__name__)
        return []


def generate_bid_analysis_report(
    matching_results: list[dict], price_deviations: list[dict]
) -> dict:
    """입찰 분석 검토 보고서 생성.

    Returns:
        {
            "total_items": int,
            "matched_count": int,
            "competitive_count": int,
            "market_price_count": int,
            "above_market_count": int,
            "deviation_count": int,
            "summary": [...]
        }
    """
    try:
        total_items = len(matching_results)
        matched_count = len([m for m in matching_results if m.get("matched")])
        competitive = len([m for m in matching_results if m.get("price_competitiveness") == "COMPETITIVE"])
        market_price = len(
            [m for m in matching_results if m.get("price_competitiveness") == "MARKET_PRICE"]
        )
        above_market = len([m for m in matching_results if m.get("price_competitiveness") == "ABOVE_MARKET"])
        deviation_count = len(price_deviations)

        summary = [
            f"총 항목: {total_items}개",
            f"입찰 매칭: {matched_count}개",
            f"경쟁력 있음: {competitive}개",
            f"시장가: {market_price}개",
            f"시장가 초과: {above_market}개",
            f"가격 편차: {deviation_count}개",
        ]

        return {
            "total_items": total_items,
            "matched_count": matched_count,
            "competitive_count": competitive,
            "market_price_count": market_price,
            "above_market_count": above_market,
            "deviation_count": deviation_count,
            "summary": summary,
        }
    except Exception as e:  # noqa: BLE001
        logger.error("Bid report generation failed: %s", type(e).__name__)
        return {}

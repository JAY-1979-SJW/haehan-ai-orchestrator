"""Excel 통합 어댑터: 외부 데이터(자재DB, CAD, 입찰) 연동 준비."""

from .material_db_adapter import (
    MaterialDBRecord,
    match_materials_with_estimate,
    detect_unmatched_items,
    generate_material_matching_report,
)
from .cad_takeoff_adapter import (
    CADTakeoffData,
    match_cad_quantity_with_estimate,
    detect_quantity_discrepancies,
    generate_cad_integration_report,
)
from .bid_analysis_adapter import (
    BidAnalysisRecord,
    match_bid_results_with_estimate,
    detect_price_deviations,
    generate_bid_analysis_report,
)

__all__ = [
    # 자재 DB 어댑터
    "MaterialDBRecord",
    "match_materials_with_estimate",
    "detect_unmatched_items",
    "generate_material_matching_report",
    # CAD 산출 어댑터
    "CADTakeoffData",
    "match_cad_quantity_with_estimate",
    "detect_quantity_discrepancies",
    "generate_cad_integration_report",
    # 입찰 분석 어댑터
    "BidAnalysisRecord",
    "match_bid_results_with_estimate",
    "detect_price_deviations",
    "generate_bid_analysis_report",
]

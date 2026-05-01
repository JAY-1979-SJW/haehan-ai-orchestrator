"""자재 단가 검증 및 가격 일관성 검사 (건설/소방 업무용)."""
from __future__ import annotations

import logging
import statistics
from typing import Optional

logger = logging.getLogger(__name__)


def analyze_material_prices(
    sheet, material_col: int, unit_price_col: int, data_start: int, data_end: int
) -> tuple[bool, Optional[str], dict]:
    """자재별 단가 정보 분석 (통계).

    Returns:
        (성공 여부, 에러 메시지, 분석 결과 dict)
        {
            "unique_materials": int,
            "price_variations": {
                "material_name": {
                    "count": int,
                    "min": float,
                    "max": float,
                    "avg": float,
                    "stdev": float,
                    "prices": [...]
                },
                ...
            }
        }
    """
    if sheet is None:
        return False, "SHEET_NOT_FOUND", {}

    if not (material_col and unit_price_col):
        return False, "MISSING_COLUMNS", {}

    try:
        price_map = {}

        for row in range(data_start, data_end + 1):
            try:
                material = sheet.Cells(row, material_col).Value
                price_val = sheet.Cells(row, unit_price_col).Value

                if material is not None and price_val is not None:
                    material_str = str(material).strip()
                    try:
                        price_num = float(price_val)
                        if material_str not in price_map:
                            price_map[material_str] = []
                        price_map[material_str].append({
                            "row": row,
                            "price": price_num,
                        })
                    except (ValueError, TypeError):
                        pass
            except Exception:  # noqa: BLE001
                pass

        price_variations = {}
        for material, prices_data in price_map.items():
            prices = [p["price"] for p in prices_data]
            if len(prices) > 0:
                price_variations[material] = {
                    "count": len(prices),
                    "min": round(min(prices), 2),
                    "max": round(max(prices), 2),
                    "avg": round(statistics.mean(prices), 2),
                    "stdev": round(statistics.stdev(prices), 2) if len(prices) > 1 else 0,
                    "prices": [p["price"] for p in prices_data],
                }

        result = {
            "unique_materials": len(price_map),
            "price_variations": price_variations,
        }

        return True, None, result
    except Exception as e:  # noqa: BLE001
        logger.error("Material price analysis failed: %s", type(e).__name__)
        return False, "MATERIAL_PRICE_ANALYSIS_FAILED", {}


def check_price_consistency(
    sheet, material_col: int, unit_price_col: int, data_start: int, data_end: int
) -> tuple[bool, Optional[str], list]:
    """같은 자재의 단가 일관성 검사.

    Returns:
        (성공 여부, 에러 메시지, 일관성 이슈 목록)
        [
            {
                "row": int,
                "material": str,
                "price": float,
                "expected_price": float,
                "is_inconsistent": bool,
            },
            ...
        ]
    """
    if sheet is None:
        return False, "SHEET_NOT_FOUND", []

    if not (material_col and unit_price_col):
        return False, "MISSING_COLUMNS", []

    try:
        material_prices = {}
        rows_data = []

        # 첫 번째 패스: 자재별 첫 가격 기록
        for row in range(data_start, data_end + 1):
            try:
                material = sheet.Cells(row, material_col).Value
                price_val = sheet.Cells(row, unit_price_col).Value

                if material is not None and price_val is not None:
                    material_str = str(material).strip()
                    try:
                        price_num = float(price_val)
                        rows_data.append({
                            "row": row,
                            "material": material_str,
                            "price": price_num,
                        })

                        if material_str not in material_prices:
                            material_prices[material_str] = price_num
                    except (ValueError, TypeError):
                        pass
            except Exception:  # noqa: BLE001
                pass

        # 두 번째 패스: 일관성 검사
        results = []
        for row_data in rows_data:
            material = row_data["material"]
            price = row_data["price"]
            expected_price = material_prices.get(material)

            is_inconsistent = False
            if expected_price is not None:
                is_inconsistent = abs(price - expected_price) > 0.01

            results.append({
                "row": row_data["row"],
                "material": material,
                "price": price,
                "expected_price": expected_price,
                "is_inconsistent": is_inconsistent,
            })

        return True, None, results
    except Exception as e:  # noqa: BLE001
        logger.error("Price consistency check failed: %s", type(e).__name__)
        return False, "PRICE_CONSISTENCY_CHECK_FAILED", []


def detect_price_outliers(
    sheet, unit_price_col: int, data_start: int, data_end: int, std_dev_threshold: float = 2.0
) -> tuple[bool, Optional[str], list]:
    """전체 단가 중 이상치 감지 (표준편차 기반).

    Returns:
        (성공 여부, 에러 메시지, 이상치 목록)
        [
            {
                "row": int,
                "price": float,
                "z_score": float,
                "is_outlier": bool,
            },
            ...
        ]
    """
    if sheet is None:
        return False, "SHEET_NOT_FOUND", []

    if unit_price_col < 1:
        return False, "INVALID_UNIT_PRICE_COL", []

    try:
        prices = []
        rows_data = []

        for row in range(data_start, data_end + 1):
            try:
                price_val = sheet.Cells(row, unit_price_col).Value
                if price_val is not None:
                    try:
                        price_num = float(price_val)
                        if price_num > 0:
                            prices.append(price_num)
                            rows_data.append({
                                "row": row,
                                "price": price_num,
                            })
                    except (ValueError, TypeError):
                        pass
            except Exception:  # noqa: BLE001
                pass

        if len(prices) < 2:
            return True, None, []

        mean = statistics.mean(prices)
        stdev = statistics.stdev(prices)

        results = []
        for row_data in rows_data:
            price = row_data["price"]
            z_score = (price - mean) / stdev if stdev > 0 else 0
            is_outlier = abs(z_score) > std_dev_threshold

            results.append({
                "row": row_data["row"],
                "price": price,
                "z_score": round(z_score, 2),
                "is_outlier": is_outlier,
            })

        return True, None, results
    except Exception as e:  # noqa: BLE001
        logger.error("Outlier detection failed: %s", type(e).__name__)
        return False, "OUTLIER_DETECTION_FAILED", []

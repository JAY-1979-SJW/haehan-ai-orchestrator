"""내역서 분석 및 자동 검토 (건설/소방 업무용)."""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def analyze_estimate_sheet(sheet) -> tuple[bool, Optional[str], dict]:
    """내역서 시트를 분석하고 구조 파악.

    Returns:
        (성공 여부, 에러 메시지, 분석 결과 dict)
        {
            "has_header": bool,
            "header_row": int | None,
            "data_start_row": int | None,
            "data_end_row": int | None,
            "total_rows": int,
            "columns": {
                "item_name": int | None,
                "spec": int | None,
                "quantity": int | None,
                "unit_price": int | None,
                "amount": int | None,
            }
        }
    """
    if sheet is None:
        return False, "SHEET_NOT_FOUND", {}

    try:
        result = {
            "has_header": False,
            "header_row": None,
            "data_start_row": None,
            "data_end_row": None,
            "total_rows": 0,
            "columns": {
                "item_name": None,
                "spec": None,
                "quantity": None,
                "unit_price": None,
                "amount": None,
            },
        }

        rows = sheet.UsedRange.Rows.Count
        result["total_rows"] = rows

        if rows < 2:
            return True, None, result

        # 1행부터 시작해서 헤더 찾기
        for r in range(1, min(rows + 1, 20)):
            cell_value = sheet.Cells(r, 1).Value
            if cell_value and "품명" in str(cell_value):
                result["has_header"] = True
                result["header_row"] = r
                result["data_start_row"] = r + 1
                break

        if result["has_header"] and result["header_row"]:
            result["data_end_row"] = rows

        return True, None, result
    except Exception as e:  # noqa: BLE001
        logger.error("Sheet analysis failed: %s", type(e).__name__)
        return False, "SHEET_ANALYSIS_FAILED", {}


def map_estimate_columns(sheet, header_row: int) -> tuple[bool, Optional[str], dict]:
    """내역서의 품명/규격/수량/단가/금액 열 자동 매핑.

    Returns:
        (성공 여부, 에러 메시지, 열 매핑 dict)
        {
            "item_name": int | None,
            "spec": int | None,
            "quantity": int | None,
            "unit_price": int | None,
            "amount": int | None,
        }
    """
    if sheet is None:
        return False, "SHEET_NOT_FOUND", {}

    if header_row < 1:
        return False, "INVALID_HEADER_ROW", {}

    try:
        mapping = {
            "item_name": None,
            "spec": None,
            "quantity": None,
            "unit_price": None,
            "amount": None,
        }

        cols = sheet.UsedRange.Columns.Count

        # 헤더 행에서 각 열 찾기
        for col in range(1, min(cols + 1, 50)):
            header_text = str(sheet.Cells(header_row, col).Value or "").strip().lower()

            if "품명" in header_text or "item" in header_text:
                mapping["item_name"] = col
            elif "규격" in header_text or "spec" in header_text or "사양" in header_text:
                mapping["spec"] = col
            elif "수량" in header_text or "qty" in header_text or "quantity" in header_text:
                mapping["quantity"] = col
            elif "단가" in header_text or "unit" in header_text or "price" in header_text:
                mapping["unit_price"] = col
            elif "금액" in header_text or "amount" in header_text or "소계" in header_text:
                mapping["amount"] = col

        return True, None, mapping
    except Exception as e:  # noqa: BLE001
        logger.error("Column mapping failed: %s", type(e).__name__)
        return False, "COLUMN_MAPPING_FAILED", {}


def validate_estimate_amounts(
    sheet, amount_col: int, quantity_col: int, unit_price_col: int, data_start: int, data_end: int
) -> tuple[bool, Optional[str], list]:
    """금액 = 수량 × 단가 수식 검증.

    Returns:
        (성공 여부, 에러 메시지, 검증 결과 목록)
        [
            {
                "row": int,
                "amount": float | None,
                "expected": float,
                "match": bool,
                "issue": str | None,
            },
            ...
        ]
    """
    if sheet is None:
        return False, "SHEET_NOT_FOUND", []

    if not (amount_col and quantity_col and unit_price_col):
        return False, "MISSING_COLUMNS", []

    try:
        results = []

        for row in range(data_start, data_end + 1):
            try:
                qty = sheet.Cells(row, quantity_col).Value
                unit = sheet.Cells(row, unit_price_col).Value
                amount = sheet.Cells(row, amount_col).Value

                if qty is None or unit is None:
                    continue

                try:
                    qty_num = float(qty)
                    unit_num = float(unit)
                    expected = qty_num * unit_num

                    match = False
                    issue = None
                    if amount is None:
                        issue = "AMOUNT_MISSING"
                    else:
                        try:
                            amount_num = float(amount)
                            if abs(amount_num - expected) < 0.01:
                                match = True
                            else:
                                issue = "AMOUNT_MISMATCH"
                        except (ValueError, TypeError):
                            issue = "AMOUNT_NOT_NUMERIC"

                    results.append({
                        "row": row,
                        "amount": amount,
                        "expected": expected,
                        "match": match,
                        "issue": issue,
                    })
                except (ValueError, TypeError):
                    pass
            except Exception:  # noqa: BLE001
                pass

        return True, None, results
    except Exception as e:  # noqa: BLE001
        logger.error("Amount validation failed: %s", type(e).__name__)
        return False, "AMOUNT_VALIDATION_FAILED", []


def detect_price_anomalies(
    sheet, unit_price_col: int, data_start: int, data_end: int, std_dev_threshold: float = 2.0
) -> tuple[bool, Optional[str], list]:
    """단가 이상치 후보 표시 (평균에서 표준편차 × threshold 이상).

    Returns:
        (성공 여부, 에러 메시지, 이상치 목록)
        [
            {
                "row": int,
                "price": float,
                "deviation": float,
                "is_anomaly": bool,
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
                            rows_data.append({"row": row, "price": price_num})
                    except (ValueError, TypeError):
                        pass
            except Exception:  # noqa: BLE001
                pass

        if len(prices) < 2:
            return True, None, []

        # 평균과 표준편차 계산
        import statistics

        mean = statistics.mean(prices)
        stdev = statistics.stdev(prices)

        results = []
        for row_data in rows_data:
            price = row_data["price"]
            deviation = abs(price - mean) / stdev if stdev > 0 else 0
            is_anomaly = deviation > std_dev_threshold

            results.append({
                "row": row_data["row"],
                "price": price,
                "deviation": round(deviation, 2),
                "is_anomaly": is_anomaly,
            })

        return True, None, results
    except Exception as e:  # noqa: BLE001
        logger.error("Price anomaly detection failed: %s", type(e).__name__)
        return False, "PRICE_ANOMALY_DETECTION_FAILED", []


def detect_missing_quantities(
    sheet, item_col: int, quantity_col: int, data_start: int, data_end: int
) -> tuple[bool, Optional[str], list]:
    """수량 누락 후보 표시.

    Returns:
        (성공 여부, 에러 메시지, 누락 목록)
        [
            {
                "row": int,
                "item_name": str,
                "quantity": float | None,
                "is_missing": bool,
            },
            ...
        ]
    """
    if sheet is None:
        return False, "SHEET_NOT_FOUND", []

    if not (item_col and quantity_col):
        return False, "MISSING_COLUMNS", []

    try:
        results = []

        for row in range(data_start, data_end + 1):
            try:
                item = sheet.Cells(row, item_col).Value
                qty = sheet.Cells(row, quantity_col).Value

                if item is not None:
                    is_missing = qty is None or (isinstance(qty, str) and not qty.strip())

                    results.append({
                        "row": row,
                        "item_name": str(item),
                        "quantity": qty,
                        "is_missing": is_missing,
                    })
            except Exception:  # noqa: BLE001
                pass

        return True, None, results
    except Exception as e:  # noqa: BLE001
        logger.error("Missing quantity detection failed: %s", type(e).__name__)
        return False, "MISSING_QUANTITY_DETECTION_FAILED", []


def detect_duplicate_items(
    sheet, item_col: int, spec_col: Optional[int], data_start: int, data_end: int
) -> tuple[bool, Optional[str], list]:
    """중복 품목 후보 표시 (같은 품명+규격).

    Returns:
        (성공 여부, 에러 메시지, 중복 목록)
        [
            {
                "row": int,
                "item_name": str,
                "spec": str | None,
                "key": str,
                "is_duplicate": bool,
            },
            ...
        ]
    """
    if sheet is None:
        return False, "SHEET_NOT_FOUND", []

    if item_col < 1:
        return False, "INVALID_ITEM_COL", []

    try:
        items_map = {}
        results = []

        for row in range(data_start, data_end + 1):
            try:
                item_name = sheet.Cells(row, item_col).Value
                if item_name is not None:
                    spec = None
                    if spec_col:
                        spec = sheet.Cells(row, spec_col).Value

                    key = f"{item_name}|{spec}"
                    is_duplicate = key in items_map

                    if key not in items_map:
                        items_map[key] = []
                    items_map[key].append(row)

                    results.append({
                        "row": row,
                        "item_name": str(item_name),
                        "spec": str(spec) if spec else None,
                        "key": key,
                        "is_duplicate": is_duplicate,
                    })
            except Exception:  # noqa: BLE001
                pass

        return True, None, results
    except Exception as e:  # noqa: BLE001
        logger.error("Duplicate item detection failed: %s", type(e).__name__)
        return False, "DUPLICATE_ITEM_DETECTION_FAILED", []


def generate_estimate_review(
    analysis: dict,
    amount_validation: list,
    price_anomalies: list,
    missing_quantities: list,
    duplicate_items: list,
) -> tuple[bool, Optional[str], dict]:
    """검토결과 시트용 요약 정보 생성.

    Returns:
        (성공 여부, 에러 메시지, 검토결과 dict)
        {
            "total_items": int,
            "validation_issues": int,
            "price_anomalies": int,
            "missing_quantities": int,
            "duplicate_items": int,
            "summary": {
                "issues": [...]
            }
        }
    """
    try:
        total_items = len(amount_validation)
        validation_issues = len([v for v in amount_validation if v.get("issue")])
        price_anomaly_count = len([p for p in price_anomalies if p.get("is_anomaly")])
        missing_qty_count = len([m for m in missing_quantities if m.get("is_missing")])
        duplicate_count = len([d for d in duplicate_items if d.get("is_duplicate")])

        issues = []
        if validation_issues > 0:
            issues.append(f"금액 오류: {validation_issues}건")
        if price_anomaly_count > 0:
            issues.append(f"단가 이상: {price_anomaly_count}건")
        if missing_qty_count > 0:
            issues.append(f"수량 누락: {missing_qty_count}건")
        if duplicate_count > 0:
            issues.append(f"중복 품목: {duplicate_count}건")

        result = {
            "total_items": total_items,
            "validation_issues": validation_issues,
            "price_anomalies": price_anomaly_count,
            "missing_quantities": missing_qty_count,
            "duplicate_items": duplicate_count,
            "summary": {
                "issues": issues,
                "issue_count": sum([
                    validation_issues,
                    price_anomaly_count,
                    missing_qty_count,
                    duplicate_count,
                ]),
            },
        }

        return True, None, result
    except Exception as e:  # noqa: BLE001
        logger.error("Review generation failed: %s", type(e).__name__)
        return False, "REVIEW_GENERATION_FAILED", {}

"""Excel 인쇄 영역 관리 (복사본 전용)."""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def set_print_area(sheet, range_address: str) -> tuple[bool, Optional[str]]:
    """시트의 인쇄 영역을 설정한다. (복사본 전용)

    Args:
        sheet: Excel sheet object
        range_address: 인쇄 범위 (예: "A1:D10")

    Returns:
        (성공 여부, 에러 메시지)
    """
    if sheet is None:
        return False, "SHEET_NOT_FOUND"

    if not range_address:
        return False, "RANGE_ADDRESS_REQUIRED"

    try:
        sheet.PageSetup.PrintArea = range_address
        return True, None
    except Exception as e:  # noqa: BLE001
        logger.error("Failed to set print area: %s", type(e).__name__)
        return False, "PRINT_AREA_SET_FAILED"


def get_print_area(sheet) -> tuple[Optional[str], Optional[str]]:
    """시트의 현재 인쇄 영역을 조회한다.

    Args:
        sheet: Excel sheet object

    Returns:
        (인쇄 영역 주소, 에러 메시지)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"

    try:
        print_area = sheet.PageSetup.PrintArea
        if print_area:
            return str(print_area), None
        return "", None
    except Exception as e:  # noqa: BLE001
        logger.error("Failed to get print area: %s", type(e).__name__)
        return None, "PRINT_AREA_GET_FAILED"


def clear_print_area(sheet) -> tuple[bool, Optional[str]]:
    """시트의 인쇄 영역을 제거한다.

    Args:
        sheet: Excel sheet object

    Returns:
        (성공 여부, 에러 메시지)
    """
    if sheet is None:
        return False, "SHEET_NOT_FOUND"

    try:
        sheet.PageSetup.PrintArea = ""
        return True, None
    except Exception as e:  # noqa: BLE001
        logger.error("Failed to clear print area: %s", type(e).__name__)
        return False, "PRINT_AREA_CLEAR_FAILED"


def set_page_setup(
    sheet,
    orientation: Optional[str] = None,
    papersize: Optional[int] = None,
    zoom: Optional[int] = None,
) -> tuple[bool, Optional[str]]:
    """시트의 페이지 설정을 구성한다.

    Args:
        sheet: Excel sheet object
        orientation: "Portrait" 또는 "Landscape"
        papersize: 용지 크기 (1=Letter, 2=Tabloid, 3=Ledger, etc.)
        zoom: 확대/축소 비율 (10-400%)

    Returns:
        (성공 여부, 에러 메시지)
    """
    if sheet is None:
        return False, "SHEET_NOT_FOUND"

    try:
        if orientation:
            if orientation.lower() == "portrait":
                sheet.PageSetup.Orientation = 1
            elif orientation.lower() == "landscape":
                sheet.PageSetup.Orientation = 2
            else:
                return False, "INVALID_ORIENTATION"

        if papersize is not None:
            sheet.PageSetup.PaperSize = papersize

        if zoom is not None:
            if not (10 <= zoom <= 400):
                return False, "ZOOM_OUT_OF_RANGE"
            sheet.PageSetup.Zoom = zoom

        return True, None
    except Exception as e:  # noqa: BLE001
        logger.error("Failed to set page setup: %s", type(e).__name__)
        return False, "PAGE_SETUP_FAILED"


def set_margins(
    sheet,
    left: Optional[float] = None,
    right: Optional[float] = None,
    top: Optional[float] = None,
    bottom: Optional[float] = None,
) -> tuple[bool, Optional[str]]:
    """시트의 여백을 설정한다.

    Args:
        sheet: Excel sheet object
        left: 좌측 여백 (인치)
        right: 우측 여백 (인치)
        top: 상단 여백 (인치)
        bottom: 하단 여백 (인치)

    Returns:
        (성공 여부, 에러 메시지)
    """
    if sheet is None:
        return False, "SHEET_NOT_FOUND"

    try:
        if left is not None and left >= 0:
            sheet.PageSetup.LeftMargin = left
        if right is not None and right >= 0:
            sheet.PageSetup.RightMargin = right
        if top is not None and top >= 0:
            sheet.PageSetup.TopMargin = top
        if bottom is not None and bottom >= 0:
            sheet.PageSetup.BottomMargin = bottom

        return True, None
    except Exception as e:  # noqa: BLE001
        logger.error("Failed to set margins: %s", type(e).__name__)
        return False, "MARGINS_SET_FAILED"

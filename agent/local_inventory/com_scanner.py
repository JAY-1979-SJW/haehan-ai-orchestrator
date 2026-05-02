"""COM 클래스 등록 상태 스캔 (Dispatch 생성 금지).

- COM ProgID 등록 여부 확인
- 레지스트리 기반 조회만 (객체 생성 안 함)
"""
from __future__ import annotations

import logging

from .metadata import check_com_class_installed

logger = logging.getLogger(__name__)

HWP_COM_CLASSES = [
    "HWPFrame.HwpObject",
    "HWPFrame.HwpObject.1",
    "HWPFrame.HwpObject.2",
]

EXCEL_COM_CLASSES = [
    "Excel.Application",
    "Excel.Sheet",
    "Excel.Workbook",
]

AUTOCAD_COM_CLASSES = [
    "AutoCAD.Application",
    "AutoCAD.Document.19",
]


def scan_hwp_com() -> dict[str, bool]:
    """한컴 COM 클래스 등록 상태.

    Returns:
        {class_name: registered}
    """
    return {
        cls: check_com_class_installed(cls)
        for cls in HWP_COM_CLASSES
    }


def scan_excel_com() -> dict[str, bool]:
    """Excel COM 클래스 등록 상태."""
    return {
        cls: check_com_class_installed(cls)
        for cls in EXCEL_COM_CLASSES
    }


def scan_autocad_com() -> dict[str, bool]:
    """AutoCAD COM 클래스 등록 상태."""
    return {
        cls: check_com_class_installed(cls)
        for cls in AUTOCAD_COM_CLASSES
    }


def scan_all_com() -> dict[str, dict[str, bool]]:
    """모든 COM 클래스 스캔."""
    return {
        "hwp": scan_hwp_com(),
        "excel": scan_excel_com(),
        "autocad": scan_autocad_com(),
    }

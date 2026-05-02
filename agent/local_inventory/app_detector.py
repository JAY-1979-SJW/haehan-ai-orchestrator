"""애플리케이션 설치 감지.

- 한컴/Excel/AutoCAD/브라우저 설치 여부
- 설치 경로 후보
- 버전 정보
- COM 등록 상태
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from agent.local_inventory.com_scanner import (
    scan_autocad_com,
    scan_excel_com,
    scan_hwp_com,
)
from agent.local_inventory.filesystem_scanner import (
    FileScanConfig,
    scan_file,
)
from agent.local_inventory.policy import SCAN_PATHS
from agent.local_inventory.registry_scanner import (
    scan_com_registry,
    scan_hwp_modules_registry,
    scan_program_registry,
)

logger = logging.getLogger(__name__)


@dataclass
class AppDetectionResult:
    """애플리케이션 감지 결과."""
    name: str
    installed: bool
    install_paths: list[str] = field(default_factory=list)
    version: str | None = None
    com_classes: dict[str, bool] = field(default_factory=dict)
    registry_info: dict = field(default_factory=dict)
    detection_method: str = "none"  # "filesystem" / "registry" / "com" / "combined"


def detect_hancom() -> AppDetectionResult:
    """한컴 설치 여부 감지."""
    result = AppDetectionResult(
        name="Hancom",
        installed=False,
        detection_method="none",
    )

    install_paths = SCAN_PATHS.get("hancom", [])

    # 파일시스템 확인
    found_paths = []
    for path in install_paths:
        entry = scan_file(path)
        if entry:
            found_paths.append(path)
            result.installed = True
            result.detection_method = "filesystem"

    result.install_paths = found_paths

    # 레지스트리 확인
    reg_info = scan_program_registry("hancom")
    if reg_info.get("values"):
        result.registry_info = reg_info
        result.version = reg_info.get("values", {}).get("DisplayVersion") or reg_info.get("values", {}).get("Version")
        if not result.installed:
            result.installed = True
            result.detection_method = "registry"
        else:
            result.detection_method = "combined"

    # COM 클래스 확인
    com_status = scan_hwp_com()
    if any(com_status.values()):
        result.com_classes = com_status
        if not result.installed:
            result.installed = True
            result.detection_method = "com"
        else:
            result.detection_method = "combined"
    else:
        result.com_classes = com_status

    # HwpAutomation 모듈 확인
    hwp_modules = scan_hwp_modules_registry()
    if hwp_modules.get("registered"):
        result.registry_info["hwp_modules"] = hwp_modules
        if not result.installed:
            result.installed = True
            result.detection_method = "registry"
        else:
            result.detection_method = "combined"

    return result


def detect_office() -> AppDetectionResult:
    """Office (Excel) 설치 여부 감지."""
    result = AppDetectionResult(
        name="Office",
        installed=False,
        detection_method="none",
    )

    install_paths = SCAN_PATHS.get("excel", [])

    # 파일시스템 확인
    found_paths = []
    for path in install_paths:
        entry = scan_file(path)
        if entry:
            found_paths.append(path)
            result.installed = True
            result.detection_method = "filesystem"

    result.install_paths = found_paths

    # 레지스트리 확인
    reg_info = scan_program_registry("excel")
    if reg_info.get("values"):
        result.registry_info = reg_info
        result.version = reg_info.get("values", {}).get("DisplayVersion") or reg_info.get("values", {}).get("Version")
        if not result.installed:
            result.installed = True
            result.detection_method = "registry"
        else:
            result.detection_method = "combined"

    # COM 클래스 확인
    com_status = scan_excel_com()
    if any(com_status.values()):
        result.com_classes = com_status
        if not result.installed:
            result.installed = True
            result.detection_method = "com"
        else:
            result.detection_method = "combined"
    else:
        result.com_classes = com_status

    return result


def detect_autocad() -> AppDetectionResult:
    """AutoCAD 설치 여부 감지."""
    result = AppDetectionResult(
        name="AutoCAD",
        installed=False,
        detection_method="none",
    )

    install_paths = SCAN_PATHS.get("autocad", [])

    # 파일시스템 확인
    found_paths = []
    for path in install_paths:
        entry = scan_file(path)
        if entry:
            found_paths.append(path)
            result.installed = True
            result.detection_method = "filesystem"

    result.install_paths = found_paths

    # 레지스트리 확인
    reg_info = scan_program_registry("autocad")
    if reg_info.get("values"):
        result.registry_info = reg_info
        result.version = reg_info.get("values", {}).get("DisplayVersion") or reg_info.get("values", {}).get("Version")
        if not result.installed:
            result.installed = True
            result.detection_method = "registry"
        else:
            result.detection_method = "combined"

    # COM 클래스 확인
    com_status = scan_autocad_com()
    if any(com_status.values()):
        result.com_classes = com_status
        if not result.installed:
            result.installed = True
            result.detection_method = "com"
        else:
            result.detection_method = "combined"
    else:
        result.com_classes = com_status

    return result


def detect_all() -> dict[str, AppDetectionResult]:
    """모든 애플리케이션 감지."""
    return {
        "hancom": detect_hancom(),
        "office": detect_office(),
        "autocad": detect_autocad(),
    }

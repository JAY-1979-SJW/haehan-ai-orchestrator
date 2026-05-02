"""로컬 인벤토리 스캔 (사용자 동의 기반).

- 사용자 명시적 동의 획득
- 정책 기반 스캔
- 메타데이터 수집
- 인벤토리 저장
"""
from __future__ import annotations

import logging
from datetime import datetime

from .inventory import LocalInventory
from .metadata import (
    get_file_metadata,
    get_folder_metadata,
    check_com_class_installed,
    get_registry_value,
    list_registry_subkeys,
)
from .policy import (
    SCAN_PATHS,
    USER_DOCUMENT_PATHS,
    REGISTRY_PATHS,
    MAX_DEPTH,
    get_scan_paths,
    get_registry_paths,
)

logger = logging.getLogger(__name__)


def show_consent_dialog() -> bool:
    """사용자 동의 대화.

    사용자가 동의하면 True 반환.
    """
    print()
    print("=" * 70)
    print("📋 로컬 자산 인벤토리 스캔")
    print("=" * 70)
    print()

    print("다음 정보를 수집합니다 (로컬만 저장, 서버 전송 없음):")
    print("  ✓ 한컴 설치 상태 및 버전")
    print("  ✓ Excel 설치 상태 및 버전")
    print("  ✓ AutoCAD 설치 상태 및 버전")
    print("  ✓ 문서 폴더 메타데이터 (경로, 크기, 수정시간)")
    print("  ✓ 설치된 프로그램 목록")
    print()

    print("수집되지 않는 정보:")
    print("  ✗ 파일 내용")
    print("  ✗ 비밀번호, 인증서, 쿠키")
    print("  ✗ 브라우저 히스토리")
    print("  ✗ 개인 정보")
    print()

    print("저장 위치: 로컬 PC (%APPDATA%\\haehan-ai-orchestrator\\inventory)")
    print("전송: 없음 (오프라인 사용)")
    print("삭제: 사용자가 언제든 삭제 가능")
    print()

    response = input("계속 진행하시겠습니까? (y/n): ").strip().lower()
    return response == "y"


def scan_hancom_inventory(inventory: LocalInventory) -> dict:
    """한컴 설치 상태 스캔."""
    logger.info("Scanning Hancom installation...")

    result = {
        "name": "Hancom",
        "installed": False,
        "paths": {},
        "com_classes": [],
        "version": None,
    }

    # 설치 경로 확인
    hancom_paths = SCAN_PATHS.get("hancom", [])
    for path in hancom_paths:
        metadata = get_file_metadata(path)
        if metadata.get("exists"):
            result["paths"]["installation"] = path
            result["installed"] = True
            logger.info(f"Found Hancom at {path}")
            break

    # COM 클래스 확인
    com_classes = [
        "HWPFrame.HwpObject",
        "HWPFrame.HwpObject.1",
        "HWPFrame.HwpObject.2",
    ]
    for com_class in com_classes:
        if check_com_class_installed(com_class):
            result["com_classes"].append(com_class)

    return result


def scan_excel_inventory(inventory: LocalInventory) -> dict:
    """Excel 설치 상태 스캔."""
    logger.info("Scanning Excel installation...")

    result = {
        "name": "Excel",
        "installed": False,
        "paths": {},
        "com_classes": [],
        "version": None,
    }

    # 설치 경로 확인
    excel_paths = SCAN_PATHS.get("excel", [])
    for path in excel_paths:
        metadata = get_file_metadata(path)
        if metadata.get("exists"):
            result["paths"]["installation"] = path
            result["installed"] = True
            logger.info(f"Found Excel at {path}")
            break

    # COM 클래스 확인
    if check_com_class_installed("Excel.Application"):
        result["com_classes"].append("Excel.Application")

    return result


def scan_autocad_inventory(inventory: LocalInventory) -> dict:
    """AutoCAD 설치 상태 스캔."""
    logger.info("Scanning AutoCAD installation...")

    result = {
        "name": "AutoCAD",
        "installed": False,
        "paths": {},
        "com_classes": [],
        "version": None,
    }

    # 설치 경로 확인
    cad_paths = SCAN_PATHS.get("autocad", [])
    for path in cad_paths:
        metadata = get_file_metadata(path)
        if metadata.get("exists"):
            result["paths"]["installation"] = path
            result["installed"] = True
            logger.info(f"Found AutoCAD at {path}")
            break

    return result


def scan_document_folders(inventory: LocalInventory) -> dict:
    """문서 폴더 메타데이터 스캔."""
    logger.info("Scanning document folders...")

    result = {}

    # 기본 문서 폴더들
    folder_names = {
        "Documents": "{USERPROFILE}\\Documents",
        "Downloads": "{USERPROFILE}\\Downloads",
        "Desktop": "{USERPROFILE}\\Desktop",
        "OneDrive": "{USERPROFILE}\\OneDrive",
    }

    for name, path_template in folder_names.items():
        import os

        path = os.path.expandvars(path_template)
        metadata = get_folder_metadata(path, max_depth=MAX_DEPTH["user_documents"])

        if metadata.get("exists"):
            result[name] = metadata
            logger.info(f"Scanned {name}: {metadata.get('file_count')} files")

    return result


def scan_local_inventory(consent: bool = False) -> bool:
    """로컬 인벤토리 전체 스캔.

    Args:
        consent: 사용자 동의 여부 (False면 대화상자 표시)

    Returns:
        성공 여부
    """
    # 사용자 동의 확인
    if not consent:
        if not show_consent_dialog():
            print("\n❌ 스캔이 취소되었습니다.")
            return False

    print("\n[스캔 진행 중...]")
    print()

    try:
        # 인벤토리 초기화
        inventory = LocalInventory()
        inventory.init_db()

        # 스캔 데이터
        scan_data = {
            "metadata": {
                "scan_date": datetime.utcnow().isoformat() + "Z",
                "scan_version": "1.0",
                "user_consent": True,
                "scan_scope": ["hancom", "excel", "autocad", "documents"],
            },
            "programs": {
                "hancom": scan_hancom_inventory(inventory),
                "excel": scan_excel_inventory(inventory),
                "autocad": scan_autocad_inventory(inventory),
            },
            "folders": scan_document_folders(inventory),
        }

        # 인벤토리 저장
        if inventory.save_inventory(scan_data):
            print("✅ 인벤토리 스캔 완료")
            print(f"   저장 경로: {inventory.get_inventory_json_path()}")
            return True
        else:
            print("❌ 인벤토리 저장 실패")
            return False

    except Exception as e:
        logger.error(f"Scan failed: {e}")
        print(f"❌ 스캔 실패: {e}")
        return False

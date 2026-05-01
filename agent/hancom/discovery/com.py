"""한컴 COM 가용성 진단.

HwpObject COM 클래스의 등록 상태 및 접근 가능성 진단.
HwpObject 생성/조작은 하지 않음 (진단만).
"""
from __future__ import annotations

import logging
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)

# 지원하는 HwpObject COM 클래스들 (우선순위 순서)
HWPOBJECT_CLASSES = [
    "HWPFrame.HwpObject",
    "HWPFrame.HwpObject.1",
    "HWPFrame.HwpObject.2",
    "HwpObject.HwpObject",
]


def check_com_class_registered(class_name: str) -> bool:
    """COM 클래스 등록 상태 확인 (registry 기반).

    Args:
        class_name: COM 클래스 이름 (예: "HWPFrame.HwpObject")

    Returns:
        등록 여부
    """
    try:
        from . import registry
        import winreg

        # HKEY_LOCAL_MACHINE\SOFTWARE\Classes\{ClassName}
        path = rf"SOFTWARE\Classes\{class_name}"
        exists = registry.check_registry_path_exists(
            winreg.HKEY_LOCAL_MACHINE,
            path
        )
        if exists:
            logger.info(f"COM 클래스 등록됨: {class_name}")
        return exists
    except Exception as e:
        logger.warning(f"COM 클래스 확인 실패 ({class_name}): {type(e).__name__}")
        return False


def get_com_class_clsid(class_name: str) -> Optional[str]:
    """COM 클래스의 CLSID 조회.

    Args:
        class_name: COM 클래스 이름

    Returns:
        CLSID 또는 None
    """
    try:
        from . import registry
        import winreg

        # HKEY_LOCAL_MACHINE\SOFTWARE\Classes\{ClassName}\CLSID
        path = rf"SOFTWARE\Classes\{class_name}\CLSID"
        clsid = registry.read_registry_value(
            winreg.HKEY_LOCAL_MACHINE,
            path,
            ""  # default value
        )
        if clsid:
            logger.info(f"{class_name} CLSID: {clsid}")
        return clsid
    except Exception as e:
        logger.warning(f"CLSID 조회 실패 ({class_name}): {type(e).__name__}")
        return None


def check_all_hwpobject_classes() -> Dict[str, Dict[str, any]]:
    """모든 지원 HwpObject 클래스 상태 확인.

    Returns:
        {클래스명: {registered, clsid, priority}}
    """
    result = {}
    for idx, class_name in enumerate(HWPOBJECT_CLASSES):
        registered = check_com_class_registered(class_name)
        clsid = None
        if registered:
            clsid = get_com_class_clsid(class_name)

        result[class_name] = {
            "registered": registered,
            "clsid": clsid,
            "priority": idx,
        }

    logger.info(f"HwpObject 클래스 진단: {result}")
    return result


def get_hwpobject_class_priority() -> List[str]:
    """등록된 HwpObject 클래스를 우선순위대로 반환.

    Returns:
        [클래스명, ...] (우선순위 순서)
    """
    registered_classes = []
    for class_name in HWPOBJECT_CLASSES:
        if check_com_class_registered(class_name):
            registered_classes.append(class_name)

    logger.info(f"등록된 HwpObject 클래스 (우선순위): {registered_classes}")
    return registered_classes


def check_com_dispatch_available(class_name: str) -> Tuple[bool, Optional[str]]:
    """COM Dispatch 가능성 확인.

    Args:
        class_name: COM 클래스 이름

    Returns:
        (가능 여부, 오류 메시지)
    """
    try:
        import win32com.client as win32

        try:
            # 실제로 Dispatch를 시도하지 않고, 클래스만 확인
            # (HwpObject 생성은 하지 않음)
            obj = win32.GetObject(class_name)
            obj = None
            return True, None
        except AttributeError:
            return False, "win32com.GetObject 실패"
        except Exception as e:
            return False, f"{type(e).__name__}: {str(e)[:100]}"

    except ImportError:
        return False, "win32com.client not available"
    except Exception as e:
        logger.error(f"COM Dispatch 확인 실패: {type(e).__name__}")
        return False, f"{type(e).__name__}"


def diagnose_com_status() -> Dict[str, any]:
    """COM 가용성 종합 진단.

    Returns:
        {
            "win32com_available": bool,
            "hwpobject_classes": {...},
            "available_classes": [...],
            "dispatch_status": {...},
        }
    """
    result = {
        "win32com_available": False,
        "hwpobject_classes": {},
        "available_classes": [],
        "dispatch_status": {},
    }

    # win32com 가용성 확인
    try:
        import win32com.client as win32
        result["win32com_available"] = True
    except ImportError:
        logger.warning("win32com not available")
        result["win32com_available"] = False

    # HwpObject 클래스 진단
    result["hwpobject_classes"] = check_all_hwpobject_classes()
    result["available_classes"] = get_hwpobject_class_priority()

    # Dispatch 가능성 확인
    for class_name in result["available_classes"]:
        available, error = check_com_dispatch_available(class_name)
        result["dispatch_status"][class_name] = {
            "available": available,
            "error": error,
        }

    logger.info(f"COM 진단 완료: {result['available_classes']} 가능")
    return result

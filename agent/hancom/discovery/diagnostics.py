"""한컴 로컬 설치 종합 진단 (orchestration).

Registry, COM, 설치 경로 정보를 통합하여 한컴 설치/COM/보안모듈 상태 진단.
local_inventory가 있으면 우선 사용하여 비표준 경로 문제 해결.
모든 작업은 read-only 진단.
"""
from __future__ import annotations

import logging
from typing import Dict, Any, Optional

from . import registry, com, installation

logger = logging.getLogger(__name__)


def _extract_hancom_from_inventory() -> Optional[Dict[str, Any]]:
    """Local Inventory에서 한컴 정보 추출.

    Returns:
        한컴 진단 결과 dict 또는 None (없을 시)
    """
    try:
        from agent.local_inventory.inventory_store import InventoryStore

        store = InventoryStore()
        inventory = store.load()
        if not inventory:
            logger.info("Local inventory not found")
            return None

        programs = inventory.get("programs", {})
        hancom = programs.get("hancom", {})
        if not hancom or not hancom.get("installed"):
            logger.info("한컴 정보 없음 in inventory")
            return None

        logger.info("한컴 정보 inventory에서 발견")

        # Inventory 기반 결과 구성
        installed_paths = hancom.get("install_paths", [])
        com_classes = hancom.get("com_classes", {})
        registry_info = hancom.get("registry_info", {})

        # COM 상태
        available_com = [k for k, v in com_classes.items() if v]
        com_status = {
            "win32com_available": True,
            "available_classes": available_com,
        }

        # 설치 경로 및 DLL
        dlls = inventory.get("dlls", {})
        hwp_dlls = dlls.get("hwp_automation", [])
        primary_dll = hwp_dlls[0].get("path") if hwp_dlls else None
        dll_candidates = {d.get("path"): True for d in hwp_dlls if isinstance(d, dict)}

        installation_status = {
            "installation_paths": installed_paths,
            "primary_dll": primary_dll,
            "dll_candidates": dll_candidates,
        }

        # 보안모듈 (inventory에는 없지만, COM 등록되면 설정된 것으로 판정)
        security_module = {
            "registered": len(available_com) > 0,  # COM이 있으면 보안모듈 등록된 것으로 판정
            "registry_path_used": "HKEY_LOCAL_MACHINE\\SOFTWARE\\HNC\\Hwp" if available_com else "",
            "module_names": available_com,
            "details": {},
        }

        registry_status = {
            f"{k}": v for k, v in registry_info.items()
            if k in ("DisplayName", "Version", "Path")
        }
        registry_status = registry_status or {"hancom_registered": len(installed_paths) > 0}

        return {
            "installed": True,
            "source": "inventory",
            "registry_status": registry_status,
            "com_status": com_status,
            "installation_status": installation_status,
            "security_module": security_module,
            "summary": f"한컴 {hancom.get('version', '?')} (Inventory)",
            "recommendations": [],
        }

    except Exception as e:
        logger.exception(f"Failed to extract hancom from inventory: {e}")
        return None


def diagnose_hancom_installation(use_inventory: bool = True) -> Dict[str, Any]:
    """한컴 설치 상태 종합 진단.

    Args:
        use_inventory: local_inventory 사용 여부 (기본값: True)

    Returns:
        {
            "installed": bool,
            "source": str,  # "inventory" | "discovery"
            "registry_status": {...},
            "com_status": {...},
            "installation_status": {...},
            "security_module": {...},
            "summary": str,
            "recommendations": [...],
        }
    """
    result = {
        "installed": False,
        "source": "discovery",
        "registry_status": {},
        "com_status": {},
        "installation_status": {},
        "security_module": {},
        "summary": "",
        "recommendations": [],
    }

    logger.info("=== 한컴 로컬 설치 종합 진단 시작 ===")

    # 0. Local Inventory 시도 (우선)
    if use_inventory:
        hancom_from_inv = _extract_hancom_from_inventory()
        if hancom_from_inv:
            logger.info("[0] Local Inventory에서 한컴 정보 발견")
            result["source"] = "inventory"
            result.update(hancom_from_inv)
            logger.info("=== 종합 진단 완료 (Inventory) ===")
            return result

    # 1. Registry 상태 확인
    logger.info("[1] Registry 상태 확인...")
    result["registry_status"] = registry.check_hancom_registry_installation()
    registry_ok = any(result["registry_status"].values())
    logger.info(f"  Registry: {result['registry_status']}")

    # 2. COM 상태 확인
    logger.info("[2] COM 상태 확인...")
    result["com_status"] = com.diagnose_com_status()
    com_ok = len(result["com_status"]["available_classes"]) > 0
    logger.info(f"  COM 가능: {result['com_status']['available_classes']}")

    # 3. 설치 경로 및 DLL 확인
    logger.info("[3] 설치 경로 및 DLL 확인...")
    result["installation_status"] = installation.diagnose_installation_status()
    install_ok = result["installation_status"]["primary_dll"] is not None
    logger.info(f"  설치 경로: {result['installation_status']['installation_paths']}")
    logger.info(f"  Primary DLL: {result['installation_status']['primary_dll']}")

    # 4. 보안모듈 상태 확인
    logger.info("[4] 보안모듈 상태 확인...")
    result["security_module"] = registry.check_security_module_registry()
    sec_module_ok = result["security_module"]["registered"]
    logger.info(f"  보안모듈: {result['security_module']}")

    # 5. 설치 판정
    result["installed"] = registry_ok and (com_ok or install_ok)
    logger.info(f"설치 판정: {result['installed']}")

    # 6. Summary 생성
    status_parts = []
    if registry_ok:
        status_parts.append("Registry ✓")
    if com_ok:
        status_parts.append("COM ✓")
    if install_ok:
        status_parts.append("DLL ✓")
    if sec_module_ok:
        status_parts.append("보안모듈 ✓")

    result["summary"] = " | ".join(status_parts) if status_parts else "한컴 미설치"

    # 7. Recommendations 생성
    result["recommendations"] = _generate_recommendations(result)
    logger.info(f"Recommendations: {result['recommendations']}")

    logger.info("=== 종합 진단 완료 (Discovery) ===")
    return result


def _generate_recommendations(diag_result: Dict[str, Any]) -> list:
    """진단 결과 기반 추천사항 생성.

    Args:
        diag_result: diagnose_hancom_installation() 반환 값

    Returns:
        [추천사항, ...]
    """
    recommendations = []

    if not diag_result["installed"]:
        recommendations.append(
            "한컴이 설치되지 않았습니다. "
            "https://developers.hancom.com/ 에서 한컴 개발자 버전 설치 후 다시 진행하세요."
        )
        return recommendations

    # Registry 확인
    if not any(diag_result["registry_status"].values()):
        recommendations.append(
            "한컴 Registry 항목이 없습니다. 한컴 재설치를 시도하세요."
        )

    # COM 확인
    if not diag_result["com_status"]["available_classes"]:
        recommendations.append(
            "HwpObject COM 클래스가 등록되지 않았습니다. "
            "한컴 설치 또는 복구를 시도하세요."
        )

    # DLL 확인
    if not diag_result["installation_status"]["primary_dll"]:
        recommendations.append(
            "HwpAutomation.dll을 찾을 수 없습니다. "
            "한컴 설치 경로를 확인하세요."
        )

    # 보안모듈 확인
    if diag_result["installed"] and not diag_result["security_module"]["registered"]:
        recommendations.append(
            "보안모듈이 등록되지 않았습니다. "
            "`python scripts/setup_hancom_security_module.py`를 실행하여 등록하세요."
        )

    return recommendations


def print_diagnosis_report(diag_result: Dict[str, Any]) -> None:
    """진단 결과를 사용자 친화적 형식으로 출력.

    Args:
        diag_result: diagnose_hancom_installation() 반환 값
    """
    print("\n" + "=" * 70)
    print("한컴 로컬 설치 진단 보고서")
    print("=" * 70)
    print()

    print(f"[최종 판정] {diag_result['summary']}")
    print()

    if diag_result["registry_status"]:
        print("[Registry 상태]")
        for key, value in diag_result["registry_status"].items():
            status = "✓" if value else "✗"
            print(f"  {status} {key}")
        print()

    if diag_result["com_status"]["available_classes"]:
        print("[COM 상태]")
        print(f"  ✓ win32com: {'있음' if diag_result['com_status']['win32com_available'] else '없음'}")
        print(f"  ✓ HwpObject 클래스: {', '.join(diag_result['com_status']['available_classes'])}")
        print()

    if diag_result["installation_status"]["installation_paths"]:
        print("[설치 경로]")
        for path in diag_result["installation_status"]["installation_paths"]:
            print(f"  ✓ {path}")
        print()

    if diag_result["installation_status"]["dll_candidates"]:
        print("[DLL 후보]")
        for dll_path, status in diag_result["installation_status"]["dll_candidates"].items():
            print(f"  ✓ {dll_path}")
        print()

    if diag_result["security_module"]["registered"]:
        print("[보안모듈]")
        print(f"  ✓ Registry: {diag_result['security_module']['registry_path_used']}")
        print(f"  ✓ 모듈명: {', '.join(diag_result['security_module']['module_names'])}")
        for module_name, dll_path in diag_result["security_module"]["details"].items():
            print(f"    - {module_name}: {dll_path}")
        print()

    if diag_result["recommendations"]:
        print("[추천사항]")
        for idx, rec in enumerate(diag_result["recommendations"], 1):
            print(f"  {idx}. {rec}")
        print()

    print("=" * 70)

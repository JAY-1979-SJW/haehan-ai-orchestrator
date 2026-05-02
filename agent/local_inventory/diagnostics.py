"""로컬 인벤토리 진단 및 비교.

- 전체 스캔 오케스트레이션
- 스캔 결과 비교
- 스캔 레벨 기반 실행
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .app_detector import detect_all
from .change_watcher import (
    InventoryDiff,
    compare_inventory,
    format_diff_report,
)
from .consent_policy import (
    inventory_scan_consent,
)
from .dll_mapper import map_all_dlls
from .inventory_store import InventoryStore
from .privacy_filter import apply_privacy_filter
from .scan_scope import ALL_SCOPES, ScanScope
from .scan_level import (
    ScanLevel,
    DEFAULT_SCAN_LEVEL,
    get_level_config,
    validate_scan_level,
)

logger = logging.getLogger(__name__)


@dataclass
class InventoryScanParams:
    """스캔 매개변수."""
    scan_level: ScanLevel = DEFAULT_SCAN_LEVEL
    scopes: list[ScanScope] = field(default_factory=lambda: list(ALL_SCOPES))
    user_selected_paths: list[str] = field(default_factory=list)  # Level 2/3용
    force_consent: bool = False
    apply_privacy_filter_flag: bool = True
    store_result: bool = True
    consent_state_path: Optional[str] = None
    inventory_path: Optional[str] = None


def run_local_inventory_scan(params: Optional[InventoryScanParams] = None) -> dict:
    """로컬 인벤토리 스캔 실행.

    Args:
        params: 스캔 매개변수

    Returns:
        {
            "ok": bool,
            "scan_level": int,
            "scopes_requested": [str],
            "scopes_scanned": [str],
            "programs": {...},
            "dlls": {...},
            "scan_date": str,
            "error": Optional[str],
        }
    """
    if params is None:
        params = InventoryScanParams()

    try:
        # 0. 레벨에 맞는 스코프 필터링
        level_config = get_level_config(params.scan_level)
        allowed = level_config.allowed_scopes
        filtered_scopes = [s for s in params.scopes if s in allowed]
        if filtered_scopes:
            params.scopes = filtered_scopes
            logger.info(f"Filtered scopes for {params.scan_level.name}: {[s.value for s in params.scopes]}")
        else:
            # 허용된 스코프가 없으면 레벨의 기본 스코프 사용
            params.scopes = list(allowed)
            logger.info(f"Auto-set scopes for {params.scan_level.name}: {[s.value for s in params.scopes]}")

        # 1. 레벨 검증
        logger.info(f"Validating scan level: {params.scan_level.name}")

        ok, reason = validate_scan_level(params.scan_level, params.scopes)
        if not ok:
            logger.info(f"Scan level validation failed: {reason}")
            return {
                "ok": False,
                "scan_level": params.scan_level.value,
                "scopes_requested": [s.value for s in params.scopes],
                "scopes_scanned": [],
                "error": reason,
            }

        # Level 0은 스캔 안 함
        if params.scan_level == ScanLevel.NO_SCAN:
            logger.info("Scan level is NO_SCAN, no scanning performed")
            return {
                "ok": False,
                "scan_level": params.scan_level.value,
                "scopes_requested": [],
                "scopes_scanned": [],
                "error": "no_scan",
            }

        # Level 3은 user_selected_paths 필수
        if params.scan_level == ScanLevel.DEEP_METADATA and not params.user_selected_paths:
            logger.error("Level 3 requires user_selected_paths")
            return {
                "ok": False,
                "scan_level": params.scan_level.value,
                "scopes_requested": [s.value for s in params.scopes],
                "scopes_scanned": [],
                "error": "level_3_requires_selected_paths",
            }

        # 레벨 설정으로 scopes 제한
        level_config = get_level_config(params.scan_level)
        actual_scopes = [
            s for s in params.scopes
            if s in level_config.allowed_scopes
        ]

        # 2. 동의 확인
        logger.info(f"Requesting consent for level {params.scan_level.name}")

        consent_path = None
        if params.consent_state_path:
            from pathlib import Path
            consent_path = Path(params.consent_state_path)

        if not inventory_scan_consent(
            actual_scopes,
            params.force_consent,
            consent_path,
            params.scan_level,
        ):
            logger.info("User declined consent")
            return {
                "ok": False,
                "scan_level": params.scan_level.value,
                "scopes_requested": [s.value for s in actual_scopes],
                "scopes_scanned": [],
                "error": "user_declined_consent",
            }

        # 3. 스캔 실행
        logger.info(f"Starting inventory scan at level {params.scan_level.name}")
        scan_data = {
            "metadata": {
                "scan_date": datetime.utcnow().isoformat() + "Z",
                "scan_version": "1.0",
                "scan_level": params.scan_level.value,
                "scopes": [s.value for s in actual_scopes],
            },
            "programs": {},
            "dlls": {},
        }

        # 애플리케이션 감지
        apps = detect_all()
        for app_name, app_result in apps.items():
            scan_data["programs"][app_name] = {
                "name": app_result.name,
                "installed": app_result.installed,
                "install_paths": app_result.install_paths,
                "version": app_result.version,
                "com_classes": app_result.com_classes,
                "registry_info": app_result.registry_info,
                "detection_method": app_result.detection_method,
            }

        # DLL 매핑
        dlls = map_all_dlls()
        for dll_type, dll_list in dlls.items():
            scan_data["dlls"][dll_type] = [
                {
                    "path": dll.path,
                    "exists": dll.exists,
                    "size_bytes": dll.size_bytes,
                    "dll_type": dll.dll_type,
                }
                for dll in dll_list
            ]

        # 4. 개인정보 필터링
        if params.apply_privacy_filter_flag:
            logger.info("Applying privacy filter")
            scan_data = apply_privacy_filter(scan_data)

        # 5. 저장
        if params.store_result:
            from pathlib import Path

            store_path = None
            if params.inventory_path:
                store_path = Path(params.inventory_path)

            store = InventoryStore(store_path)
            if store.save(scan_data):
                logger.info(f"Inventory saved to {store.get_path()}")
            else:
                logger.warning("Failed to save inventory")

        return {
            "ok": True,
            "scan_level": params.scan_level.value,
            "scopes_requested": [s.value for s in actual_scopes],
            "scopes_scanned": [s.value for s in actual_scopes],
            "programs": scan_data.get("programs", {}),
            "dlls": scan_data.get("dlls", {}),
            "scan_date": scan_data.get("metadata", {}).get("scan_date"),
        }

    except Exception as e:
        logger.error(f"Scan failed: {e}")
        return {
            "ok": False,
            "scan_level": params.scan_level.value if params else DEFAULT_SCAN_LEVEL.value,
            "scopes_requested": [s.value for s in params.scopes] if params else [],
            "scopes_scanned": [],
            "error": str(e),
        }


def compare_inventory_snapshots(params: Optional[dict] = None) -> dict:
    """두 인벤토리 스냅샷 비교.

    Args:
        params: {
            "inventory_path": Optional[str],  # 저장된 인벤토리 경로
        }

    Returns:
        {
            "ok": bool,
            "diff": InventoryDiff (dict 형태),
            "report": str,  # 사람이 읽을 수 있는 보고서
            "error": Optional[str],
        }
    """
    if params is None:
        params = {}

    try:
        from pathlib import Path

        # 저장된 인벤토리 로드
        store_path = None
        if params.get("inventory_path"):
            store_path = Path(params["inventory_path"])

        store = InventoryStore(store_path)
        old_inventory = store.load()

        if not old_inventory:
            logger.warning("No previous inventory found")
            return {
                "ok": False,
                "diff": None,
                "report": "No previous inventory found",
                "error": "no_previous_inventory",
            }

        # 현재 스캔 실행
        scan_params = InventoryScanParams(
            inventory_path=params.get("inventory_path"),
        )
        scan_result = run_local_inventory_scan(scan_params)

        if not scan_result.get("ok"):
            return {
                "ok": False,
                "diff": None,
                "report": "",
                "error": scan_result.get("error"),
            }

        # 비교
        new_inventory = {
            "metadata": {
                "scan_date": scan_result.get("scan_date"),
            },
            "programs": scan_result.get("programs", {}),
            "dlls": scan_result.get("dlls", {}),
        }

        diff = compare_inventory(old_inventory, new_inventory)

        report = format_diff_report(diff)
        logger.info(report)

        return {
            "ok": True,
            "diff": {
                "added_programs": diff.added_programs,
                "removed_programs": diff.removed_programs,
                "changed_programs": diff.changed_programs,
                "added_dlls": diff.added_dlls,
                "removed_dlls": diff.removed_dlls,
                "has_changes": diff.has_changes,
            },
            "report": report,
        }

    except Exception as e:
        logger.error(f"Comparison failed: {e}")
        return {
            "ok": False,
            "diff": None,
            "report": "",
            "error": str(e),
        }

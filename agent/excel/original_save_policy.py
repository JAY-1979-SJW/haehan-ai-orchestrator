"""원본 저장 정책 및 강한 승인 기능."""
from __future__ import annotations

import logging
from typing import Optional

from . import approval_policy, backup_manager, validator

logger = logging.getLogger(__name__)


def save_original_with_backup(
    wb,
    original_path: str,
    approval_token: str,
    change_summary: Optional[dict] = None,
    backup_path: Optional[str] = None,
) -> dict:
    """원본 파일을 백업 후 저장한다.

    강한 승인 정책 적용:
    - 승인 토큰 필수
    - 자동 백업 생성
    - 변경 계획 hash 검증
    - 문서 보호 상태 확인

    Returns:
        {
            "success": bool,
            "original_path": str | None,
            "backup_path": str | None,
            "backup_created": bool,
            "changes": [...],
            "error": str | None,
        }
    """
    result = validator.build_update_result()
    change_summary = change_summary or {}

    try:
        # STOP 조건 1: 승인 토큰 확인
        if not approval_token:
            result["error"] = "APPROVAL_TOKEN_REQUIRED"
            return result

        # STOP 조건 2: 변경 계획 hash 생성
        change_hash = approval_policy.generate_change_hash(change_summary)
        if not change_hash:
            result["error"] = "CHANGE_HASH_GENERATION_FAILED"
            return result

        # STOP 조건 3: 승인 토큰 유효성 검증
        valid, error = approval_policy.validate_approval_token(approval_token, change_hash)
        if not valid:
            result["error"] = error
            return result

        # STOP 조건 4: 워크북 확인
        if wb is None:
            result["error"] = "WORKBOOK_NOT_FOUND"
            return result

        # STOP 조건 5: 원본 경로 확인
        if not original_path:
            result["error"] = "ORIGINAL_PATH_REQUIRED"
            return result

        # STOP 조건 6: 문서 보호 상태 확인
        valid, error = approval_policy.check_document_protection(wb)
        if not valid:
            result["error"] = error
            return result

        # STOP 조건 7: 종합 저장 준비 상태 확인
        valid, error = approval_policy.check_save_readiness(
            wb, approval_token, change_hash
        )
        if not valid:
            result["error"] = error
            return result

        # 자동 백업 생성
        backup_success = False
        target_backup_path = backup_path
        backup_created = False

        try:
            success, error, backup_result_path = backup_manager.create_backup(
                original_path, target_backup_path
            )

            if not success:
                result["error"] = error
                return result

            backup_created = True
            target_backup_path = backup_result_path

            # 백업 검증
            valid, error = backup_manager.verify_backup(target_backup_path, original_path)
            if not valid:
                logger.warning("Backup verification warning: %s", error)

            backup_success = True
        except Exception as e:  # noqa: BLE001
            logger.error("Backup creation failed: %s", type(e).__name__)
            result["error"] = "BACKUP_CREATION_FAILED"
            return result

        # 원본 저장 (승인됨)
        try:
            wb.Save()
            result["success"] = True
            result["original_path"] = original_path
            result["backup_path"] = target_backup_path
            result["backup_created"] = backup_created
            result["changes"] = approval_policy.describe_changes(change_summary)

            # 오래된 백업 정리
            try:
                backup_manager.cleanup_old_backups(original_path, keep_count=3)
            except Exception as e:  # noqa: BLE001
                logger.warning("Backup cleanup warning: %s", type(e).__name__)

        except Exception as e:  # noqa: BLE001
            logger.error("Original save failed: %s", type(e).__name__)
            result["error"] = "ORIGINAL_SAVE_FAILED"

        return result

    except Exception as e:  # noqa: BLE001
        logger.error("save_original_with_backup 실패: %s", type(e).__name__)
        result["error"] = "SAVE_WITH_BACKUP_FAILED"
        return result


def get_backup_info(original_path: str) -> dict:
    """원본 파일의 백업 정보 조회.

    Returns:
        {
            "original_path": str,
            "latest_backup": str | None,
            "backup_count": int,
            "backups": [...]
        }
    """
    try:
        import os

        if not original_path or not os.path.exists(original_path):
            return {
                "original_path": original_path,
                "latest_backup": None,
                "backup_count": 0,
                "backups": [],
            }

        dir_path = os.path.dirname(original_path)
        base_name = os.path.basename(original_path)
        base, ext = os.path.splitext(base_name)

        backups = []
        for file in os.listdir(dir_path):
            if file.startswith(base) and ".backup." in file and file.endswith(ext):
                backup_path = os.path.join(dir_path, file)
                mtime = os.path.getmtime(backup_path)
                size = os.path.getsize(backup_path)
                backups.append({
                    "path": backup_path,
                    "size": size,
                    "modified": mtime,
                })

        backups.sort(key=lambda x: x["modified"], reverse=True)

        return {
            "original_path": original_path,
            "latest_backup": backups[0]["path"] if backups else None,
            "backup_count": len(backups),
            "backups": backups,
        }
    except Exception as e:  # noqa: BLE001
        logger.error("Backup info retrieval failed: %s", type(e).__name__)
        return {}

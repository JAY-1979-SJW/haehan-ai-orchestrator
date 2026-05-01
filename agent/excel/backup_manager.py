"""Excel 백업 관리."""
from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


def generate_backup_path(original_path: str) -> str:
    """원본 파일 경로에서 백업 경로 생성.

    Args:
        original_path: 원본 파일 경로 (예: C:\\file.xlsx)

    Returns:
        백업 경로 (예: C:\\file.backup.20260502_143022.xlsx)
    """
    try:
        if not original_path:
            return ""

        base, ext = os.path.splitext(original_path)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{base}.backup.{timestamp}{ext}"

        return backup_path
    except Exception as e:  # noqa: BLE001
        logger.error("Backup path generation failed: %s", type(e).__name__)
        return ""


def create_backup(original_path: str, backup_path: Optional[str] = None) -> tuple[bool, Optional[str], Optional[str]]:
    """원본 파일의 백업 생성.

    Args:
        original_path: 원본 파일 경로
        backup_path: 백업 저장 경로 (기본값: 자동 생성)

    Returns:
        (성공 여부, 에러 메시지, 백업 경로)
    """
    try:
        # 입력 검증
        if not original_path:
            return False, "ORIGINAL_PATH_REQUIRED", None

        if not os.path.exists(original_path):
            return False, "ORIGINAL_FILE_NOT_FOUND", None

        # 백업 경로 결정
        target_backup_path = backup_path or generate_backup_path(original_path)
        if not target_backup_path:
            return False, "BACKUP_PATH_GENERATION_FAILED", None

        # 백업 디렉토리 생성 (필요시)
        backup_dir = os.path.dirname(target_backup_path)
        if backup_dir and not os.path.exists(backup_dir):
            try:
                os.makedirs(backup_dir, exist_ok=True)
            except Exception as e:  # noqa: BLE001
                logger.error("Backup directory creation failed: %s", type(e).__name__)
                return False, "BACKUP_DIR_CREATION_FAILED", None

        # 백업 파일 복사
        try:
            shutil.copy2(original_path, target_backup_path)
            return True, None, target_backup_path
        except Exception as e:  # noqa: BLE001
            logger.error("Backup copy failed: %s", type(e).__name__)
            return False, "BACKUP_COPY_FAILED", None

    except Exception as e:  # noqa: BLE001
        logger.error("Backup creation failed: %s", type(e).__name__)
        return False, "BACKUP_CREATION_FAILED", None


def verify_backup(backup_path: str, original_path: str) -> tuple[bool, Optional[str]]:
    """백업 파일 유효성 검증.

    Args:
        backup_path: 백업 파일 경로
        original_path: 원본 파일 경로

    Returns:
        (유효 여부, 에러 메시지)
    """
    try:
        # 백업 파일 존재 확인
        if not os.path.exists(backup_path):
            return False, "BACKUP_FILE_NOT_FOUND"

        # 백업 파일 크기 확인 (0 바이트가 아닌지)
        if os.path.getsize(backup_path) == 0:
            return False, "BACKUP_FILE_EMPTY"

        # 원본 파일과 백업 파일 크기 비교
        if os.path.exists(original_path):
            original_size = os.path.getsize(original_path)
            backup_size = os.path.getsize(backup_path)

            # 크기 차이가 크면 경고
            if original_size > 0:
                size_diff_percent = abs(backup_size - original_size) / original_size * 100
                if size_diff_percent > 10:
                    logger.warning(
                        "Backup size differs from original by %.1f%%",
                        size_diff_percent,
                    )

        return True, None
    except Exception as e:  # noqa: BLE001
        logger.error("Backup verification failed: %s", type(e).__name__)
        return False, "BACKUP_VERIFICATION_FAILED"


def cleanup_old_backups(original_path: str, keep_count: int = 3) -> tuple[bool, Optional[str]]:
    """원본 파일의 오래된 백업 정리.

    Args:
        original_path: 원본 파일 경로
        keep_count: 유지할 백업 개수 (기본값: 3)

    Returns:
        (성공 여부, 에러 메시지)
    """
    try:
        if not original_path or not os.path.exists(original_path):
            return False, "ORIGINAL_PATH_INVALID"

        # 같은 디렉토리의 백업 파일 검색
        dir_path = os.path.dirname(original_path)
        base_name = os.path.basename(original_path)
        base, ext = os.path.splitext(base_name)

        backup_files = []
        for file in os.listdir(dir_path):
            if file.startswith(base) and ".backup." in file and file.endswith(ext):
                backup_path = os.path.join(dir_path, file)
                mtime = os.path.getmtime(backup_path)
                backup_files.append((backup_path, mtime))

        # 파일 개수가 많으면 오래된 것부터 삭제
        if len(backup_files) > keep_count:
            backup_files.sort(key=lambda x: x[1])
            to_delete = backup_files[: len(backup_files) - keep_count]

            for backup_path, _ in to_delete:
                try:
                    os.remove(backup_path)
                    logger.info("Deleted old backup: %s", backup_path)
                except Exception as e:  # noqa: BLE001
                    logger.warning("Failed to delete backup %s: %s", backup_path, type(e).__name__)

        return True, None
    except Exception as e:  # noqa: BLE001
        logger.error("Backup cleanup failed: %s", type(e).__name__)
        return False, "BACKUP_CLEANUP_FAILED"

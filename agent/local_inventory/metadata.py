"""로컬 인벤토리 메타데이터 수집.

- 파일/폴더 메타데이터 (경로, 크기, 수정시간, 확장자)
- Registry 값 조회 (read-only)
- COM 클래스 정보
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


def get_file_metadata(path: str) -> dict:
    """파일 메타데이터 조회 (내용 읽기 안 함).

    Returns:
        {
            "path": str,
            "exists": bool,
            "size_bytes": int | None,
            "modified_time": str | None,  # ISO 8601
            "extension": str,
        }
    """
    try:
        p = Path(path)

        if not p.exists():
            return {
                "path": path,
                "exists": False,
                "size_bytes": None,
                "modified_time": None,
                "extension": p.suffix.lower(),
            }

        # 파일 크기 조회
        size = None
        try:
            if p.is_file():
                size = p.stat().st_size
        except (OSError, PermissionError):
            pass

        # 수정시간 조회
        modified = None
        try:
            mtime = p.stat().st_mtime
            modified = datetime.utcfromtimestamp(mtime).isoformat() + "Z"
        except (OSError, PermissionError):
            pass

        return {
            "path": str(p),
            "exists": True,
            "is_file": p.is_file(),
            "is_dir": p.is_dir(),
            "size_bytes": size,
            "modified_time": modified,
            "extension": p.suffix.lower(),
        }

    except Exception as e:
        logger.warning(f"Failed to get metadata for {path}: {e}")
        return {
            "path": path,
            "exists": False,
            "size_bytes": None,
            "modified_time": None,
            "extension": Path(path).suffix.lower(),
            "error": str(e),
        }


def get_folder_metadata(path: str, max_depth: int = 2, current_depth: int = 0) -> dict:
    """폴더 메타데이터 조회 (깊이 제한).

    Returns:
        {
            "path": str,
            "exists": bool,
            "file_count": int,
            "folder_count": int,
            "total_size_bytes": int,
            "last_modified": str,
            "file_types": {"extension": count, ...},
            "last_scanned": str,
        }
    """
    from .policy import is_excluded_folder, is_allowed_extension

    try:
        p = Path(path)

        if not p.exists() or not p.is_dir():
            return {
                "path": path,
                "exists": False,
                "file_count": 0,
                "folder_count": 0,
                "total_size_bytes": 0,
            }

        file_count = 0
        folder_count = 0
        total_size = 0
        file_types = {}
        last_modified = None

        try:
            for item in p.iterdir():
                # 깊이 제한
                if current_depth >= max_depth:
                    break

                # 제외 폴더 제외
                if item.is_dir() and is_excluded_folder(item.name):
                    continue

                try:
                    if item.is_file():
                        file_count += 1
                        stat = item.stat()
                        total_size += stat.st_size

                        # 확장자별 카운트 (문서 타입만)
                        ext = item.suffix.lower()
                        if ext in {".hwp", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".pdf"}:
                            file_types[ext] = file_types.get(ext, 0) + 1

                        # 최신 수정시간 추적
                        if last_modified is None:
                            mtime = stat.st_mtime
                            last_modified = datetime.utcfromtimestamp(mtime).isoformat() + "Z"

                    elif item.is_dir():
                        folder_count += 1

                except (OSError, PermissionError):
                    continue

        except (OSError, PermissionError) as e:
            logger.warning(f"Error iterating folder {path}: {e}")

        return {
            "path": str(p),
            "exists": True,
            "file_count": file_count,
            "folder_count": folder_count,
            "total_size_bytes": total_size,
            "file_types": file_types,
            "last_modified": last_modified,
            "last_scanned": datetime.utcnow().isoformat() + "Z",
        }

    except Exception as e:
        logger.warning(f"Failed to get folder metadata for {path}: {e}")
        return {
            "path": path,
            "exists": False,
            "error": str(e),
        }


def get_registry_value(
    hkey: int,
    path: str,
    value_name: str,
) -> Optional[str]:
    """Registry 값 조회 (read-only).

    Args:
        hkey: HKEY_LOCAL_MACHINE, HKEY_CURRENT_USER 등
        path: registry 경로 (예: r"SOFTWARE\HNC\HOffice")
        value_name: 값 이름

    Returns:
        값 또는 None
    """
    try:
        import winreg

        try:
            key = winreg.OpenKey(hkey, path, 0, winreg.KEY_READ)
            try:
                value, _ = winreg.QueryValueEx(key, value_name)
                return str(value)
            finally:
                winreg.CloseKey(key)
        except FileNotFoundError:
            return None

    except ImportError:
        logger.warning("winreg not available")
        return None
    except Exception as e:
        logger.warning(f"Failed to get registry value {path}\\{value_name}: {e}")
        return None


def list_registry_subkeys(hkey: int, path: str) -> list[str]:
    """Registry 하위 키 목록 조회 (read-only).

    Args:
        hkey: HKEY_LOCAL_MACHINE, HKEY_CURRENT_USER 등
        path: registry 경로

    Returns:
        하위 키 이름 목록
    """
    try:
        import winreg

        subkeys = []
        try:
            key = winreg.OpenKey(hkey, path, 0, winreg.KEY_READ)
            try:
                i = 0
                while True:
                    try:
                        subkey = winreg.EnumKey(key, i)
                        subkeys.append(subkey)
                        i += 1
                    except OSError:
                        break
            finally:
                winreg.CloseKey(key)
        except FileNotFoundError:
            pass

        return subkeys

    except ImportError:
        logger.warning("winreg not available")
        return []
    except Exception as e:
        logger.warning(f"Failed to list registry keys {path}: {e}")
        return []


def check_com_class_installed(class_name: str) -> bool:
    """COM 클래스가 등록되어 있는지 확인 (registry 기반).

    Args:
        class_name: COM 클래스명 (예: "HWPFrame.HwpObject")

    Returns:
        등록 여부
    """
    try:
        import winreg

        # CLSID 조회
        path = f"SOFTWARE\\Classes\\{class_name}\\CLSID"
        clsid = get_registry_value(
            winreg.HKEY_LOCAL_MACHINE,
            path,
            "",
        )
        return clsid is not None

    except Exception as e:
        logger.warning(f"Failed to check COM class {class_name}: {e}")
        return False

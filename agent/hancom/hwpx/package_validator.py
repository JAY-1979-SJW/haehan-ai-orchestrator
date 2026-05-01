"""HWPX 패키지 검증.

HWPX는 OpenDocument 기반 ZIP 패키지:
- mimetype 파일 (선택사항)
- Contents/ 디렉토리
  - content.hpf (또는 content.xml)
  - 1.hml, 2.hml, ... (섹션 XML)
- META-INF/ 디렉토리
  - manifest.xml

검증 규칙:
- ZIP 구조 확인
- Contents/content.hpf 또는 section XML 존재
- 섹션 최소 1개 이상
"""
from __future__ import annotations

import logging
import zipfile
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def validate_hwpx_package(hwpx_path: str) -> Tuple[bool, Optional[str]]:
    """HWPX 패키지 유효성 검증.

    Returns:
        (유효성, error_or_None)
    """
    if not Path(hwpx_path).exists():
        return False, "HWPX_FILE_NOT_FOUND"

    try:
        # ZIP 구조 확인
        if not zipfile.is_zipfile(hwpx_path):
            return False, "NOT_A_ZIP_FILE"

        with zipfile.ZipFile(hwpx_path, "r") as zf:
            file_list = zf.namelist()

            # Contents 디렉토리 확인
            has_contents = any(f.startswith("Contents/") for f in file_list)
            if not has_contents:
                return False, "CONTENTS_DIR_NOT_FOUND"

            # content.hpf 또는 section XML 확인
            has_content_hpf = "Contents/content.hpf" in file_list
            section_xml_files = [f for f in file_list if f.startswith("Contents/") and f.endswith(".xml")]

            if not has_content_hpf and not section_xml_files:
                return False, "CONTENT_FILE_NOT_FOUND"

            # 섹션 최소 1개 확인 (.hml 또는 .xml)
            hwml_files = [f for f in file_list if f.startswith("Contents/") and f.endswith(".hml")]
            if not hwml_files and not section_xml_files:
                return False, "NO_SECTIONS_FOUND"

            logger.info(f"HWPX valid: {len(file_list)} files, {len(hwml_files)} sections")
            return True, None

    except zipfile.BadZipFile:
        logger.error("Invalid ZIP format")
        return False, "INVALID_ZIP_FORMAT"
    except Exception as e:
        logger.error(f"Validation failed: {type(e).__name__}")
        return False, "VALIDATION_FAILED"


def get_hwpx_structure(hwpx_path: str) -> dict:
    """HWPX 패키지 내부 구조를 분석한다.

    Returns:
        {
            "valid": bool,
            "file_count": int,
            "directories": [str, ...],
            "has_content_hpf": bool,
            "sections": [str, ...],
            "meta_files": [str, ...],
            "error": str | None,
        }
    """
    result = {
        "valid": False,
        "file_count": 0,
        "directories": [],
        "has_content_hpf": False,
        "sections": [],
        "meta_files": [],
        "error": None,
    }

    try:
        if not zipfile.is_zipfile(hwpx_path):
            result["error"] = "NOT_A_ZIP_FILE"
            return result

        with zipfile.ZipFile(hwpx_path, "r") as zf:
            file_list = zf.namelist()
            result["file_count"] = len(file_list)

            # 디렉토리 추출
            dirs = set()
            for f in file_list:
                if "/" in f:
                    dirs.add(f.split("/")[0])
            result["directories"] = sorted(list(dirs))

            # content.hpf 확인
            result["has_content_hpf"] = "Contents/content.hpf" in file_list

            # 섹션 파일 추출 (.hml 또는 .xml)
            result["sections"] = sorted([
                f for f in file_list
                if f.startswith("Contents/") and (f.endswith(".hml") or f.endswith(".xml"))
            ])

            # 메타 파일 추출
            result["meta_files"] = sorted([f for f in file_list if f.startswith("META-INF/")])

            # 유효성 확인
            has_contents = "Contents" in dirs
            has_sections = len(result["sections"]) > 0
            result["valid"] = has_contents and (result["has_content_hpf"] or has_sections)

            logger.info(f"HWPX structure: {result['file_count']} files, {len(result['sections'])} sections")

            return result

    except Exception as e:
        logger.error(f"Structure analysis failed: {type(e).__name__}")
        result["error"] = f"ANALYSIS_FAILED:{type(e).__name__}"
        return result


def extract_hwpx_metadata(hwpx_path: str) -> dict:
    """HWPX 메타데이터를 추출한다.

    Returns:
        {
            "success": bool,
            "file_count": int,
            "total_size": int,
            "content_size": int,
            "error": str | None,
        }
    """
    result = {
        "success": False,
        "file_count": 0,
        "total_size": 0,
        "content_size": 0,
        "error": None,
    }

    try:
        result["total_size"] = Path(hwpx_path).stat().st_size

        with zipfile.ZipFile(hwpx_path, "r") as zf:
            result["file_count"] = len(zf.namelist())

            # Contents 파일 전체 크기
            content_size = sum(
                zf.getinfo(f).file_size
                for f in zf.namelist()
                if f.startswith("Contents/")
            )
            result["content_size"] = content_size
            result["success"] = True

        return result

    except Exception as e:
        logger.error(f"Metadata extraction failed: {type(e).__name__}")
        result["error"] = f"METADATA_FAILED:{type(e).__name__}"
        return result

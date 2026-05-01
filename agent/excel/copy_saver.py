"""Excel 복사본 저장.

SaveCopyAs를 사용하여 복사본을 저장한다.
원본은 저장하지 않고, ActiveWorkbook도 변경하지 않는다.
"""
from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)

_XL_OPEN_XML_WORKBOOK = 51


def build_safe_copy_path(
    workbook: Any,
    output_path: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """복사본 저장 경로를 생성한다.

    - output_path가 주어지면 그것을 검증 및 사용
    - output_path가 없으면 temp 폴더에 자동 생성
    - 절대경로만 허용
    - 원본 경로와 동일하면 차단

    Returns:
        (safe_path, error_or_None)
    """
    try:
        wb_path = str(workbook.FullName)
        wb_name = str(workbook.Name)
    except Exception:  # noqa: BLE001
        wb_path = None
        wb_name = "workbook.xlsx"

    if output_path:
        # output_path가 명시된 경우
        try:
            p = Path(output_path).expanduser()
        except (OSError, ValueError):
            return None, "OUTPUT_PATH_NOT_ALLOWED"

        if not p.is_absolute():
            return None, "OUTPUT_PATH_NOT_ALLOWED"

        # 원본 경로와 동일하면 차단
        if wb_path and str(p) == wb_path:
            return None, "OUTPUT_PATH_SAME_AS_ORIGINAL"

        return str(p), None
    else:
        # output_path가 없으면 temp 폴더에 자동 생성
        temp_dir = tempfile.gettempdir()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name, ext = os.path.splitext(wb_name)
        copy_path = os.path.join(temp_dir, f"{base_name}_copy_{ts}{ext}")
        return copy_path, None


def save_copy(
    workbook: Any,
    output_path: str,
) -> Optional[str]:
    """SaveCopyAs를 사용하여 복사본을 저장한다.

    - wb.Save() 호출 없음
    - ActiveWorkbook이 변경되지 않음
    - 원본 FullName은 유지됨

    Returns:
        error_or_None
    """
    if workbook is None:
        return "WORKBOOK_REQUIRED"
    if not output_path or not isinstance(output_path, str):
        return "OUTPUT_PATH_REQUIRED"

    try:
        p = Path(output_path).expanduser()
    except (OSError, ValueError):
        return "OUTPUT_PATH_NOT_ALLOWED"

    if not p.is_absolute():
        return "OUTPUT_PATH_NOT_ALLOWED"

    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return "OUTPUT_PATH_NOT_ALLOWED"

    try:
        # SaveCopyAs 사용: 복사본 저장, ActiveWorkbook 변경 없음
        workbook.SaveCopyAs(str(p))
        logger.info("SaveCopyAs 성공: %s", str(p))
        return None
    except AttributeError:
        # SaveCopyAs가 없을 경우 (구 버전 Excel), SaveAs로 대체
        logger.warning("SaveCopyAs 미지원, SaveAs 사용")
        try:
            workbook.SaveAs(str(p), FileFormat=_XL_OPEN_XML_WORKBOOK)
            return None
        except Exception as e:  # noqa: BLE001
            logger.error("SaveAs 실패: %s", type(e).__name__)
            return "WORKBOOK_SAVE_FAILED"
    except Exception as e:  # noqa: BLE001
        logger.error("SaveCopyAs 실패: %s", type(e).__name__)
        return "WORKBOOK_SAVE_FAILED"

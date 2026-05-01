"""Excel 업데이트 결과 검증 및 응답 생성.

update_cell_by_header_copy 액션의 최종 응답을 구성한다.
"""
from __future__ import annotations

from typing import Any, Optional


def build_update_result(
    success: bool = False,
    *,
    sheet: Optional[str] = None,
    header_row: Optional[int] = None,
    matched_row: Optional[int] = None,
    target_cell: Optional[str] = None,
    old_value: Any = None,
    new_value: Any = None,
    output_file: Optional[str] = None,
    error: Optional[str] = None,
) -> dict:
    """update_cell_by_header_copy 최종 응답을 구성한다.

    Returns:
        {
            "success": bool,
            "read_only": False,
            "write_mode": "copy_only",
            "original_saved": False,
            "output_file": str | None,
            "sheet": str | None,
            "header_row": int | None,
            "matched_row": int | None,
            "target_cell": str | None,
            "old_value": Any,
            "new_value": Any,
            "error": str | None,
        }
    """
    return {
        "success": bool(success),
        "read_only": False,
        "write_mode": "copy_only",
        "original_saved": False,
        "output_file": output_file,
        "sheet": sheet,
        "header_row": header_row,
        "matched_row": matched_row,
        "target_cell": target_cell,
        "old_value": old_value,
        "new_value": new_value,
        "error": error,
    }

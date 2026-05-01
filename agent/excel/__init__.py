"""Excel 워크플로우 모듈 (헤더 인식 → 행/열 추가 → 수식 입력 → 서식 복사 → 복사본 저장)."""

from .cell_writer import col_letter, update_cell
from .column_writer import (
    fill_column_values,
    insert_column_at,
    insert_column_next_to_header,
)
from .copy_saver import build_safe_copy_path, save_copy
from .formula_writer import (
    build_formula_from_headers,
    fill_formula_down,
    write_formula_to_cell,
)
from .header_detector import detect_header_row, map_headers
from .row_finder import find_row_by_header_value
from .row_writer import fill_row_by_headers, insert_row_at, insert_row_by_match
from .style_copier import (
    copy_cell_format,
    copy_column_format,
    copy_range_format,
    copy_row_format,
)
from .validator import build_update_result
from .workflows import (
    insert_column_by_header_copy,
    insert_row_by_header_copy,
    write_formula_by_header_copy,
)

__all__ = [
    # 기본 모듈
    "detect_header_row",
    "map_headers",
    "find_row_by_header_value",
    "update_cell",
    "col_letter",
    "build_safe_copy_path",
    "save_copy",
    "build_update_result",
    # 행 관련
    "insert_row_at",
    "fill_row_by_headers",
    "insert_row_by_match",
    # 열 관련
    "insert_column_at",
    "insert_column_next_to_header",
    "fill_column_values",
    # 수식 관련
    "write_formula_to_cell",
    "fill_formula_down",
    "build_formula_from_headers",
    # 서식 관련
    "copy_row_format",
    "copy_column_format",
    "copy_cell_format",
    "copy_range_format",
    # 워크플로우
    "insert_row_by_header_copy",
    "insert_column_by_header_copy",
    "write_formula_by_header_copy",
]

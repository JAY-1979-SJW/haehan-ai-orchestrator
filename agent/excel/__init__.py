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
from .table_analyzer import (
    analyze_column_type,
    analyze_table_structure,
    detect_data_range,
)
from .formula_validator import (
    check_formula_consistency_in_range,
    extract_cell_references,
    scan_formula_errors,
    validate_formula_in_cell,
)
from .data_validator import (
    check_empty_cells_in_range,
    check_numeric_consistency,
    detect_duplicates_in_column,
    validate_data_range,
)
from .reporter import (
    build_analysis_report,
    format_report_as_text,
    summarize_changes,
)
from .analysis_workflows import (
    analyze_active_workbook,
    generate_analysis_report,
    validate_data_quality,
    validate_formulas,
)
from .change_tracker import (
    compare_analyses,
    generate_change_summary,
    track_cell_changes,
)
from .structure_analyzer import analyze_active_sheet_structure
from .merged_cell_detector import detect_merged_cells
from .table_region_detector import (
    detect_table_regions,
    detect_header_row_candidates,
    detect_total_row_candidates,
)
from .hidden_filter_detector import (
    detect_hidden_rows,
    detect_hidden_columns,
    detect_autofilter,
)
from .formula_scanner import (
    scan_formula_cells,
    detect_numeric_as_text_candidates,
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
    # 표 분석 (고도화)
    "analyze_column_type",
    "analyze_table_structure",
    "detect_data_range",
    # 수식 검증 (고도화)
    "extract_cell_references",
    "validate_formula_in_cell",
    "check_formula_consistency_in_range",
    "scan_formula_errors",
    # 데이터 검증 (고도화)
    "check_empty_cells_in_range",
    "detect_duplicates_in_column",
    "check_numeric_consistency",
    "validate_data_range",
    # 보고서 (고도화)
    "build_analysis_report",
    "format_report_as_text",
    "summarize_changes",
    # 분석 워크플로우 (고도화)
    "analyze_active_workbook",
    "validate_data_quality",
    "validate_formulas",
    "generate_analysis_report",
    # 변경 추적 (고도화)
    "compare_analyses",
    "track_cell_changes",
    "generate_change_summary",
    # 구조 분석 (EXCEL-PC-4A 고도화)
    "analyze_active_sheet_structure",
    "detect_merged_cells",
    "detect_table_regions",
    "detect_header_row_candidates",
    "detect_total_row_candidates",
    "detect_hidden_rows",
    "detect_hidden_columns",
    "detect_autofilter",
    "scan_formula_cells",
    "detect_numeric_as_text_candidates",
]

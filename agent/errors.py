"""표준 에러 코드.

- ``out["error"]`` 로 외부에 노출되는 식별자의 단일 출처.
- 이 단계에서는 **기존 문자열을 그대로 상수화**하여 하위 호환을 유지한다
  (호출자/테스트가 기존 문자열을 assert 하고 있으므로 값은 변경하지 않음).
- prefix 형태의 코드는 세부 사유를 ``:suffix`` 로 붙여 반환한다.
  예: ``url_not_allowed:blocked_host:localhost``.
"""
from __future__ import annotations

# ── 단일 코드 (접미 없음) ───────────────────────────────────────────────
ACTION_NOT_ALLOWED = "action_not_allowed"
CONCURRENT_BROWSER_LIMIT = "concurrent_browser_limit"

SITE_KEY_REQUIRED = "site_key_required"
TARGET_URL_REQUIRED = "target_url_required"

SITE_PROFILE_NOT_FOUND = "site_profile_not_found"
SECRET_NOT_FOUND = "secret_not_found"

HOST_NOT_ALLOWED = "host_not_allowed"
LOGIN_HOST_NOT_ALLOWED = "login_host_not_allowed"
TARGET_HOST_NOT_ALLOWED = "target_host_not_allowed"
TARGET_PATH_NOT_ALLOWED = "target_path_not_allowed"

LOGIN_FAILED = "login_failed"
INSPECT_CHECK_FAILED = "inspect_check_failed"

LOGIN_GOTO_TIMEOUT = "login_goto_timeout"
LOGIN_SELECTOR_TIMEOUT = "login_selector_timeout"
SELECTOR_TIMEOUT = "selector_timeout"
TARGET_GOTO_TIMEOUT = "target_goto_timeout"
PLAYWRIGHT_TIMEOUT = "playwright_timeout"
PLAYWRIGHT_NOT_INSTALLED = "playwright_not_installed"

# Excel 커넥터 (1단계) ─ 파일 경로/포맷/시트/출력 관련
FILE_PATH_REQUIRED = "file_path_required"
FILE_NOT_ALLOWED = "file_not_allowed"
FILE_NOT_FOUND = "file_not_found"
SHEET_NOT_FOUND = "sheet_not_found"
OUTPUT_PATH_REQUIRED = "output_path_required"
OUTPUT_PATH_NOT_ALLOWED = "output_path_not_allowed"
OUTPUT_FILE_EXISTS = "output_file_exists"
EXCEL_UNSUPPORTED_FORMAT = "excel_unsupported_format"
ROWS_REQUIRED = "rows_required"

# Excel 2단계: workbook 구조 요약 / 헤더 기반 표 읽기
TABLE_HEADER_NOT_FOUND = "table_header_not_found"
TABLE_EMPTY = "table_empty"
TABLE_TOO_LARGE = "table_too_large"
INVALID_HEADER_ROW = "invalid_header_row"
INVALID_MAX_ROWS = "invalid_max_rows"

# Excel COM (B안 1단계 POC) ─ 실제 Excel 데스크톱 앱 제어
EXCEL_COM_NOT_SUPPORTED = "excel_com_not_supported"
EXCEL_COM_DISPATCH_FAILED = "excel_com_dispatch_failed"
EXCEL_APP_NOT_FOUND = "excel_app_not_found"
WORKBOOK_OPEN_FAILED = "workbook_open_failed"
WORKBOOK_SAVE_FAILED = "workbook_save_failed"
CELL_READ_FAILED = "cell_read_failed"
CELL_WRITE_FAILED = "cell_write_failed"

# HWP COM (B안 1단계 POC) ─ 로컬 한글 데스크톱 앱 제어
HWP_COM_NOT_SUPPORTED = "hwp_com_not_supported"
HWP_COM_DISPATCH_FAILED = "hwp_com_dispatch_failed"
HWP_APP_NOT_FOUND = "hwp_app_not_found"
HWP_SECURITY_MODULE_REQUIRED = "hwp_security_module_required"
HWP_DOCUMENT_OPEN_FAILED = "hwp_document_open_failed"
HWP_TEXT_READ_FAILED = "hwp_text_read_failed"
HWP_TEXT_WRITE_FAILED = "hwp_text_write_failed"
HWP_DOCUMENT_SAVE_FAILED = "hwp_document_save_failed"

# CAD COM (B안 1단계 POC) ─ 로컬 AutoCAD 데스크톱 앱 제어
CAD_COM_NOT_SUPPORTED = "cad_com_not_supported"
CAD_COM_DISPATCH_FAILED = "cad_com_dispatch_failed"
CAD_APP_NOT_FOUND = "cad_app_not_found"
CAD_DOCUMENT_OPEN_FAILED = "cad_document_open_failed"
CAD_DOCUMENT_INFO_FAILED = "cad_document_info_failed"
CAD_ENTITY_ADD_FAILED = "cad_entity_add_failed"
CAD_DOCUMENT_SAVE_FAILED = "cad_document_save_failed"
# CAD 액션 편입(2단계) — executor/approval 레벨 입력 검증용
CAD_INVALID_PATH = "cad_invalid_path"
CAD_OVERWRITE_FORBIDDEN = "cad_overwrite_forbidden"
CAD_INVALID_ARGUMENT = "cad_invalid_argument"

# CAD API 액션 편입(3단계) — orchestrator/api/v1/cad/* 프록시 호출 실패
CAD_PROXY_UNREACHABLE = "cad_proxy_unreachable"
CAD_PROXY_TIMEOUT = "cad_proxy_timeout"
CAD_PROXY_AUTH_MISSING = "cad_proxy_auth_missing"
CAD_PROXY_UPSTREAM_ERROR = "cad_proxy_upstream_error"
CAD_MISSING_PARAM = "cad_missing_param"

# COM 연동 보안: 승인/쓰기 제어
WRITE_APPROVAL_REQUIRED = "write_approval_required"
WRITE_NOT_ALLOWED = "write_not_allowed"
DRY_RUN_PLANNED = "dry_run_planned"

# Local Software Manager (1C) ─ 설치 실행 승인/검증
INSTALL_APPROVAL_REQUIRED = "install_approval_required"
INSTALL_PROGRAM_ID_REQUIRED = "install_program_id_required"
INSTALL_NOT_IN_ALLOWLIST = "install_not_in_allowlist"
INSTALL_ALREADY_INSTALLED = "install_already_installed"
INSTALL_NOT_REQUIRED = "install_not_required"
EXECUTION_NOT_ENABLED_YET = "execution_not_enabled_yet"

# ── prefix 코드 (상세 사유 suffix 가 붙음) ──────────────────────────────
URL_NOT_ALLOWED = "url_not_allowed"
LOGIN_URL_NOT_ALLOWED = "login_url_not_allowed"
TARGET_URL_NOT_ALLOWED = "target_url_not_allowed"
PLAYWRIGHT_ERROR = "playwright_error"
SECRET_STORE_ERROR = "secret_store_error"
EXCEL_ERROR = "excel_error"


# ── 분류용 집합 ────────────────────────────────────────────────────────
ALL_CODES: frozenset[str] = frozenset({
    ACTION_NOT_ALLOWED,
    CONCURRENT_BROWSER_LIMIT,
    SITE_KEY_REQUIRED,
    TARGET_URL_REQUIRED,
    SITE_PROFILE_NOT_FOUND,
    SECRET_NOT_FOUND,
    HOST_NOT_ALLOWED,
    LOGIN_HOST_NOT_ALLOWED,
    TARGET_HOST_NOT_ALLOWED,
    TARGET_PATH_NOT_ALLOWED,
    LOGIN_FAILED,
    INSPECT_CHECK_FAILED,
    LOGIN_GOTO_TIMEOUT,
    LOGIN_SELECTOR_TIMEOUT,
    SELECTOR_TIMEOUT,
    TARGET_GOTO_TIMEOUT,
    PLAYWRIGHT_TIMEOUT,
    PLAYWRIGHT_NOT_INSTALLED,
    FILE_PATH_REQUIRED,
    FILE_NOT_ALLOWED,
    FILE_NOT_FOUND,
    SHEET_NOT_FOUND,
    OUTPUT_PATH_REQUIRED,
    OUTPUT_PATH_NOT_ALLOWED,
    OUTPUT_FILE_EXISTS,
    EXCEL_UNSUPPORTED_FORMAT,
    ROWS_REQUIRED,
    TABLE_HEADER_NOT_FOUND,
    TABLE_EMPTY,
    TABLE_TOO_LARGE,
    INVALID_HEADER_ROW,
    INVALID_MAX_ROWS,
    EXCEL_COM_NOT_SUPPORTED,
    EXCEL_COM_DISPATCH_FAILED,
    EXCEL_APP_NOT_FOUND,
    WORKBOOK_OPEN_FAILED,
    WORKBOOK_SAVE_FAILED,
    CELL_READ_FAILED,
    CELL_WRITE_FAILED,
    HWP_COM_NOT_SUPPORTED,
    HWP_COM_DISPATCH_FAILED,
    HWP_APP_NOT_FOUND,
    HWP_SECURITY_MODULE_REQUIRED,
    HWP_DOCUMENT_OPEN_FAILED,
    HWP_TEXT_READ_FAILED,
    HWP_TEXT_WRITE_FAILED,
    HWP_DOCUMENT_SAVE_FAILED,
    CAD_COM_NOT_SUPPORTED,
    CAD_COM_DISPATCH_FAILED,
    CAD_APP_NOT_FOUND,
    CAD_DOCUMENT_OPEN_FAILED,
    CAD_DOCUMENT_INFO_FAILED,
    CAD_ENTITY_ADD_FAILED,
    CAD_DOCUMENT_SAVE_FAILED,
    CAD_INVALID_PATH,
    CAD_OVERWRITE_FORBIDDEN,
    CAD_INVALID_ARGUMENT,
    CAD_PROXY_UNREACHABLE,
    CAD_PROXY_TIMEOUT,
    CAD_PROXY_AUTH_MISSING,
    CAD_PROXY_UPSTREAM_ERROR,
    CAD_MISSING_PARAM,
})

PREFIX_CODES: frozenset[str] = frozenset({
    URL_NOT_ALLOWED,
    LOGIN_URL_NOT_ALLOWED,
    TARGET_URL_NOT_ALLOWED,
    PLAYWRIGHT_ERROR,
    SECRET_STORE_ERROR,
    EXCEL_ERROR,
})


def is_standard_code(err: str) -> bool:
    """``err`` 가 표준 코드(또는 표준 prefix 로 시작) 인지 판정."""
    if not isinstance(err, str) or not err:
        return False
    if err in ALL_CODES:
        return True
    head = err.split(":", 1)[0]
    return head in PREFIX_CODES


def with_reason(prefix: str, reason: str) -> str:
    """prefix 코드에 사유 suffix 를 붙여 반환.

    ``reason`` 이 비어 있으면 prefix 만 그대로 반환.
    """
    if not isinstance(prefix, str) or not prefix:
        raise ValueError("prefix must be non-empty string")
    if not isinstance(reason, str) or not reason:
        return prefix
    return f"{prefix}:{reason}"


__all__ = [
    "ACTION_NOT_ALLOWED",
    "CONCURRENT_BROWSER_LIMIT",
    "SITE_KEY_REQUIRED",
    "TARGET_URL_REQUIRED",
    "SITE_PROFILE_NOT_FOUND",
    "SECRET_NOT_FOUND",
    "HOST_NOT_ALLOWED",
    "LOGIN_HOST_NOT_ALLOWED",
    "TARGET_HOST_NOT_ALLOWED",
    "TARGET_PATH_NOT_ALLOWED",
    "LOGIN_FAILED",
    "INSPECT_CHECK_FAILED",
    "LOGIN_GOTO_TIMEOUT",
    "LOGIN_SELECTOR_TIMEOUT",
    "SELECTOR_TIMEOUT",
    "TARGET_GOTO_TIMEOUT",
    "PLAYWRIGHT_TIMEOUT",
    "PLAYWRIGHT_NOT_INSTALLED",
    "FILE_PATH_REQUIRED",
    "FILE_NOT_ALLOWED",
    "FILE_NOT_FOUND",
    "SHEET_NOT_FOUND",
    "OUTPUT_PATH_REQUIRED",
    "OUTPUT_PATH_NOT_ALLOWED",
    "OUTPUT_FILE_EXISTS",
    "EXCEL_UNSUPPORTED_FORMAT",
    "ROWS_REQUIRED",
    "TABLE_HEADER_NOT_FOUND",
    "TABLE_EMPTY",
    "TABLE_TOO_LARGE",
    "INVALID_HEADER_ROW",
    "INVALID_MAX_ROWS",
    "EXCEL_COM_NOT_SUPPORTED",
    "EXCEL_COM_DISPATCH_FAILED",
    "EXCEL_APP_NOT_FOUND",
    "WORKBOOK_OPEN_FAILED",
    "WORKBOOK_SAVE_FAILED",
    "CELL_READ_FAILED",
    "CELL_WRITE_FAILED",
    "HWP_COM_NOT_SUPPORTED",
    "HWP_COM_DISPATCH_FAILED",
    "HWP_APP_NOT_FOUND",
    "HWP_SECURITY_MODULE_REQUIRED",
    "HWP_DOCUMENT_OPEN_FAILED",
    "HWP_TEXT_READ_FAILED",
    "HWP_TEXT_WRITE_FAILED",
    "HWP_DOCUMENT_SAVE_FAILED",
    "CAD_COM_NOT_SUPPORTED",
    "CAD_COM_DISPATCH_FAILED",
    "CAD_APP_NOT_FOUND",
    "CAD_DOCUMENT_OPEN_FAILED",
    "CAD_DOCUMENT_INFO_FAILED",
    "CAD_ENTITY_ADD_FAILED",
    "CAD_DOCUMENT_SAVE_FAILED",
    "CAD_INVALID_PATH",
    "CAD_OVERWRITE_FORBIDDEN",
    "CAD_INVALID_ARGUMENT",
    "CAD_PROXY_UNREACHABLE",
    "CAD_PROXY_TIMEOUT",
    "CAD_PROXY_AUTH_MISSING",
    "CAD_PROXY_UPSTREAM_ERROR",
    "CAD_MISSING_PARAM",
    "WRITE_APPROVAL_REQUIRED",
    "WRITE_NOT_ALLOWED",
    "DRY_RUN_PLANNED",
    "INSTALL_APPROVAL_REQUIRED",
    "INSTALL_PROGRAM_ID_REQUIRED",
    "INSTALL_NOT_IN_ALLOWLIST",
    "INSTALL_ALREADY_INSTALLED",
    "INSTALL_NOT_REQUIRED",
    "EXECUTION_NOT_ENABLED_YET",
    "URL_NOT_ALLOWED",
    "LOGIN_URL_NOT_ALLOWED",
    "TARGET_URL_NOT_ALLOWED",
    "PLAYWRIGHT_ERROR",
    "SECRET_STORE_ERROR",
    "EXCEL_ERROR",
    "ALL_CODES",
    "PREFIX_CODES",
    "is_standard_code",
    "with_reason",
]

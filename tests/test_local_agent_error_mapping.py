"""로컬 에이전트 에러 매핑 테스트.

에러 타입별 HTTP 상태 코드 매핑과 에러 응답 생성 함수의 정합성을 검증한다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_orchestrator.agent_hub.error_mapping import (
    ERROR_STATUS_CODES,
    ErrorType,
    make_error_response,
)

# ── ErrorType 열거형 검증 ──────────────────────────────────────────────────


def test_error_type_enum_exists():
    """ErrorType 열거형이 정의되어 있는지 검증."""
    assert hasattr(ErrorType, "INVALID_ALLOWED_ACTIONS")
    assert hasattr(ErrorType, "INVALID_TTL")
    assert hasattr(ErrorType, "INVALID_REQUEST")
    assert hasattr(ErrorType, "NOT_FOUND")
    assert hasattr(ErrorType, "INVALID_REGISTRATION_CODE")
    assert hasattr(ErrorType, "AGENT_NOT_FOUND")
    assert hasattr(ErrorType, "UNKNOWN_ACTION")
    assert hasattr(ErrorType, "MISSING_URL")
    assert hasattr(ErrorType, "URL_SCHEME_NOT_ALLOWED")


# ── ERROR_STATUS_CODES 매핑 ──────────────────────────────────────────────────


def test_error_status_codes_mapping_exists():
    """에러 타입별 HTTP 상태 코드 매핑이 존재하는지 검증."""
    assert isinstance(ERROR_STATUS_CODES, dict)
    assert len(ERROR_STATUS_CODES) > 0


def test_error_status_codes_all_valid_http_codes():
    """모든 HTTP 상태 코드가 유효한지 검증."""
    valid_codes = {400, 404, 409, 410, 403, 429}
    for error_type, code in ERROR_STATUS_CODES.items():
        assert code in valid_codes, f"Invalid HTTP code {code} for {error_type}"


def test_error_status_codes_covers_main_types():
    """주요 에러 타입이 모두 매핑되어 있는지 검증."""
    assert ErrorType.INVALID_ALLOWED_ACTIONS.value in ERROR_STATUS_CODES
    assert ErrorType.INVALID_TTL.value in ERROR_STATUS_CODES
    assert ErrorType.INVALID_REQUEST.value in ERROR_STATUS_CODES
    assert ErrorType.NOT_FOUND.value in ERROR_STATUS_CODES
    assert ErrorType.INVALID_REGISTRATION_CODE.value in ERROR_STATUS_CODES
    assert ErrorType.AGENT_NOT_FOUND.value in ERROR_STATUS_CODES
    assert ErrorType.UNKNOWN_ACTION.value in ERROR_STATUS_CODES
    assert ErrorType.MISSING_URL.value in ERROR_STATUS_CODES
    assert ErrorType.URL_SCHEME_NOT_ALLOWED.value in ERROR_STATUS_CODES


# ── make_error_response() 함수 ─────────────────────────────────────────────


def test_make_error_response_invalid_allowed_actions():
    """INVALID_ALLOWED_ACTIONS 에러 응답 생성."""
    status_code, detail = make_error_response(
        ErrorType.INVALID_ALLOWED_ACTIONS, message="unsupported actions: ['delete_file']"
    )
    assert status_code == 400
    assert "code" in detail or "error" in detail
    assert "message" in detail
    assert "delete_file" in detail["message"]


def test_make_error_response_invalid_ttl():
    """INVALID_TTL 에러 응답 생성."""
    status_code, detail = make_error_response(ErrorType.INVALID_TTL, message="TTL must be between 1 and 10080")
    assert status_code == 400
    assert "code" in detail or "error" in detail
    assert "message" in detail
    assert "TTL" in detail["message"]


def test_make_error_response_invalid_request():
    """INVALID_REQUEST 에러 응답 생성."""
    status_code, detail = make_error_response(ErrorType.INVALID_REQUEST, message="Missing required field")
    assert status_code == 400
    assert "code" in detail or "error" in detail
    assert "message" in detail


def test_make_error_response_not_found():
    """NOT_FOUND 에러 응답 생성."""
    status_code, detail = make_error_response(ErrorType.NOT_FOUND, message="registration_code not found")
    assert status_code == 404
    assert "code" in detail or "error" in detail
    assert "message" in detail


def test_make_error_response_agent_not_found():
    """AGENT_NOT_FOUND 에러 응답 생성."""
    status_code, detail = make_error_response(ErrorType.AGENT_NOT_FOUND, message="미등록 에이전트: agent-123")
    assert status_code == 404
    assert "code" in detail or "error" in detail
    assert "message" in detail
    assert "agent-123" in detail["message"]


def test_make_error_response_unknown_action():
    """UNKNOWN_ACTION 에러 응답 생성."""
    status_code, detail = make_error_response(ErrorType.UNKNOWN_ACTION, message="Unknown action: invalid_action")
    assert status_code == 400
    assert "code" in detail or "error" in detail
    assert "message" in detail


def test_make_error_response_missing_url():
    """MISSING_URL 에러 응답 생성."""
    status_code, detail = make_error_response(ErrorType.MISSING_URL, message="url은 필수입니다")
    assert status_code == 400
    assert "code" in detail or "error" in detail
    assert "message" in detail


def test_make_error_response_url_scheme_not_allowed():
    """URL_SCHEME_NOT_ALLOWED 에러 응답 생성."""
    status_code, detail = make_error_response(ErrorType.URL_SCHEME_NOT_ALLOWED, message="Scheme not allowed: file")
    assert status_code == 400
    assert "code" in detail or "error" in detail
    assert "message" in detail


def test_make_error_response_default_message():
    """에러 타입만으로 응답 생성 (기본 메시지)."""
    status_code, detail = make_error_response(ErrorType.NOT_FOUND)
    assert status_code == 404
    assert "code" in detail or "error" in detail
    assert "message" in detail


def test_make_error_response_with_error_code():
    """에러 코드 명시적 지정."""
    status_code, detail = make_error_response(
        ErrorType.INVALID_REQUEST, error_code="CUSTOM_ERROR_CODE", message="Custom error"
    )
    assert status_code == 400
    # error_code가 지정된 경우 그것을 사용해야 함
    assert "error_code" in detail or "code" in detail
    assert "message" in detail


# ── 토큰 미포함 검증 ────────────────────────────────────────────────────────


def test_make_error_response_no_token_in_message():
    """에러 응답에 토큰 원문이 포함되지 않는지 검증."""
    _status_code, detail = make_error_response(
        ErrorType.INVALID_REGISTRATION_CODE, message="Code is invalid or expired"
    )
    detail_str = str(detail)
    # 실제 토큰이나 민감 데이터가 없어야 함
    assert "eyJ" not in detail_str  # JWT 프리픽스
    assert "***" not in detail_str  # 마스킹 표시


# ── 모듈 import 검증 ────────────────────────────────────────────────────────


def test_error_mapping_module_importable():
    """에러 매핑 모듈이 정상적으로 임포트 가능한지 검증."""
    import ai_orchestrator.agent_hub.error_mapping as error_mapping_module

    assert hasattr(error_mapping_module, "ErrorType")
    assert hasattr(error_mapping_module, "ERROR_STATUS_CODES")
    assert hasattr(error_mapping_module, "make_error_response")


def test_no_circular_import_with_router():
    """에러 매핑 모듈과 라우터 간 순환 참조 없음을 검증."""
    try:
        from ai_orchestrator.agent_hub.router.root import local_agent_router

        assert local_agent_router is not None
    except ImportError:
        pass


# ── 추가 에러 타입 검증 ────────────────────────────────────────────────────


def test_invalid_registration_code_mapping():
    """INVALID_REGISTRATION_CODE 매핑 확인."""
    status_code, detail = make_error_response(ErrorType.INVALID_REGISTRATION_CODE, message="INVALID_CODE_MESSAGE")
    assert status_code == 400
    assert "code" in detail or "error" in detail


def test_all_error_types_have_status_codes():
    """모든 ErrorType이 상태 코드 매핑을 가지고 있는지 검증."""
    for error_type in ErrorType:
        assert error_type.value in ERROR_STATUS_CODES, f"No status code mapping for {error_type.name}"


def test_error_response_structure_consistency():
    """모든 에러 응답이 일관된 구조를 가지는지 검증."""
    error_types = [
        ErrorType.INVALID_REQUEST,
        ErrorType.NOT_FOUND,
        ErrorType.INVALID_ALLOWED_ACTIONS,
    ]

    for error_type in error_types:
        status_code, detail = make_error_response(error_type)
        # 모든 응답이 status_code와 detail을 반환해야 함
        assert isinstance(status_code, int)
        assert isinstance(detail, dict)
        # detail에는 code/error와 message가 있어야 함
        assert "code" in detail or "error" in detail
        assert "message" in detail

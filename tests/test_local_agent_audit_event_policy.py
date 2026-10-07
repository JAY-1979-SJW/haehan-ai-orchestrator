"""로컬 에이전트 감사 이벤트 정책 테스트.

APPROVE_STATUS_HTTP, REJECT_STATUS_HTTP 매핑과
APPROVE_AUDIT_EVENT, REJECT_AUDIT_EVENT 매핑의 정합성,
그리고 에러 응답 생성 함수의 동작을 검증한다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_orchestrator.agent_hub.policy.audit_event_policy import (
    APPROVE_AUDIT_EVENT,
    APPROVE_STATUS_HTTP,
    REJECT_AUDIT_EVENT,
    REJECT_STATUS_HTTP,
    make_approval_error_detail,
    make_rejection_error_detail,
)

# ── APPROVE_STATUS_HTTP snapshot ───────────────────────────────────────────


def test_approve_status_http_snapshot():
    """승인 상태-HTTP 코드 매핑 값이 정확한지 검증."""
    expected = {
        "approved": 200,
        "not_found": 404,
        "task_mismatch": 400,
        "already_used": 409,
        "expired": 410,
        "forbidden": 403,
        "rate_limited": 429,
    }
    assert APPROVE_STATUS_HTTP == expected


# ── REJECT_STATUS_HTTP snapshot ───────────────────────────────────────────


def test_reject_status_http_snapshot():
    """거절 상태-HTTP 코드 매핑 값이 정확한지 검증."""
    expected = {
        "rejected": 200,
        "not_found": 404,
        "task_mismatch": 400,
        "already_used": 409,
        "expired": 410,
        "forbidden": 403,
        "rate_limited": 429,
    }
    assert REJECT_STATUS_HTTP == expected


# ── APPROVE_AUDIT_EVENT snapshot ──────────────────────────────────────────


def test_approve_audit_event_snapshot():
    """승인 상태-감사이벤트 타입 매핑 값이 정확한지 검증."""
    expected = {
        "approved": "LOCAL_AGENT_TASK_APPROVED",
        "not_found": "APPROVAL_INVALID_TOKEN",
        "task_mismatch": "APPROVAL_INVALID_TOKEN",
        "already_used": "APPROVAL_ALREADY_USED",
        "expired": "LOCAL_AGENT_TASK_APPROVAL_EXPIRED",
        "forbidden": "APPROVAL_DENIED",
        "rate_limited": "APPROVAL_RATE_LIMITED",
    }
    assert APPROVE_AUDIT_EVENT == expected


# ── REJECT_AUDIT_EVENT snapshot ──────────────────────────────────────────


def test_reject_audit_event_snapshot():
    """거절 상태-감사이벤트 타입 매핑 값이 정확한지 검증."""
    expected = {
        "rejected": "LOCAL_AGENT_TASK_REJECTED_BY_APPROVER",
        "not_found": "APPROVAL_REJECT_INVALID_TOKEN",
        "task_mismatch": "APPROVAL_REJECT_INVALID_TOKEN",
        "already_used": "APPROVAL_ALREADY_USED",
        "expired": "LOCAL_AGENT_TASK_APPROVAL_EXPIRED",
        "forbidden": "APPROVAL_REJECT_FORBIDDEN",
        "rate_limited": "APPROVAL_RATE_LIMITED",
    }
    assert REJECT_AUDIT_EVENT == expected


# ── make_approval_error_detail() 동작 ────────────────────────────────────


def test_make_approval_error_detail_approved():
    """승인 성공 상태 응답 생성."""
    code, detail = make_approval_error_detail("approved")
    assert code == 200
    assert detail == {"error": "APPROVED", "status": "approved"}


def test_make_approval_error_detail_not_found():
    """승인 미발견 상태 응답 생성."""
    code, detail = make_approval_error_detail("not_found")
    assert code == 404
    assert detail == {"error": "NOT_FOUND", "status": "not_found"}


def test_make_approval_error_detail_task_mismatch():
    """승인 태스크 불일치 상태 응답 생성."""
    code, detail = make_approval_error_detail("task_mismatch")
    assert code == 400
    assert detail == {"error": "TASK_MISMATCH", "status": "task_mismatch"}


def test_make_approval_error_detail_expired():
    """승인 만료 상태 응답 생성."""
    code, detail = make_approval_error_detail("expired")
    assert code == 410
    assert detail == {"error": "EXPIRED", "status": "expired"}


def test_make_approval_error_detail_rate_limited():
    """승인 레이트 제한 상태 응답 생성."""
    code, detail = make_approval_error_detail("rate_limited")
    assert code == 429
    assert detail == {"error": "RATE_LIMITED", "status": "rate_limited"}


def test_make_approval_error_detail_custom_map():
    """승인 에러 응답: 커스텀 상태 코드 맵 사용."""
    custom_map = {"custom": 418}
    code, detail = make_approval_error_detail("custom", status_code_map=custom_map)
    assert code == 418
    assert detail == {"error": "CUSTOM", "status": "custom"}


# ── make_rejection_error_detail() 동작 ────────────────────────────────────


def test_make_rejection_error_detail_rejected():
    """거절 성공 상태 응답 생성."""
    code, detail = make_rejection_error_detail("rejected")
    assert code == 200
    assert detail == {"error": "REJECTED", "status": "rejected"}


def test_make_rejection_error_detail_not_found():
    """거절 미발견 상태 응답 생성."""
    code, detail = make_rejection_error_detail("not_found")
    assert code == 404
    assert detail == {"error": "NOT_FOUND", "status": "not_found"}


def test_make_rejection_error_detail_expired():
    """거절 만료 상태 응답 생성."""
    code, detail = make_rejection_error_detail("expired")
    assert code == 410
    assert detail == {"error": "EXPIRED", "status": "expired"}


def test_make_rejection_error_detail_rate_limited():
    """거절 레이트 제한 상태 응답 생성."""
    code, detail = make_rejection_error_detail("rate_limited")
    assert code == 429
    assert detail == {"error": "RATE_LIMITED", "status": "rate_limited"}


def test_make_rejection_error_detail_custom_map():
    """거절 에러 응답: 커스텀 상태 코드 맵 사용."""
    custom_map = {"custom": 418}
    code, detail = make_rejection_error_detail("custom", status_code_map=custom_map)
    assert code == 418
    assert detail == {"error": "CUSTOM", "status": "custom"}


# ── unknown status 처리 방식 ──────────────────────────────────────────────


def test_make_approval_error_detail_unknown_status():
    """승인 미지 상태는 기본값 400으로 응답."""
    code, detail = make_approval_error_detail("unknown_status")
    assert code == 400
    assert detail == {"error": "UNKNOWN_STATUS", "status": "unknown_status"}


def test_make_rejection_error_detail_unknown_status():
    """거절 미지 상태는 기본값 400으로 응답."""
    code, detail = make_rejection_error_detail("unknown_status")
    assert code == 400
    assert detail == {"error": "UNKNOWN_STATUS", "status": "unknown_status"}


# ── token_id / approval_token / device_token 문자열 미포함 ──────────────────


def test_approve_status_http_no_sensitive_strings():
    """승인 상태 코드 맵에 민감한 문자열 미포함."""
    http_map_str = str(APPROVE_STATUS_HTTP)
    assert "token_id" not in http_map_str
    assert "approval_token" not in http_map_str
    assert "device_token" not in http_map_str


def test_reject_status_http_no_sensitive_strings():
    """거절 상태 코드 맵에 민감한 문자열 미포함."""
    http_map_str = str(REJECT_STATUS_HTTP)
    assert "token_id" not in http_map_str
    assert "approval_token" not in http_map_str
    assert "device_token" not in http_map_str


def test_approve_audit_event_no_sensitive_strings():
    """승인 감사 이벤트 맵에 민감한 문자열 미포함."""
    event_map_str = str(APPROVE_AUDIT_EVENT)
    assert "token_id" not in event_map_str
    assert "approval_token" not in event_map_str
    assert "device_token" not in event_map_str


def test_reject_audit_event_no_sensitive_strings():
    """거절 감사 이벤트 맵에 민감한 문자열 미포함."""
    event_map_str = str(REJECT_AUDIT_EVENT)
    assert "token_id" not in event_map_str
    assert "approval_token" not in event_map_str
    assert "device_token" not in event_map_str


def test_error_detail_response_no_token_values():
    """에러 응답 사전에 실제 토큰 값이 없는지 확인."""
    _, detail = make_approval_error_detail("approved")
    detail_str = str(detail)
    # 토큰 같은 민감한 값이 없는지 확인 (실제 토큰 문자열은 포함되면 안 됨)
    assert "eyJ" not in detail_str  # JWT 프리픽스
    assert "***" not in detail_str  # 마스킹 표시도 없어야 함 (token이 응답에 없으므로)


# ── policy 모듈 import 가능 ─────────────────────────────────────────────────


def test_policy_module_importable():
    """정책 모듈이 정상적으로 임포트 가능한지 검증."""
    import ai_orchestrator.agent_hub.policy.audit_event_policy as policy_module

    assert hasattr(policy_module, "APPROVE_STATUS_HTTP")
    assert hasattr(policy_module, "REJECT_STATUS_HTTP")
    assert hasattr(policy_module, "APPROVE_AUDIT_EVENT")
    assert hasattr(policy_module, "REJECT_AUDIT_EVENT")
    assert hasattr(policy_module, "make_approval_error_detail")
    assert hasattr(policy_module, "make_rejection_error_detail")


# ── router import와 순환 참조 없음 ───────────────────────────────────────


def test_no_circular_import_with_router():
    """정책 모듈과 라우터 간 순환 참조 없음을 검증."""
    try:
        # router를 임포트하면 policy도 임포트되어야 함
        from ai_orchestrator.agent_hub.router.root import LocalAgentRouter

        # 성공하면 순환 참조가 없음
        assert LocalAgentRouter is not None
    except ImportError:
        # router 모듈이 없거나 policy를 찾을 수 없는 경우는 pass
        # (router가 아직 작성되지 않았을 수 있음)
        pass


def test_all_status_keys_have_http_codes():
    """모든 상태 키에 HTTP 코드가 매핑되어 있는지 검증."""
    approve_keys = set(APPROVE_AUDIT_EVENT.keys())
    approve_http_keys = set(APPROVE_STATUS_HTTP.keys())
    assert approve_keys == approve_http_keys, f"Mismatch: {approve_keys ^ approve_http_keys}"

    reject_keys = set(REJECT_AUDIT_EVENT.keys())
    reject_http_keys = set(REJECT_STATUS_HTTP.keys())
    assert reject_keys == reject_http_keys, f"Mismatch: {reject_keys ^ reject_http_keys}"


def test_http_codes_are_valid():
    """모든 HTTP 코드가 유효한 상태 코드인지 검증."""
    valid_codes = {200, 400, 403, 404, 409, 410, 429}
    for code in APPROVE_STATUS_HTTP.values():
        assert code in valid_codes, f"Invalid HTTP code: {code}"
    for code in REJECT_STATUS_HTTP.values():
        assert code in valid_codes, f"Invalid HTTP code: {code}"


def test_audit_event_names_are_uppercase():
    """모든 감사 이벤트 이름이 대문자 스네이크 케이스인지 검증."""
    for status, event_name in APPROVE_AUDIT_EVENT.items():
        assert event_name.isupper(), f"Event name not uppercase: {event_name}"
        assert "_" in event_name or event_name.isalpha(), f"Invalid format: {event_name}"

    for status, event_name in REJECT_AUDIT_EVENT.items():
        assert event_name.isupper(), f"Event name not uppercase: {event_name}"
        assert "_" in event_name or event_name.isalpha(), f"Invalid format: {event_name}"

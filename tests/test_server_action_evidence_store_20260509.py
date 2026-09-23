"""
Evidence Store 테스트: safe field 저장, 금지 필드 차단
"""

import pytest

from ai_orchestrator.server.action_evidence_store import (
    clear_store,
    save_evidence,
    validate_evidence_fields,
)
from ai_orchestrator.server.action_task_api import api_receive_evidence


@pytest.fixture(autouse=True)
def _clean():
    clear_store()
    yield
    clear_store()


# 1. safe result 저장
def test_save_safe_evidence():
    rec = save_evidence(
        action_name="download_file",
        approval_request_id="req-001",
        params_hash="abc123",
        result_status="SUCCESS",
        result_fields_safe={"downloaded_file_count": 1, "target_url": "https://x.com/f.pdf"},
    )
    assert rec["evidence_id"] is not None
    assert rec["result_status"] == "SUCCESS"
    assert "downloaded_file_count" in rec["result_fields_safe"]


# 2. forbidden field 포함 시 차단
def test_forbidden_field_blocked():
    violations = validate_evidence_fields({"cookie": "abc"})
    assert any("cookie" in v for v in violations)


# 3. cookie/session/storage_state 차단
@pytest.mark.parametrize("field", ["cookie", "session", "storage_state"])
def test_cookie_session_storage_blocked(field):
    violations = validate_evidence_fields({field: "value"})
    assert len(violations) > 0


# 4. password/otp/cert_password 차단
@pytest.mark.parametrize("field", ["password", "otp", "cert_password"])
def test_password_fields_blocked(field):
    violations = validate_evidence_fields({field: "value"})
    assert len(violations) > 0


# 5. evidence file ref만 허용
def test_evidence_file_ref_allowed():
    rec = save_evidence(
        action_name="attach_file",
        approval_request_id="req-002",
        params_hash="abc",
        result_status="SUCCESS",
        result_fields_safe={"attached": True},
        evidence_files_ref=["data/audit/screenshots/screenshot_abc.png"],
    )
    assert rec["evidence_files_ref"] == ["data/audit/screenshots/screenshot_abc.png"]


# 6. 실제 파일 내용 저장 금지
def test_file_content_not_stored():
    violations = validate_evidence_fields({"file_content": b"binary data"})
    assert len(violations) > 0


# 7. api_receive_evidence — 금지 필드 BLOCKED 반환
def test_api_receive_evidence_blocks_forbidden():
    result = api_receive_evidence(
        action_name="download_file",
        approval_request_id="req-x",
        params_hash="abc",
        result_status="SUCCESS",
        result_fields_safe={"cookie": "bad_value"},
    )
    assert result["accepted"] is False
    assert result["evidence_id"] is None
    assert result["blocked_reason"] is not None


# 8. api_receive_evidence — safe field 수용
def test_api_receive_evidence_accepts_safe():
    result = api_receive_evidence(
        action_name="download_file",
        approval_request_id="req-y",
        params_hash="abc",
        result_status="SUCCESS",
        result_fields_safe={"downloaded_count": 3},
    )
    assert result["accepted"] is True
    assert result["evidence_id"] is not None

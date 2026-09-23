"""
Approval/Audit Store 테스트: 저장·금지 필드 차단·상태 기록
"""

import pytest

from ai_orchestrator.server.action_approval_audit_store import (
    STATUS_PENDING,
    clear_store,
    get_approval_request,
    save_approval_request,
    update_approval_status,
)


@pytest.fixture(autouse=True)
def _clean():
    clear_store()
    yield
    clear_store()


# 1. approval_request 저장
def test_save_approval_request():
    rec = save_approval_request(
        approval_request_id="req-001",
        action_name="attach_file",
        params_hash="abc123",
        requested_by="user1",
        scope_safe={"action_name": "attach_file", "site_context": "g2b"},
        summary_safe={"user_intent_summary": "첨부파일 업로드"},
        status=STATUS_PENDING,
    )
    assert rec["approval_request_id"] == "req-001"
    assert rec["action_name"] == "attach_file"
    assert rec["params_hash"] == "abc123"
    assert rec["status"] == STATUS_PENDING


# 2. raw params 저장 안 됨
def test_raw_params_not_stored():
    with pytest.raises(ValueError, match="금지 필드"):
        save_approval_request(
            approval_request_id="req-002",
            action_name="attach_file",
            params_hash="abc",
            requested_by="user1",
            scope_safe={"params": {"file_path": "/tmp/x.hwp"}},  # 금지
            summary_safe={},
        )


# 3. summary_safe만 저장 — 민감 필드 차단
def test_sensitive_field_in_summary_blocked():
    with pytest.raises(ValueError, match="금지 필드"):
        save_approval_request(
            approval_request_id="req-003",
            action_name="attach_file",
            params_hash="abc",
            requested_by="user1",
            scope_safe={},
            summary_safe={"password": "secret123"},  # 금지
        )


# 4. 만료/소비 상태 기록 가능
def test_update_approval_status():
    save_approval_request(
        approval_request_id="req-004",
        action_name="attach_file",
        params_hash="abc",
        requested_by="user1",
        scope_safe={},
        summary_safe={},
    )
    ok = update_approval_status(
        "req-004",
        status="APPROVED_AND_CONSUMED",
        verdict="HANDOFF_READY",
        consumed_at="2026-05-09T00:00:00+00:00",
    )
    assert ok is True
    rec = get_approval_request("req-004")
    assert rec["status"] == "APPROVED_AND_CONSUMED"
    assert rec["verdict"] == "HANDOFF_READY"


# 5. params_hash 기록
def test_params_hash_recorded():
    save_approval_request(
        approval_request_id="req-005",
        action_name="download_file",
        params_hash="deadbeef",
        requested_by="user2",
        scope_safe={},
        summary_safe={},
    )
    rec = get_approval_request("req-005")
    assert rec["params_hash"] == "deadbeef"


# 6. 민감 필드 저장 차단 — cookie/session
@pytest.mark.parametrize("bad_field", ["cookie", "session", "otp", "cert_password", "private_key"])
def test_sensitive_fields_blocked(bad_field):
    with pytest.raises(ValueError, match="금지 필드"):
        save_approval_request(
            approval_request_id="req-bad",
            action_name="attach_file",
            params_hash="abc",
            requested_by="user1",
            scope_safe={bad_field: "value"},
            summary_safe={},
        )

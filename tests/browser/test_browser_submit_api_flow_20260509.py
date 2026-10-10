"""
browser.prepare_submit / browser.submit_with_user_approval API flow 테스트
"""

import pytest
from fastapi.testclient import TestClient

from ai_orchestrator.agent_hub.policy.user_approval_gate import (
    _REQUESTS,
    _TOKENS,
    approve_request,
)
from ai_orchestrator.asgi import app
from ai_orchestrator.server.action_approval_audit_store import clear_store as clear_audit
from ai_orchestrator.server.action_evidence_store import clear_store as clear_evidence
from tools.gates.auth import get_current_user

PREPARE_URL = "/api/v1/actions/prepare"
EVIDENCE_URL = "/api/v1/actions/evidence"


@pytest.fixture
def client():
    # AUTH_ENABLED 기본 true — 이 시험은 인증이 아니라 액션 흐름 검증이므로 의존성만 우회하고 종료 시 복원한다.
    prev = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: {"role": "admin", "actor": "test_user"}
    try:
        yield TestClient(app)
    finally:
        if prev is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = prev


@pytest.fixture(autouse=True)
def _clean():
    _REQUESTS.clear()
    _TOKENS.clear()
    clear_audit()
    clear_evidence()
    yield
    _REQUESTS.clear()
    _TOKENS.clear()
    clear_audit()
    clear_evidence()


# 1. /api/v1/actions/prepare browser.prepare_submit 성공
def test_api_prepare_submit_success(client):
    resp = client.post(
        PREPARE_URL,
        json={
            "action_name": "browser.prepare_submit",
            "params": {
                "page_url": "https://www.g2b.go.kr/submit",
                "submit_selector": "button.submit",
                "target_id": "공고 12345",
            },
            "requested_by": "test_user",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] in ("HANDOFF_READY", "APPROVAL_REQUIRED")


# 2. /api/v1/actions/prepare submit 토큰 없음 APPROVAL_REQUIRED
def test_api_submit_no_token_approval_required(client):
    resp = client.post(
        PREPARE_URL,
        json={
            "action_name": "browser.submit_with_user_approval",
            "params": {
                "page_url": "https://www.g2b.go.kr/submit",
                "submit_selector": "button.submit",
            },
            "requested_by": "test_user",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "APPROVAL_REQUIRED"
    assert data["approval_request_id"] is not None


# 3. /api/v1/actions/prepare submit 토큰 있음 HANDOFF_READY
def test_api_submit_with_token_handoff_ready(client):
    # 1단계: 승인 요청 생성
    prep = client.post(
        PREPARE_URL,
        json={
            "action_name": "browser.submit_with_user_approval",
            "params": {
                "page_url": "https://www.g2b.go.kr/submit",
                "submit_selector": "button.submit",
            },
            "requested_by": "test_user",
        },
    ).json()
    req_id = prep["approval_request_id"]

    # 2단계: 승인 토큰 발급
    approval = approve_request(req_id, approver_user_id="test_user")
    token = approval["approval_token"]

    # 3단계: 토큰으로 재요청
    resp = client.post(
        PREPARE_URL,
        json={
            "action_name": "browser.submit_with_user_approval",
            "params": {
                "page_url": "https://www.g2b.go.kr/submit",
                "submit_selector": "button.submit",
            },
            "requested_by": "test_user",
            "approval_token": token,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "HANDOFF_READY"
    assert data["handoff_required"] is True


# 4. /api/v1/actions/evidence safe result accepted
def test_api_evidence_safe_accepted(client):
    resp = client.post(
        EVIDENCE_URL,
        json={
            "action_name": "browser.submit_with_user_approval",
            "approval_request_id": "req-001",
            "params_hash": "abc123",
            "result_status": "SUCCESS",
            "result_fields_safe": {"submission_status": "SUBMITTED"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted"] is True
    assert data["evidence_id"] is not None


# 5. /api/v1/actions/evidence forbidden field BLOCKED
def test_api_evidence_forbidden_field_blocked(client):
    resp = client.post(
        EVIDENCE_URL,
        json={
            "action_name": "browser.submit_with_user_approval",
            "approval_request_id": "req-001",
            "params_hash": "abc123",
            "result_status": "SUCCESS",
            "result_fields_safe": {"cookie": "bad_value"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted"] is False


# 6. bid/esign 미구현 액션 NOT_IMPLEMENTED 유지
@pytest.mark.parametrize(
    "action_name",
    [
        "bid.prepare_bid",
        "bid.submit_with_user_approval",
        "esign.prepare_signature",
        "esign.execute_with_user_approval",
    ],
)
def test_bid_esign_unimplemented(client, action_name):
    resp = client.post(
        PREPARE_URL,
        json={
            "action_name": action_name,
            "params": {"dummy": "val"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["implemented"] is False


# 7. download_file/attach_file 기존 동작 보존
def test_download_file_still_works(client):
    resp = client.post(
        PREPARE_URL,
        json={
            "action_name": "browser.download_file",
            "params": {"url": "https://www.g2b.go.kr/file.pdf"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "HANDOFF_READY"


def test_attach_file_still_works(client):
    resp = client.post(
        PREPARE_URL,
        json={
            "action_name": "browser.attach_file",
            "params": {
                "file_path": "/tmp/bid.hwp",
                "field_selector": "#attach",
            },
            "requested_by": "test_user",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "APPROVAL_REQUIRED"


# 8. 응답에 민감 필드 미포함
def test_response_no_sensitive_fields(client):
    resp = client.post(
        PREPARE_URL,
        json={
            "action_name": "browser.prepare_submit",
            "params": {
                "page_url": "https://www.g2b.go.kr/submit",
                "submit_selector": "button.submit",
            },
        },
    )
    body = resp.json()
    forbidden = {"password", "otp", "cookie", "session"}
    for f in forbidden:
        assert f not in body


# 9. registry에 핸들러 등록됨
def test_handlers_registered(client):
    # prepare_submit handler 등록 확인 (API 성공으로 간접 확인)
    resp = client.post(
        PREPARE_URL,
        json={
            "action_name": "browser.prepare_submit",
            "params": {"page_url": "https://www.g2b.go.kr/submit"},
        },
    )
    assert resp.status_code == 200


# 10. registry에 implement=True 확인
def test_browser_submit_implemented(client):
    # implemented=False인 액션은 API 응답에서 implemented=False
    # implemented=True인 액션은 API 응답에서 implemented=True
    resp = client.post(
        PREPARE_URL,
        json={
            "action_name": "browser.prepare_submit",
            "params": {"page_url": "https://www.g2b.go.kr/submit"},
        },
    )
    data = resp.json()
    assert data["implemented"] is True

    resp = client.post(
        PREPARE_URL,
        json={
            "action_name": "browser.submit_with_user_approval",
            "params": {"page_url": "https://www.g2b.go.kr/submit"},
        },
    )
    data = resp.json()
    assert data["implemented"] is True
